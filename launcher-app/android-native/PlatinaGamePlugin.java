package org.carloscostaxavier.platinareluzentelauncher;

import android.app.Activity;
import android.content.Intent;
import android.content.res.AssetManager;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import org.libsdl.app.SDLActivity;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@CapacitorPlugin(name = "PlatinaGame")
public class PlatinaGamePlugin extends Plugin {
    private static final long MAX_ROM_BYTES = 512L * 1024L * 1024L;
    private static final String[] REQUIRED_RUNTIME_FILES = {
            "header.bin",
            "firmware.bin",
            "build-version.txt",
            "wazaeffect/we.arc",
            "battle/skill/waza_seq.narc"
    };
    private final ExecutorService worker = Executors.newSingleThreadExecutor();

    @PluginMethod
    public void getRuntimeStatus(PluginCall call) {
        File libs = new File(getContext().getApplicationInfo().nativeLibraryDir);
        boolean nativeLibraries = new File(libs, "libmain.so").isFile()
                && new File(libs, "libSDL2.so").isFile()
                && new File(libs, "libc++_shared.so").isFile();
        boolean runtimeAssets = true;
        for (String relativePath : REQUIRED_RUNTIME_FILES) {
            if (!assetExists("pokeplatinum/" + relativePath)) {
                runtimeAssets = false;
                break;
            }
        }
        JSObject result = new JSObject();
        result.put("available", nativeLibraries && runtimeAssets);
        result.put("abi", "arm64-v8a");
        result.put("nativeLibraries", nativeLibraries);
        result.put("runtimeAssets", runtimeAssets);
        call.resolve(result);
    }

    @PluginMethod
    public void launchGame(PluginCall call) {
        worker.execute(() -> {
            Activity activity = getActivity();
            if (activity == null) {
                call.reject("A atividade Android não está disponível.");
                return;
            }
            try {
                File rom = new File(getContext().getFilesDir(), "roms/current.nds");
                validateRom(rom);
                extractRuntimeAssets();
                activity.runOnUiThread(() -> {
                    try {
                        Intent intent = new Intent(activity, SDLActivity.class);
                        activity.startActivity(intent);
                        JSObject result = new JSObject();
                        result.put("ok", true);
                        result.put("message", "A atividade SDL foi aberta. Confirme se a tela do jogo apareceu no dispositivo; abrir a atividade ainda não confirma que o jogo carregou.");
                        call.resolve(result);
                    } catch (Exception error) {
                        call.reject("Não foi possível iniciar o motor nativo: " + error.getMessage());
                    }
                });
            } catch (Exception error) {
                activity.runOnUiThread(() -> call.reject("Falha ao preparar o jogo: " + error.getMessage()));
            }
        });
    }

    private void validateRom(File rom) throws IOException {
        if (!rom.isFile() || rom.length() < 0x200 || rom.length() > MAX_ROM_BYTES) {
            throw new IOException("Importe primeiro uma ROM Nintendo DS .nds válida.");
        }
        byte[] header = new byte[0x160];
        try (RandomAccessFile input = new RandomAccessFile(rom, "r")) {
            input.readFully(header);
        }
        String title = new String(header, 0, 12, StandardCharsets.US_ASCII).replace("\u0000", "").trim();
        String code = new String(header, 0x0c, 4, StandardCharsets.US_ASCII);
        if (title.isEmpty() || !code.matches("[A-Z0-9]{4}")) {
            throw new IOException("O cabeçalho da ROM importada não parece válido.");
        }
        if (!"CPUE".equals(code)) {
            throw new IOException(
                    "Esta compilação nativa espera Pokémon Platinum USA Rev. 1 (código CPUE). "
                            + "A ROM selecionada não corresponde à versão de jogo configurada.");
        }
    }

