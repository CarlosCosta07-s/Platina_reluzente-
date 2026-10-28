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
    private final ExecutorService worker = Executors.newSingleThreadExecutor();

    @PluginMethod
    public void getRuntimeStatus(PluginCall call) {
        File libs = new File(getContext().getApplicationInfo().nativeLibraryDir);
        boolean nativeLibraries = new File(libs, "libmain.so").isFile()
                && new File(libs, "libSDL2.so").isFile()
                && new File(libs, "libc++_shared.so").isFile();
        boolean runtimeAssets = assetExists("pokeplatinum/header.bin")
                && assetExists("pokeplatinum/firmware.bin")
                && assetExists("pokeplatinum/build-version.txt");
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
                        result.put("message", "ROM importada; iniciando o motor nativo incluído neste APK.");
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
    }

    private void extractRuntimeAssets() throws IOException {
        File filesDir = getContext().getFilesDir();
        File destination = new File(filesDir, "pokeplatinum");
        String expectedVersion = readAssetText("pokeplatinum/build-version.txt").trim();
        File stamp = new File(destination, "build-version.txt");
        if (destination.isDirectory()
                && new File(destination, "header.bin").isFile()
                && new File(destination, "firmware.bin").isFile()
                && stamp.isFile()
                && expectedVersion.equals(readFileText(stamp).trim())) return;

        File staging = new File(filesDir, "pokeplatinum.staging");
        File previous = new File(filesDir, "pokeplatinum.previous");
        deleteRecursively(staging);
        deleteRecursively(previous);
        copyAssetTree("pokeplatinum", staging);
        if (!new File(staging, "header.bin").isFile()
                || !new File(staging, "firmware.bin").isFile()
                || !new File(staging, "build-version.txt").isFile()) {
            deleteRecursively(staging);
            throw new IOException("O pacote não contém todos os recursos obrigatórios do jogo.");
        }
        if (destination.exists() && !destination.renameTo(previous)) {
            deleteRecursively(staging);
            throw new IOException("Não foi possível atualizar os recursos locais do jogo.");
        }
        if (!staging.renameTo(destination)) {
            if (previous.exists()) previous.renameTo(destination);
            deleteRecursively(staging);
            throw new IOException("Não foi possível preparar a pasta de recursos do jogo.");
        }
        deleteRecursively(previous);
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
    private void deleteRecursively(File file) {
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children != null) for (File child : children) deleteRecursively(child);
        }
        if (file.exists() && !file.delete()) file.deleteOnExit();
    }
    @Override
    protected void handleOnDestroy() {
        worker.shutdown();
        super.handleOnDestroy();
    }
}
