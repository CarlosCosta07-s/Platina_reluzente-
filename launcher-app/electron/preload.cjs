'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('platina', Object.freeze({
  getPlatform: () => ipcRenderer.invoke('platina:platform'),
  selectRom: () => ipcRenderer.invoke('platina:select-rom'),
  selectExecutable: () => ipcRenderer.invoke('platina:select-executable'),
  launchGame: (executablePath) => ipcRenderer.invoke('platina:launch-game', executablePath)
}));
