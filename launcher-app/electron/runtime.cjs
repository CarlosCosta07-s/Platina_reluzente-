'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

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
const RUNTIME_MANIFEST_FILE = 'launcher-runtime-manifest.json';

function sha256FileSync(filePath) {
  const hash = crypto.createHash('sha256');
  const descriptor = fs.openSync(filePath, 'r');
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  try {
    let bytesRead;
    while ((bytesRead = fs.readSync(descriptor, buffer, 0, buffer.length, null)) > 0) {
      hash.update(buffer.subarray(0, bytesRead));
    }
  } finally {
    fs.closeSync(descriptor);
  }
  return hash.digest('hex');
}

/**
 * Verify the immutable payload manifest emitted by stage-native-runtime.cjs.
 * Extracted game assets, saves and user settings are intentionally outside the
 * manifest; only the shipped native executable and libraries are fingerprinted.
 */
function verifyRuntimeManifest(runtimeRoot, platform = process.platform) {
  const expectedPlatform = platform === 'win32' ? 'windows' : platform;
  try {
    const root = path.resolve(runtimeRoot);
    const rootStat = fs.lstatSync(root);
    if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) return false;

    const markerPath = path.join(root, RUNTIME_VERSION_FILE);
    const manifestPath = path.join(root, RUNTIME_MANIFEST_FILE);
    const markerStat = fs.lstatSync(markerPath);
    const manifestStat = fs.lstatSync(manifestPath);
    if (markerStat.isSymbolicLink() || !markerStat.isFile()
        || manifestStat.isSymbolicLink() || !manifestStat.isFile()) return false;

    const marker = fs.readFileSync(markerPath, 'utf8').trim();
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    if (manifest.schemaVersion !== 1 || manifest.platform !== expectedPlatform
        || typeof manifest.buildId !== 'string'
        || !/^[a-f0-9]{64}$/i.test(manifest.buildId)
        || manifest.buildId !== marker
        || !Array.isArray(manifest.files) || manifest.files.length === 0) return false;

    const seen = new Set();
    const fingerprint = crypto.createHash('sha256');
    let previousPath = '';
    for (const entry of manifest.files) {
      if (!entry || typeof entry.path !== 'string' || !entry.path
          || entry.path.includes('\\') || path.posix.isAbsolute(entry.path)
          || entry.path.split('/').some((part) => !part || part === '.' || part === '..')
          || !Number.isSafeInteger(entry.size) || entry.size <= 0
          || typeof entry.sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(entry.sha256)
          || seen.has(entry.path) || (previousPath && entry.path < previousPath)) return false;
      seen.add(entry.path);
      previousPath = entry.path;

      const filePath = path.join(root, ...entry.path.split('/'));
      const stat = fs.lstatSync(filePath);
      if (stat.isSymbolicLink() || !stat.isFile() || stat.size !== entry.size) return false;
      const actualSha256 = sha256FileSync(filePath);
      if (actualSha256 !== entry.sha256.toLowerCase()) return false;
      fingerprint.update(entry.path + '\0' + entry.sha256.toLowerCase() + '\n');
    }

    const calculatedBuildId = fingerprint.digest('hex');
    const expectedExecutable = platform === 'win32' ? 'main.exe' : 'main';
    if (!seen.has(expectedExecutable)) return false;
    return calculatedBuildId === marker;
  } catch {
    return false;
  }
}

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
    return Boolean(findBundledExecutable(runtimeRoot, platform)
      && verifyRuntimeManifest(runtimeRoot, platform));
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
  if (!verifyRuntimeManifest(source, platform)) {
    throw new Error('The bundled runtime manifest is missing or failed integrity validation. Rebuild the launcher package.');
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
      || !verifyRuntimeManifest(staging, platform)
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

function ensureHorizontalScreenLayout(runtimeRoot) {
  const configPath = path.join(path.resolve(runtimeRoot), 'sim_config.ini');
  let contents = '';
  try {
    const stat = fs.lstatSync(configPath);
    if (stat.isSymbolicLink() || !stat.isFile()) {
      throw new Error('O arquivo de configuração do runtime deve ser um arquivo regular: ' + configPath);
    }
    contents = fs.readFileSync(configPath, 'utf8');
  } catch (error) {
    if (!error || error.code !== 'ENOENT') throw error;
  }

  const newline = contents.includes('\r\n') ? '\r\n' : '\n';
  const hadTrailingNewline = contents.length === 0 || /(?:\r\n|\n)$/.test(contents);
  const lines = contents.length === 0 ? [] : contents.split(/\r?\n/);
  if (hadTrailingNewline && lines.length && lines[lines.length - 1] === '') lines.pop();

  let generalStart = lines.findIndex((line) => /^\s*\[\s*General\s*\]\s*$/i.test(line));
  let changed = false;
  if (generalStart === -1) {
    if (lines.some((line) => line.trim() !== '')) lines.push('');
    lines.push('[General]', 'ScreenLayout=horizontal');
    changed = true;
  } else {
    let generalEnd = lines.length;
    for (let index = generalStart + 1; index < lines.length; index += 1) {
      if (/^\s*\[[^\]]+\]\s*$/.test(lines[index])) {
        generalEnd = index;
        break;
      }
    }

    const layoutLines = [];
    for (let index = generalStart + 1; index < generalEnd; index += 1) {
      if (/^\s*ScreenLayout\s*=/i.test(lines[index])) layoutLines.push(index);
    }
    if (layoutLines.length === 0) {
      lines.splice(generalStart + 1, 0, 'ScreenLayout=horizontal');
      changed = true;
    } else {
      const first = layoutLines[0];
      if (lines[first] !== 'ScreenLayout=horizontal') {
        lines[first] = 'ScreenLayout=horizontal';
        changed = true;
      }
      for (let index = layoutLines.length - 1; index >= 1; index -= 1) {
        lines.splice(layoutLines[index], 1);
        changed = true;
      }
    }
  }

  if (changed) {
    fs.writeFileSync(configPath, lines.join(newline) + (hadTrailingNewline ? newline : ''), 'utf8');
  }
  return configPath;
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
module.exports = { resolveRuntimeDirectory, findBundledExecutable, hasRequiredRuntimeData, isRuntimeUsable: runtimeIsUsable, verifyRuntimeManifest, prepareWritableRuntime, ensureHorizontalScreenLayout, validateNdsHeader };
