'use strict';
const fs = require('node:fs');
const path = require('node:path');

function resolveRuntimeDirectory(isPackaged, resourcesPath, appDirectory) {
  return isPackaged ? path.join(resourcesPath, 'runtime') : path.join(appDirectory, 'runtime');
}
function findBundledExecutable(runtimeRoot, platform = process.platform) {
  const names = platform === 'win32' ? ['main.exe'] : ['main'];
  for (const name of names) {
    const candidate = path.join(runtimeRoot, name);
    try {
      if (!fs.statSync(candidate).isFile()) continue;
      if (platform !== 'win32') fs.accessSync(candidate, fs.constants.X_OK);
      return candidate;
    } catch {}
  }
  return null;
}
const REQUIRED_RUNTIME_FILES = [
  'header.bin',
  'firmware.bin',
  'wazaeffect/we.arc',
  'battle/skill/waza_seq.narc'
];

function hasRequiredRuntimeData(runtimeRoot) {
  for (const relativePath of REQUIRED_RUNTIME_FILES) {
    try {
      const stat = fs.statSync(path.join(runtimeRoot, relativePath));
      if (!stat.isFile() || stat.size === 0) return false;
    } catch (error) {
      if (error && (error.code === 'ENOENT' || error.code === 'ENOTDIR')) return false;
      throw error;
    }
  }
  return true;
}

function validateNdsHeader(header, fileSize) {
  if (!Buffer.isBuffer(header) || header.length < 0x160
      || !Number.isSafeInteger(fileSize) || fileSize < 0x200
      || fileSize > 512 * 1024 * 1024) return false;
  const title = header.subarray(0, 12).toString('ascii').replace(/\0/g, '').trim();
  const code = header.subarray(0x0c, 0x10).toString('ascii');
  const romVersion = header[0x1e];
  // This native build is compiled for Pokémon Platinum USA Rev. 1 (CPUE).
  // The game code alone does not distinguish a revision, so verify the NDS
  // header's ROM-version byte as well.
  return title.length > 0 && code === 'CPUE' && romVersion === 1;
}
module.exports = { resolveRuntimeDirectory, findBundledExecutable, hasRequiredRuntimeData, validateNdsHeader };
