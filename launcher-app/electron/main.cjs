'use strict';
const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { launchNativeProcess, hasActiveNativeProcess, onNativeProcessIdle } = require('./native-process.cjs');
const { commitDesktopRom, recoverDesktopRom } = require('./rom-storage.cjs');
const { resolveRuntimeDirectory, findBundledExecutable, hasRequiredRuntimeData, isRuntimeUsable, prepareWritableRuntime, ensureHorizontalScreenLayout, validateNdsHeader, createPlatinumLaunchSpec } = require('./runtime.cjs');
const { BLACK_ROM_SHA1, blackPaths, ensureBlackDirectories, inspectBlackRom, inspectBlackRuntime, isBlackImportedMetadataValid, createBlackLaunchSpec } = require('./black-runtime.cjs');

const MAX_ROM_BYTES = 512 * 1024 * 1024;
// Native runtime and generated assets are pinned to this exact retail image.
// Header fields alone do not prove that the imported ROM is the expected revision.
const ORIGINAL_ROM_SHA1 = '0862ec35b24de5c7e2dcb88c9eea0873110d755c';

function createWindow() {
  const window = new BrowserWindow({
    width: 1240, height: 860, minWidth: 760, minHeight: 620,
    title: 'Platina Reluzente — Biblioteca de Ports Nativos', backgroundColor: '#0c1019',
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
  const recoveryResult = await recoverDesktopRom({ destinationPath: filePath, metadataPath: metadataFile, expectedSha1: ORIGINAL_ROM_SHA1 });
  if (recoveryResult === false) return null;
  try {
    const [metadataText, stat, metadataStat] = await Promise.all([
      fs.promises.readFile(metadataFile, 'utf8'),
      fs.promises.lstat(filePath),
      fs.promises.lstat(metadataFile)
    ]);
    const metadata = JSON.parse(metadataText);
    if (stat.isSymbolicLink() || !stat.isFile()
        || metadataStat.isSymbolicLink() || !metadataStat.isFile()
        || !Number.isSafeInteger(metadata.size) || stat.size !== metadata.size) {
      return null;
    }
    // Imports saved by older launcher versions did not carry the approved
    // full-image SHA-1. Require it here too so stale metadata cannot bypass
    // the strict revision check after an application update.
    if (typeof metadata.sha1 !== 'string'
        || metadata.sha1.toLowerCase() !== ORIGINAL_ROM_SHA1) {
      return null;
    }
    return { ...metadata, filePath };
  } catch (error) {
    if (error && (error.code === 'ENOENT' || error.code === 'ENOTDIR')) return null;
    throw error;
  }
}
async function readImportedBlackRom() {
  const paths = blackPaths({ platform: process.platform, env: process.env });
  const recoveryResult = await recoverDesktopRom({
    destinationPath: paths.romPath,
    metadataPath: paths.romMetadataPath,
    expectedSha1: BLACK_ROM_SHA1
  });
  if (recoveryResult === false) return null;

  try {
    const [metadataText, stat] = await Promise.all([
      fs.promises.readFile(paths.romMetadataPath, 'utf8'),
      fs.promises.lstat(paths.romPath)
    ]);
    if (stat.isSymbolicLink() || !stat.isFile()) return null;
    const metadata = JSON.parse(metadataText);
    if (!isBlackImportedMetadataValid(metadata, stat.size)) return null;
    return { ...metadata, filePath: paths.romPath };
  } catch (error) {
    if (error && (error.code === 'ENOENT' || error.code === 'ENOTDIR')) return null;
    throw error;
  }
}

function blackRuntimeDirectory() {
  // The runtime is an internal resource of this app. It is never selected by
  // the player and is not launched through an external file picker.
  // Keep runtime files in a child folder so staging never replaces the
  // tracked README that documents this reserved resource slot.
  return app.isPackaged
    ? path.join(process.resourcesPath, 'black-runtime', 'runtime')
    : path.join(__dirname, '..', 'black-runtime', 'runtime');
}
async function readBundledBlackRuntime() {
  try {
    const runtime = await inspectBlackRuntime(blackRuntimeDirectory(), process.platform);
    return { runtime, error: '' };
  } catch (error) {
    if (error && (error.code === 'ENOENT' || error.code === 'ENOTDIR')) {
      return {
        runtime: null,
        error: 'O runtime nativo de Pokémon Black ainda não está integrado ao pacote único. A integração depende de uma base distribuível legalmente.'
      };
    }
    return { runtime: null, error: 'O runtime interno de Pokémon Black não passou na validação: ' + error.message };
  }
}

ipcMain.handle('platina:platform', () => process.platform);
ipcMain.handle('platina:runtime-status', async () => {
  const root = runtimeRoot();
  const exe = findBundledExecutable(root, process.platform);
  const packagedDataAvailable = hasRequiredRuntimeData(root);
  const writableDataAvailable = hasRequiredRuntimeData(
    path.join(app.getPath('userData'), 'runtime')
  );
  const runtimeDataAvailable = packagedDataAvailable || writableDataAvailable;
  const runtimeAvailable = isRuntimeUsable(root, process.platform);
  return {
    available: runtimeAvailable,
    executableName: exe ? path.basename(exe) : '',
    runtimeDataAvailable,
    extractOnFirstLaunch: !runtimeDataAvailable,
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
  let headerBytesRead = 0;
  try {
    while (headerBytesRead < header.length) {
      const { bytesRead } = await sourceFile.read(
        header,
        headerBytesRead,
        header.length - headerBytesRead,
        headerBytesRead
      );
      if (bytesRead === 0) break;
      headerBytesRead += bytesRead;
    }
  } finally {
    await sourceFile.close();
  }
  if (headerBytesRead !== header.length) {
    return { canceled: false, ok: false, message: 'Não foi possível ler o cabeçalho completo da ROM selecionada.' };
  }
  if (header.subarray(0x0c, 0x10).toString('ascii') === 'CPUE' && header[0x1e] === 0) {
    return {
      canceled: false,
      ok: false,
      message: 'A ROM selecionada é Pokémon Platinum USA Rev. 0. Este build nativo foi preparado para USA Rev. 1; use uma cópia original Rev. 1 ou aguarde uma implementação específica e validada para Rev. 0.'
    };
  }
  if (!validateNdsHeader(header, stat.size)) {
    return {
      canceled: false,
      ok: false,
      message: 'Esta compilação exige Pokémon Platinum USA Rev. 1 (código CPUE e campo ROM version 0x1E igual a 1). A ROM selecionada não corresponde à versão configurada.'
    };
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
    },
    expectedSha1: ORIGINAL_ROM_SHA1
  });
  return { canceled: false, ok: true, name: metadata.name, size: metadata.size, sha256: metadata.sha256 };
});

ipcMain.handle('platina:black-status', async () => {
  const [rom, bundledRuntime] = await Promise.all([
    readImportedBlackRom(),
    readBundledBlackRuntime()
  ]);
  return {
    runtimeAvailable: Boolean(bundledRuntime.runtime),
    romImported: Boolean(rom),
    romName: rom ? rom.name : '',
    romSize: rom ? rom.size : 0,
    error: bundledRuntime.error || '',
    platform: process.platform
  };
});

ipcMain.handle('platina:import-black-rom', async () => {
  const selection = await dialog.showOpenDialog({
    title: 'Importar ROM local de Pokémon Black',
    properties: ['openFile'],
    filters: [{ name: 'ROM de Nintendo DS (.nds)', extensions: ['nds'] }]
  });
  if (selection.canceled || selection.filePaths.length === 0) return { canceled: true };

  const source = selection.filePaths[0];
  try {
    const inspected = await inspectBlackRom(source);
    const paths = blackPaths({ platform: process.platform, env: process.env });
    await ensureBlackDirectories(paths);
    const metadata = await commitDesktopRom({
      sourcePath: source,
      destinationPath: paths.romPath,
      metadataPath: paths.romMetadataPath,
      metadata: {
        name: path.basename(source),
        size: inspected.size,
        importedAt: new Date().toISOString()
      },
      expectedSha1: BLACK_ROM_SHA1
    });
    return {
      canceled: false,
      ok: true,
      name: metadata.name,
      size: metadata.size,
      sha1: metadata.sha1,
      sha256: metadata.sha256
    };
  } catch (error) {
    return { canceled: false, ok: false, message: error.message };
  }
});

ipcMain.handle('platina:launch-black-game', async () => {
  const paths = blackPaths({ platform: process.platform, env: process.env });
  let rom;
  try {
    rom = await readImportedBlackRom();
  } catch (error) {
    return { ok: false, message: 'Não foi possível verificar a ROM importada de Pokémon Black: ' + error.message };
  }
  if (!rom) {
    return { ok: false, message: 'Importe uma ROM compatível de Pokémon Black antes de iniciar.' };
  }

  const bundledRuntime = await readBundledBlackRuntime();
  if (!bundledRuntime.runtime) {
    return {
      ok: false,
      message: bundledRuntime.error || 'O runtime nativo de Pokémon Black ainda não está integrado ao pacote único.'
    };
  }

  try {
    await ensureBlackDirectories(paths);
    const spec = createBlackLaunchSpec({
      runtime: bundledRuntime.runtime,
      paths,
      romPath: rom.filePath,
      romSha256: rom.sha256,
      platform: process.platform,
      env: process.env
    });
    const result = await launchNativeProcess({
      ...spec,
      platform: process.platform,
      romSha256: rom.sha256
    });
    if (result.ok) {
      return {
        ...result,
        message: 'O processo nativo de Pokémon Black foi iniciado. Isso ainda não confirma a tela de título; consulte o log se a janela não aparecer: ' + result.logPath
      };
    }
    return result;
  } catch (error) {
    return { ok: false, message: 'Falha ao preparar a inicialização de Pokémon Black: ' + error.message, logPath: paths.logPath };
  }
});

ipcMain.handle('platina:open-startup-log', async () => {
  const logPath = path.join(app.getPath('userData'), 'logs', 'native-startup.log');
  try {
    await fs.promises.mkdir(path.dirname(logPath), { recursive: true });
    let stat;
    try {
      stat = await fs.promises.lstat(logPath);
    } catch (error) {
      if (!error || error.code !== 'ENOENT') throw error;
      // Make the action useful even before the first launch attempt. Use
      // exclusive creation so an unexpected file or symlink is never followed.
      try {
        await fs.promises.writeFile(
          logPath,
          'Nenhuma tentativa de inicialização nativa foi registrada ainda.\n',
          { encoding: 'utf8', flag: 'wx', mode: 0o600 }
        );
      } catch (createError) {
        if (!createError || createError.code !== 'EEXIST') throw createError;
      }
      stat = await fs.promises.lstat(logPath);
    }
    if (stat.isSymbolicLink() || !stat.isFile()) {
      return { ok: false, message: 'O caminho do log não é um arquivo regular seguro.', logPath };
    }
    const openError = await shell.openPath(logPath);
    if (openError) {
      return { ok: false, message: 'Não foi possível abrir o log automaticamente: ' + openError, logPath };
    }
    return { ok: true, logPath, message: 'Log de inicialização aberto: ' + logPath };
  } catch (error) {
    return { ok: false, message: 'Não foi possível abrir o log de inicialização: ' + error.message, logPath };
  }
});

ipcMain.handle('platina:launch-game', async () => {
  const rom = await readImportedRom();
  if (!rom) return { ok: false, message: 'Importe primeiro a ROM .nds.' };
  const root = runtimeRoot();
  const exe = findBundledExecutable(root, process.platform);
  if (!exe) {
    return {
      ok: false,
      message: 'Este pacote desktop está incompleto: o executável nativo está ausente. Baixe o pacote mais recente.'
    };
  }
  let writableRuntime;
  try {
    writableRuntime = prepareWritableRuntime(
      root,
      path.join(app.getPath('userData'), 'runtime'),
      process.platform
    );
    ensureHorizontalScreenLayout(writableRuntime.root);
  } catch (error) {
    return {
      ok: false,
      message: 'Não foi possível preparar a pasta gravável do jogo: ' + error.message
    };
  }
  const logPath = path.join(app.getPath('userData'), 'logs', 'native-startup.log');
  try {
    const launchSpec = createPlatinumLaunchSpec({
      runtime: writableRuntime,
      rom,
      logPath,
      platform: process.platform,
      env: process.env
    });
    return launchNativeProcess(launchSpec);
  } catch (error) {
    return {
      ok: false,
      message: 'Não foi possível preparar a chamada de inicialização de Pokémon Platinum: ' + error.message,
      logPath
    };
  }
});

const hasSingleInstanceLock = app.requestSingleInstanceLock();

if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const windows = BrowserWindow.getAllWindows();
    if (windows.length === 0) {
      createWindow();
      return;
    }
    const mainWindow = windows[0];
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    createWindow();
    app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
  });

  app.on('window-all-closed', () => {
    if (process.platform === 'darwin') return;
    if (hasActiveNativeProcess()) {
      // Keep this one launcher process alive until the game exits. This retains
      // the in-process launch guard and prevents a second launcher from starting
      // another native game while the first game window is still open.
      onNativeProcessIdle(() => {
        if (BrowserWindow.getAllWindows().length === 0) app.quit();
      });
      return;
    }
    app.quit();
  });
}
