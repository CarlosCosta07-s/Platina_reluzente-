'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('platina', Object.freeze({
  getPlatform: () => ipcRenderer.invoke('platina:platform'),
  getRuntimeStatus: () => ipcRenderer.invoke('platina:runtime-status'),
  getImportedRom: () => ipcRenderer.invoke('platina:get-imported-rom'),
  importRom: () => ipcRenderer.invoke('platina:import-rom'),
  launchGame: () => ipcRenderer.invoke('platina:launch-game'),
  onLaunchProgress: (callback) => {
    if (typeof callback !== 'function') return;
    ipcRenderer.on('platina:launch-progress', (_event, message) => callback(String(message)));
  },
  openStartupLog: () => ipcRenderer.invoke('platina:open-startup-log'),
  getBlackStatus: () => ipcRenderer.invoke('platina:black-status'),
  importBlackRom: () => ipcRenderer.invoke('platina:import-black-rom'),
  launchBlackGame: () => ipcRenderer.invoke('platina:launch-black-game')
}));
