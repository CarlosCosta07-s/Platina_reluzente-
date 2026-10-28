'use strict';

const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

function createWindow() {
  const window = new BrowserWindow({
    width: 1240,
    height: 860,
    minWidth: 760,
    minHeight: 620,
    title: 'Platina Reluzente — Launcher',
    backgroundColor: '#0c1019',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.loadFile(path.join(__dirname, '..', 'index.html'));
}

ipcMain.handle('platina:platform', () => process.platform);

ipcMain.handle('platina:select-rom', async () => {
  const result = await dialog.showOpenDialog({
    title: 'Selecionar ROM local de Nintendo DS',
    properties: ['openFile'],
    filters: [{ name: 'ROM de Nintendo DS', extensions: ['nds'] }, { name: 'Todos os arquivos', extensions: ['*'] }]
  });
  if (result.canceled || result.filePaths.length === 0) return { canceled: true };
  const filePath = result.filePaths[0];
  const stat = await fs.promises.stat(filePath);
  if (!stat.isFile()) return { canceled: true };
  return { canceled: false, path: filePath, name: path.basename(filePath), size: stat.size };
});

ipcMain.handle('platina:select-executable', async () => {
  const result = await dialog.showOpenDialog({
    title: 'Selecionar executável do porte nativo',
    properties: ['openFile'],
    filters: process.platform === 'win32'
      ? [{ name: 'Executável do Windows', extensions: ['exe'] }]
      : [{ name: 'Aplicativo executável', extensions: ['*'] }]
  });
  if (result.canceled || result.filePaths.length === 0) return { canceled: true };
  const filePath = result.filePaths[0];
  const stat = await fs.promises.stat(filePath);
  if (!stat.isFile()) return { canceled: true };
  return { canceled: false, path: filePath, name: path.basename(filePath) };
});

ipcMain.handle('platina:launch-game', async (_event, executablePath) => {
  if (typeof executablePath !== 'string' || executablePath.trim() === '') {
    return { ok: false, message: 'Selecione primeiro o executável do jogo.' };
  }
  const resolvedPath = path.resolve(executablePath);
  let stat;
  try {
    stat = await fs.promises.stat(resolvedPath);
  } catch {
    return { ok: false, message: 'O executável salvo não foi encontrado. Selecione-o novamente.' };
  }
  if (!stat.isFile()) return { ok: false, message: 'O caminho escolhido não é um arquivo.' };
  if (process.platform === 'win32' && path.extname(resolvedPath).toLowerCase() !== '.exe') {
    return { ok: false, message: 'No Windows, selecione o arquivo .exe do pacote nativo.' };
  }
  if (process.platform !== 'win32') {
    try {
      await fs.promises.access(resolvedPath, fs.constants.X_OK);
    } catch {
      return { ok: false, message: 'O arquivo não tem permissão de execução. No Linux, use chmod +x no executável.' };
    }
  }

  return new Promise((resolve) => {
    const child = spawn(resolvedPath, [], {
      cwd: path.dirname(resolvedPath),
      detached: true,
      stdio: 'ignore',
      shell: false,
      windowsHide: false
    });
    child.once('error', (error) => {
      resolve({ ok: false, message: 'Não foi possível iniciar o executável: ' + error.message });
    });
    child.once('spawn', () => {
      child.unref();
      resolve({ ok: true, message: 'O executável foi iniciado em sua própria pasta.' });
    });
  });
});

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
