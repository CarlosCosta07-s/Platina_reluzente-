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


const RUNTIME_VERSION_FILE = 'launcher-runtime-version.txt';

function runtimeBuildId(runtimeRoot, platform) {
  const versionPath = path.join(runtimeRoot, RUNTIME_VERSION_FILE);
  try {
    const stat = fs.lstatSync(versionPath);
    if (stat.isSymbolicLink() || !stat.isFile()) {
      throw new Error('Runtime build marker is not a regular file: ' + versionPath);
    }
    const value = fs.readFileSync(versionPath, 'utf8').trim();
    if (!value) throw new Error('Runtime build marker is empty: ' + versionPath);
    return value;
  } catch (error) {
    if (!error || error.code !== 'ENOENT') throw error;
    const executable = findBundledExecutable(runtimeRoot, platform);
    if (!executable) throw new Error('Cannot fingerprint a runtime without its native executable.');
    const stat = fs.lstatSync(executable);
    return 'local-' + platform + '-' + stat.size + '-' + Math.trunc(stat.mtimeMs);
  }
}

function assertRuntimeTreeHasNoSymlinks(root) {
  const absoluteRoot = path.resolve(root);
  const rootStat = fs.lstatSync(absoluteRoot);
  if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) {
    throw new Error('Runtime root must be a real directory: ' + absoluteRoot);
  }

  function visit(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const fullPath = path.join(directory, entry.name);
      const stat = fs.lstatSync(fullPath);
      if (stat.isSymbolicLink()) {
        throw new Error('Symbolic links are not allowed in the runtime tree: ' + fullPath);
      }
      if (stat.isDirectory()) visit(fullPath);
      else if (!stat.isFile()) {
        throw new Error('Unsupported entry in runtime tree: ' + fullPath);
      }
    }
  }

  visit(absoluteRoot);
}

function runtimeIsUsable(runtimeRoot, platform) {
  try {
    assertRuntimeTreeHasNoSymlinks(runtimeRoot);
    return Boolean(findBundledExecutable(runtimeRoot, platform));
  } catch {
    return false;
  }
}

function copyRuntimeTreeContents(source, destination) {
  fs.mkdirSync(destination, { recursive: true });
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    const from = path.join(source, entry.name);
    const to = path.join(destination, entry.name);
    const stat = fs.lstatSync(from);
    if (stat.isSymbolicLink()) {
      throw new Error('Symbolic links are not allowed in the runtime tree: ' + from);
    }
    if (stat.isDirectory()) {
      copyRuntimeTreeContents(from, to);
      fs.utimesSync(to, stat.atime, stat.mtime);
    } else if (stat.isFile()) {
      fs.copyFileSync(from, to);
      fs.chmodSync(to, stat.mode & 0o777);
      fs.utimesSync(to, stat.atime, stat.mtime);
    } else {
      throw new Error('Unsupported entry in runtime tree: ' + from);
    }
  }
}

/**
 * Copy the bundled runtime into per-user writable storage before launch.
 * The native engine extracts assets and stores configuration relative to its
 * current working directory, which may be read-only inside an AppImage or an
 * application installed under a protected system directory.
 */
function prepareWritableRuntime(sourceRoot, destinationRoot, platform = process.platform) {
  const source = path.resolve(sourceRoot);
  const destination = path.resolve(destinationRoot);
  if (source === destination) {
    throw new Error('Bundled and writable runtime directories must be different.');
  }

  assertRuntimeTreeHasNoSymlinks(source);
  const sourceExecutable = findBundledExecutable(source, platform);
  if (!sourceExecutable) {
    throw new Error('The bundled runtime is missing its native executable.');
  }
  const sourceBuildId = runtimeBuildId(source, platform);
  const parent = path.dirname(destination);
  const staging = destination + '.staging';
  const previous = destination + '.previous';
  fs.mkdirSync(parent, { recursive: true });

  // Recover the last committed copy before starting another replacement.
  if (fs.existsSync(previous)) {
    if (!fs.existsSync(destination)) {
      fs.renameSync(previous, destination);
    } else if (runtimeIsUsable(destination, platform)) {
      fs.rmSync(previous, { recursive: true, force: true });
    } else {
      fs.rmSync(destination, { recursive: true, force: true });
      fs.renameSync(previous, destination);
    }
  }
  if (fs.existsSync(staging)) fs.rmSync(staging, { recursive: true, force: true });

  if (runtimeIsUsable(destination, platform)) {
    try {
      if (runtimeBuildId(destination, platform) === sourceBuildId) {
        return {
          root: destination,
          executable: path.join(destination, path.basename(sourceExecutable)),
          buildId: sourceBuildId,
          reused: true
        };
      }
    } catch {
      // A malformed local marker requires a clean staged copy.
    }
  }

  // Start from the old writable copy when present so game-created settings and
  // save files survive runtime upgrades; then overlay the exact bundled files.
  if (fs.existsSync(destination)) {
    assertRuntimeTreeHasNoSymlinks(destination);
    copyRuntimeTreeContents(destination, staging);
  } else {
    fs.mkdirSync(staging, { recursive: true });
  }
  copyRuntimeTreeContents(source, staging);
  fs.writeFileSync(path.join(staging, RUNTIME_VERSION_FILE), sourceBuildId + '\n', 'utf8');
  const stagedExecutable = path.join(staging, path.basename(sourceExecutable));
  const executableMode = fs.lstatSync(sourceExecutable).mode & 0o777;
  fs.chmodSync(stagedExecutable, executableMode);

  assertRuntimeTreeHasNoSymlinks(staging);
  if (!findBundledExecutable(staging, platform)
      || runtimeBuildId(staging, platform) !== sourceBuildId) {
    fs.rmSync(staging, { recursive: true, force: true });
    throw new Error('The writable runtime copy failed its post-copy validation.');
  }

  if (fs.existsSync(destination)) fs.renameSync(destination, previous);
  try {
    fs.renameSync(staging, destination);
  } catch (error) {
    if (fs.existsSync(previous) && !fs.existsSync(destination)) {
      fs.renameSync(previous, destination);
    }
    throw error;
  }
  fs.rmSync(previous, { recursive: true, force: true });

  return {
    root: destination,
    executable: path.join(destination, path.basename(sourceExecutable)),
    buildId: sourceBuildId,
    reused: false
  };
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
module.exports = { resolveRuntimeDirectory, findBundledExecutable, hasRequiredRuntimeData, isRuntimeUsable: runtimeIsUsable, prepareWritableRuntime, validateNdsHeader };
