'use strict';
const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { commitDesktopRom, recoverDesktopRom } = require('./rom-storage.cjs');
const { resolveRuntimeDirectory, findBundledExecutable, hasRequiredRuntimeData, validateNdsHeader } = require('./runtime.cjs');

const MAX_ROM_BYTES = 512 * 1024 * 1024;

function createWindow() {
  const window = new BrowserWindow({
    width: 1240, height: 860, minWidth: 760, minHeight: 620,
    title: 'Platina Reluzente — Launcher', backgroundColor: '#0c1019',
    autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false }
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.loadFile(path.join(__dirname, '..', 'web-dist', 'index.html'));
}
function runtimeRoot() {
  return resolveRuntimeDirectory(app.isPackaged, process.resourcesPath, path.resolve(__dirname, '..'));
}
function metadataPath() {
  return path.join(app.getPath('userData'), 'rom-import.json');
}
async function readImportedRom() {
  const filePath = path.join(app.getPath('userData'), 'roms', 'current.nds');
  const metadataFile = metadataPath();
  // Verify the saved ROM against its SHA-256 sidecar and recover interrupted
  // imports before exposing it. Unverified files are not shown as imported;
  // ambiguous transaction residue and storage errors still surface to the UI.
  const recoveryResult = await recoverDesktopRom({ destinationPath: filePath, metadataPath: metadataFile });
  if (recoveryResult === false) return null;
  try {
    const [metadataText, stat] = await Promise.all([
      fs.promises.readFile(metadataFile, 'utf8'),
      fs.promises.stat(filePath)
    ]);
    const metadata = JSON.parse(metadataText);
    if (!stat.isFile() || !Number.isSafeInteger(metadata.size) || stat.size !== metadata.size) {
      return null;
    }
    return { ...metadata, filePath };
  } catch (error) {
    if (error && (error.code === 'ENOENT' || error.code === 'ENOTDIR')) return null;
    throw error;
  }
}
ipcMain.handle('platina:platform', () => process.platform);
ipcMain.handle('platina:runtime-status', async () => {
  const root = runtimeRoot();
  const exe = findBundledExecutable(root, process.platform);
  const runtimeDataAvailable = hasRequiredRuntimeData(root);
  return {
    available: Boolean(exe && runtimeDataAvailable),
    executableName: exe ? path.basename(exe) : '',
    runtimeDataAvailable,
    platform: process.platform
  };
});
ipcMain.handle('platina:get-imported-rom', async () => {
  const rom = await readImportedRom();
  return rom ? { name: rom.name, size: rom.size, sha256: rom.sha256 } : null;
});
ipcMain.handle('platina:import-rom', async () => {
  const selection = await dialog.showOpenDialog({
    title: 'Importar ROM local de Nintendo DS',
    properties: ['openFile'],
    filters: [{ name: 'ROM de Nintendo DS (.nds)', extensions: ['nds'] }]
  });
  if (selection.canceled || selection.filePaths.length === 0) return { canceled: true };

  const source = selection.filePaths[0];
  const stat = await fs.promises.stat(source);
  if (!stat.isFile() || path.extname(source).toLowerCase() !== '.nds') {
    return { canceled: false, ok: false, message: 'Selecione um arquivo .nds.' };
  }
  if (stat.size < 0x200 || stat.size > MAX_ROM_BYTES) {
    return { canceled: false, ok: false, message: 'Tamanho inválido para uma ROM Nintendo DS. Limite: 512 MiB.' };
  }

  const sourceFile = await fs.promises.open(source, 'r');
  const header = Buffer.alloc(0x200);
  try { await sourceFile.read(header, 0, header.length, 0); }
  finally { await sourceFile.close(); }
  if (!validateNdsHeader(header, stat.size)) {
    return { canceled: false, ok: false, message: 'Esta compilação espera Pokémon Platinum USA Rev. 1 (código CPUE). A ROM selecionada não corresponde à versão configurada.' };
  }

  const romDir = path.join(app.getPath('userData'), 'roms');
  const destination = path.join(romDir, 'current.nds');
  const metadata = await commitDesktopRom({
    sourcePath: source,
    destinationPath: destination,
    metadataPath: metadataPath(),
    metadata: {
      name: path.basename(source),
      size: stat.size,
      importedAt: new Date().toISOString()
    }
  });
  return { canceled: false, ok: true, name: metadata.name, size: metadata.size, sha256: metadata.sha256 };
});

ipcMain.handle('platina:launch-game', async () => {
  const rom = await readImportedRom();
  if (!rom) return { ok: false, message: 'Importe primeiro a ROM .nds.' };
  const root = runtimeRoot();
  const exe = findBundledExecutable(root, process.platform);
  const runtimeDataAvailable = hasRequiredRuntimeData(root);
  if (!exe || !runtimeDataAvailable) {
    return {
      ok: false,
      message: 'Este pacote desktop está incompleto: o executável nativo ou os recursos obrigatórios do jogo estão ausentes. Baixe o pacote completo mais recente.'
    };
  }
  return new Promise((resolve) => {
    const child = spawn(exe, [], {
      cwd: root, detached: true, stdio: 'ignore', shell: false, windowsHide: false,
      env: { ...process.env, PLATINA_IMPORTED_ROM: rom.filePath }
    });
    child.once('error', (error) => resolve({ ok: false, message: 'Falha ao iniciar o executável nativo: ' + error.message }));
    child.once('spawn', () => {
      child.unref();
      resolve({ ok: true, message: 'O executável nativo incluído no pacote foi iniciado.' });
    });
  });
});

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
