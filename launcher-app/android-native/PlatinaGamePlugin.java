package org.carloscostaxavier.platinareluzentelauncher;

import android.app.Activity;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;
import android.system.StructStat;
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
import java.util.HashSet;
import java.util.Set;
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
            "battle/skill/waza_seq.narc",
            "runtime-manifest.txt"
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
        int romVersion = header[0x1e] & 0xff;
        if (!"CPUE".equals(code) || romVersion != 1) {
            throw new IOException(
                    "Esta compilação exige Pokémon Platinum USA Rev. 1 (código CPUE e campo ROM version 0x1E igual a 1). "
                            + "A ROM selecionada não corresponde à versão configurada.");
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

        // Remove staging residue even when the currently installed runtime is
        // already valid. A process may have crashed before its previous install
        // started, and that temporary tree must not accumulate across launches.
        if (staging.exists() && !deleteRecursively(staging)) {
            throw new IOException("Não foi possível limpar a importação anterior dos recursos locais.");
        }

        // Preserve saves created by older APKs before replacing their runtime tree.
        if (destination.exists()) migrateLegacySaveIfNeeded(destination);
        if (isCompleteRuntime(destination, expectedVersion)) return;

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

    private void migrateLegacySaveIfNeeded(File legacyRuntimeDirectory) throws IOException {
        if (isSymbolicLink(legacyRuntimeDirectory)) {
            throw new IOException("A pasta antiga de recursos não pode ser um link simbólico.");
        }
        if (!legacyRuntimeDirectory.isDirectory()) return;

        File legacySave = new File(legacyRuntimeDirectory, "save.bin");
        File canonicalSave = new File(getContext().getFilesDir(), "save.bin");
        if (isSymbolicLink(legacySave) || isSymbolicLink(canonicalSave)) {
            throw new IOException("O arquivo de salvamento contém um link simbólico; migração interrompida.");
        }
        if (!legacySave.exists()) return;
        if (!legacySave.isFile()) {
            throw new IOException("O save antigo não é um arquivo regular; migração interrompida.");
        }
        // The canonical save wins if it already exists: never replace newer progress
        // with an older copy found in the runtime directory.
        if (canonicalSave.exists()) return;

        File staging = new File(getContext().getFilesDir(), "save.bin.migrating");
        if (isSymbolicLink(staging) || staging.exists()) {
            if (!staging.delete()) {
                throw new IOException("Não foi possível limpar o save temporário de uma migração anterior.");
            }
        }

        long expectedLength = legacySave.length();
        long copied = 0;
        try (InputStream input = new FileInputStream(legacySave);
             FileOutputStream output = new FileOutputStream(staging, false)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
                copied += count;
            }
            output.flush();
            output.getFD().sync();
            if (copied != expectedLength) {
                throw new IOException("O save antigo mudou durante a migração; a versão anterior foi preservada.");
            }
        } catch (IOException error) {
            if (!isSymbolicLink(staging)) staging.delete();
            throw error;
        }

        if (isSymbolicLink(canonicalSave)) {
            staging.delete();
            throw new IOException("O destino do save tornou-se um link simbólico durante a migração.");
        }
        if (canonicalSave.exists()) {
            if (!staging.delete()) {
                throw new IOException("O save canônico foi criado, mas o temporário da migração não pôde ser removido.");
            }
            return;
        }
        if (!staging.renameTo(canonicalSave)) {
            if (canonicalSave.exists() && !isSymbolicLink(canonicalSave)) {
                if (!staging.delete()) {
                    throw new IOException("O save canônico já existe, mas não foi possível limpar a cópia temporária.");
                }
                return;
            }
            throw new IOException(
                    "Não foi possível instalar o save migrado; a cópia antiga continua em "
                            + legacySave.getAbsolutePath());
        }
    }

    private boolean isSymbolicLink(File file) {
        try {
            StructStat stat = Os.lstat(file.getAbsolutePath());
            return (stat.st_mode & OsConstants.S_IFMT) == OsConstants.S_IFLNK;
        } catch (ErrnoException error) {
            // A missing entry is not a symlink. Permission/I/O failures are
            // treated as unsafe so validation and cleanup never follow an
            // entry whose type could not be established.
            return error.errno != OsConstants.ENOENT && error.errno != OsConstants.ENOTDIR;
        }
    }

    private boolean isRegularFileWithoutSymlinks(File root, String relativePath) {
        if (!isSafeRuntimePath(relativePath) || isSymbolicLink(root) || !root.isDirectory()) {
            return false;
        }
        String[] components = relativePath.split("/");
        File current = root;
        for (int index = 0; index < components.length; index++) {
            current = new File(current, components[index]);
            if (isSymbolicLink(current)) return false;
            if (index < components.length - 1) {
                if (!current.isDirectory()) return false;
            } else if (!current.isFile()) {
                return false;
            }
        }
        return true;
    }

    private boolean isCompleteRuntime(File directory, String expectedVersion) {
        if (isSymbolicLink(directory) || !directory.isDirectory()) return false;
        for (String relativePath : REQUIRED_RUNTIME_FILES) {
            if (!isRegularFileWithoutSymlinks(directory, relativePath)) return false;
            File required = new File(directory, relativePath);
            if (required.length() <= 0) return false;
        }

        File stamp = new File(directory, "build-version.txt");
        File manifest = new File(directory, "runtime-manifest.txt");
        try {
            if (!isRegularFileWithoutSymlinks(directory, "build-version.txt")
                    || !isRegularFileWithoutSymlinks(directory, "runtime-manifest.txt")) return false;
            if (!expectedVersion.equals(readFileText(stamp).trim())) return false;

            Set<String> listedFiles = new HashSet<>();
            try (InputStream input = new FileInputStream(manifest);
                 BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    String[] fields = line.split("\\t", -1);
                    if (fields.length != 2 || !isSafeRuntimePath(fields[0])
                            || "runtime-manifest.txt".equals(fields[0])) return false;

                    final long expectedSize;
                    try {
                        expectedSize = Long.parseLong(fields[1]);
                    } catch (NumberFormatException invalidSize) {
                        return false;
                    }
                    if (expectedSize < 0) return false;

                    File listedFile = new File(directory, fields[0]);
                    if (!isRegularFileWithoutSymlinks(directory, fields[0])
                            || listedFile.length() != expectedSize
                            || !listedFiles.add(fields[0])) return false;
                }
            }

            if (listedFiles.isEmpty()) return false;
            for (String requiredPath : REQUIRED_RUNTIME_FILES) {
                if (!"runtime-manifest.txt".equals(requiredPath) && !listedFiles.contains(requiredPath)) {
                    return false;
                }
            }
            return true;
        } catch (IOException ignored) {
            return false;
        }
    }

    private boolean isSafeRuntimePath(String relativePath) {
        if (relativePath == null || relativePath.isEmpty() || relativePath.startsWith("/")
                || relativePath.indexOf((char) 92) >= 0 || relativePath.indexOf((char) 0) >= 0) {
            return false;
        }
        for (String component : relativePath.split("/", -1)) {
            if (component.isEmpty() || ".".equals(component) || "..".equals(component)) return false;
        }
        return true;
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
        try (InputStream input = getContext().getAssets().open(assetPath)) {
            return input.read() != -1;
        } catch (IOException error) {
            return false;
        }
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
        // lstat the entry first: File.isDirectory() follows symlinks and would
        // otherwise recurse into an unrelated directory before deleting it.
        if (isSymbolicLink(file)) return file.delete();
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
