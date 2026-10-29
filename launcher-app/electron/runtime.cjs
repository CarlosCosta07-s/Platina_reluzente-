'use strict';
const fs = require('node:fs');
const path = require('node:path');

function resolveRuntimeDirectory(isPackaged, resourcesPath, appDirectory) {
  return isPackaged ? path.join(resourcesPath, 'runtime') : path.join(appDirectory, 'runtime');
}
function findBundledExecutable(runtimeRoot, platform = process.platform) {
  const names = platform === 'win32' ? ['main.exe'] : ['main'];
  try {
    const rootStat = fs.lstatSync(runtimeRoot);
    if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) return null;
  } catch {
    return null;
  }

  for (const name of names) {
    const candidate = path.join(runtimeRoot, name);
    try {
      // The executable is bundled by the build workflow. Do not follow a
      // symbolic link that could point outside the application runtime.
      const stat = fs.lstatSync(candidate);
      if (stat.isSymbolicLink() || !stat.isFile()) continue;
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
  let rootStat;
  try {
    rootStat = fs.lstatSync(runtimeRoot);
  } catch (error) {
    if (error && (error.code === 'ENOENT' || error.code === 'ENOTDIR')) return false;
    throw error;
  }
  if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) return false;

  for (const relativePath of REQUIRED_RUNTIME_FILES) {
    const components = relativePath.split('/');
    let currentPath = path.resolve(runtimeRoot);
    for (let index = 0; index < components.length; index += 1) {
      currentPath = path.join(currentPath, components[index]);
      let stat;
      try {
        // lstat each component so a linked parent directory cannot redirect
        // validation to a file outside the packaged runtime.
        stat = fs.lstatSync(currentPath);
      } catch (error) {
        if (error && (error.code === 'ENOENT' || error.code === 'ENOTDIR')) return false;
        throw error;
      }
      if (stat.isSymbolicLink()) return false;
      if (index < components.length - 1) {
        if (!stat.isDirectory()) return false;
      } else if (!stat.isFile() || stat.size === 0) {
        return false;
      }
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
