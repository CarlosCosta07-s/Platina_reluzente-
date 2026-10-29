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
function validateNdsHeader(header, fileSize) {
  if (!Buffer.isBuffer(header) || header.length < 0x160
      || !Number.isSafeInteger(fileSize) || fileSize < 0x200
      || fileSize > 512 * 1024 * 1024) return false;
  const title = header.subarray(0, 12).toString('ascii').replace(/\0/g, '').trim();
  const code = header.subarray(0x0c, 0x10).toString('ascii');
  // This native build is compiled for Pokémon Platinum USA Rev. 1 (CPUE).
  // Reject other DS games/regions before storing a ROM the runtime cannot use.
  return title.length > 0 && code === 'CPUE';
}
module.exports = { resolveRuntimeDirectory, findBundledExecutable, validateNdsHeader };