    private void extractRuntimeAssets() throws IOException {
        File filesDir = getContext().getFilesDir();
        File destination = new File(filesDir, "pokeplatinum");
        File staging = new File(filesDir, "pokeplatinum.staging");
        File previous = new File(filesDir, "pokeplatinum.previous");
        String expectedVersion = readAssetText("pokeplatinum/build-version.txt").trim();
        if (expectedVersion.isEmpty()) {
            throw new IOException("A versão dos recursos incluídos no APK está vazia.");
        }

        // Recover an interrupted replacement before touching either the current
        // runtime or its backup. A present destination is not automatically valid:
        // the process may have died while an earlier copy was incomplete.
        if (!destination.exists() && previous.exists() && !previous.renameTo(destination)) {
            throw new IOException("Não foi possível recuperar a pasta de recursos anterior.");
        }
        if (destination.exists() && previous.exists()) {
            if (isCompleteRuntime(destination, expectedVersion)) {
                // Destination is already the exact runtime version required by this APK.
                // A stale backup is expendable only after this check succeeds.
                deleteRecursively(previous);
            } else {
                if (!deleteRecursively(destination)) {
                    throw new IOException("Não foi possível remover os recursos incompletos para recuperar o backup.");
                }
                if (!previous.renameTo(destination)) {
                    throw new IOException("Não foi possível restaurar o backup dos recursos do jogo.");
                }
            }
        }

        if (isCompleteRuntime(destination, expectedVersion)) return;

        if (staging.exists() && !deleteRecursively(staging)) {
            throw new IOException("Não foi possível limpar a importação anterior dos recursos locais.");
        }
        copyAssetTree("pokeplatinum", staging);
        if (!isCompleteRuntime(staging, expectedVersion)) {
            if (!deleteRecursively(staging)) {
                throw new IOException("O pacote de recursos está incompleto; a pasta temporária foi mantida em " + staging.getAbsolutePath());
            }
            throw new IOException("O pacote não contém uma versão completa dos recursos obrigatórios do jogo.");
        }

        if (destination.exists()) {
            // The recovery block above should have cleared this path if a backup
            // existed. Never delete an existing backup to make room for a rename.
            if (previous.exists()) {
                if (!deleteRecursively(staging)) {
                    throw new IOException("Não foi possível limpar os recursos temporários; backup preservado em " + previous.getAbsolutePath());
                }
                throw new IOException("Já existe um backup dos recursos; a instalação foi interrompida para preservá-lo.");
            }
            if (!destination.renameTo(previous)) {
                deleteRecursively(staging);
                throw new IOException("Não foi possível guardar a versão anterior dos recursos.");
            }
        }

        if (!staging.renameTo(destination)) {
            if (previous.exists() && !previous.renameTo(destination)) {
                throw new IOException(
                        "Não foi possível instalar os recursos novos. O backup anterior foi preservado em "
                                + previous.getAbsolutePath());
            }
            if (!deleteRecursively(staging)) {
                throw new IOException("A instalação falhou e os recursos temporários permaneceram em " + staging.getAbsolutePath());
            }
            throw new IOException("Não foi possível preparar a pasta de recursos do jogo.");
        }

        if (!isCompleteRuntime(destination, expectedVersion)) {
            // This should be impossible after the validated same-volume rename,
            // but fail safely rather than reporting a corrupt runtime as ready.
            if (!deleteRecursively(destination)) {
                throw new IOException("A verificação final falhou e a pasta instalada não pôde ser removida.");
            }
            if (previous.exists() && !previous.renameTo(destination)) {
                throw new IOException("A verificação final falhou; o backup continua em " + previous.getAbsolutePath());
            }
            throw new IOException("A pasta de recursos instalada não passou na verificação final.");
        }

        // The new runtime is complete. Backup cleanup is non-fatal: a stale
        // backup consumes space but must not turn a successful install into failure.
        deleteRecursively(previous);
    }

    private boolean isCompleteRuntime(File directory, String expectedVersion) {
        if (!directory.isDirectory()) return false;
        for (String relativePath : REQUIRED_RUNTIME_FILES) {
            if (!new File(directory, relativePath).isFile()) return false;
        }
        File stamp = new File(directory, "build-version.txt");
        try {
            return expectedVersion.equals(readFileText(stamp).trim());
        } catch (IOException ignored) {
            return false;
        }
    }

    private void copyAssetTree(String assetPath, File destination) throws IOException {
        AssetManager assets = getContext().getAssets();
        String[] children = assets.list(assetPath);
        if (children != null && children.length > 0) {
            if (!destination.exists() && !destination.mkdirs()) throw new IOException("Não foi possível criar " + destination.getAbsolutePath());
            for (String child : children) copyAssetTree(assetPath + "/" + child, new File(destination, child));
            return;
        }
        File parent = destination.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) throw new IOException("Não foi possível criar " + parent.getAbsolutePath());
        try (InputStream input = assets.open(assetPath);
             FileOutputStream output = new FileOutputStream(destination)) {
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            output.getFD().sync();
        }
    }
    private boolean assetExists(String assetPath) {
        try (InputStream ignored = getContext().getAssets().open(assetPath)) { return true; }
        catch (IOException error) { return false; }
    }
    private String readAssetText(String assetPath) throws IOException {
        try (InputStream input = getContext().getAssets().open(assetPath);
             BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
            StringBuilder value = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) value.append(line).append('\n');
            return value.toString();
        }
    }
    private String readFileText(File file) throws IOException {
        try (InputStream input = new FileInputStream(file);
             BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
            StringBuilder value = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) value.append(line).append('\n');
            return value.toString();
        }
    }
    private boolean deleteRecursively(File file) {
        if (!file.exists()) return true;
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children == null) return false;
            for (File child : children) {
                if (!deleteRecursively(child)) return false;
            }
        }
        return !file.exists() || file.delete();
    }
    @Override
    protected void handleOnDestroy() {
        worker.shutdown();
        super.handleOnDestroy();
    }
}
