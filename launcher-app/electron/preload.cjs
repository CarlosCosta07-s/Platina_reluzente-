'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('platina', Object.freeze({
  getPlatform: () => ipcRenderer.invoke('platina:platform'),
  getRuntimeStatus: () => ipcRenderer.invoke('platina:runtime-status'),
  getImportedRom: () => ipcRenderer.invoke('platina:get-imported-rom'),
  importRom: () => ipcRenderer.invoke('platina:import-rom'),
  getLocalizationStatus: () => ipcRenderer.invoke('platina:localization-status'),
  setLanguage: (language) => ipcRenderer.invoke('platina:set-language', language),
  importLocalizationPackage: () => ipcRenderer.invoke('platina:import-localization'),
  launchGame: () => ipcRenderer.invoke('platina:launch-game'),
  onLaunchProgress: (callback) => {
    if (typeof callback !== 'function') return;
    ipcRenderer.on('platina:launch-progress', (_event, progress) => {
      if (progress && typeof progress === 'object') {
        callback({
          gameId: progress.gameId === 'black' ? 'black' : 'platinum',
          message: String(progress.message || '')
        });
      } else {
        callback({ gameId: 'platinum', message: String(progress) });
      }
    });
  },
  openStartupLog: () => ipcRenderer.invoke('platina:open-startup-log'),
  getBlackStatus: () => ipcRenderer.invoke('platina:black-status'),
  importBlackRom: () => ipcRenderer.invoke('platina:import-black-rom'),
  launchBlackGame: () => ipcRenderer.invoke('platina:launch-black-game')
}));
