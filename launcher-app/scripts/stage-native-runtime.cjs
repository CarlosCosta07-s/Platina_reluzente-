'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const REQUIRED_RUNTIME_FILES = [
  'header.bin',
  'firmware.bin',
  'wazaeffect/we.arc',
  'battle/skill/waza_seq.narc'
];

const PERSONAL_FILES = new Set([
  'save.bin',
  'sim_config.ini',
  'launcher-runtime-version.txt'
]);

// Never package a local ROM, save dump, or patch by accident.
const FORBIDDEN_EXTENSIONS = new Set([
  '.nds', '.3ds', '.cia', '.cci', '.iso', '.gba', '.gbc', '.gb',
  '.n64', '.z64', '.v64', '.gcm', '.wbfs', '.dsv', '.sav',
  '.xdelta', '.ips', '.bps'
]);

const TARGETS = Object.freeze({
  linux: Object.freeze({ buildDirectory: 'build_linux', executable: 'main' }),
  windows: Object.freeze({ buildDirectory: 'build_win64', executable: 'main.exe' })
});

function requireRealDirectory(directory, label) {
  const stat = fs.lstatSync(directory);
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error(label + ' precisa ser uma pasta real, sem link simbólico: ' + directory);
  }
}

function inspectRuntimeTree(sourceRoot, expectedExecutable, platform) {
  requireRealDirectory(sourceRoot, 'Runtime de origem');
  const files = [];

  function visit(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const sourcePath = path.join(directory, entry.name);
      const stat = fs.lstatSync(sourcePath);
      const relativePath = path.relative(sourceRoot, sourcePath).split(path.sep).join('/');
      if (stat.isSymbolicLink()) {
        throw new Error('Runtime contém link simbólico; não será empacotado: ' + relativePath);
      }
      if (stat.isDirectory()) {
        visit(sourcePath);
        continue;
      }
      if (!stat.isFile()) {
        throw new Error('Runtime contém uma entrada especial não suportada: ' + relativePath);
      }

      const extension = path.extname(entry.name).toLowerCase();
      if (FORBIDDEN_EXTENSIONS.has(extension)) {
        throw new Error('Arquivo ROM/save/patch proibido na pasta de runtime: ' + relativePath);
      }
      if (PERSONAL_FILES.has(entry.name.toLowerCase())) {
        continue;
      }
      files.push({ sourcePath, relativePath, mode: stat.mode & 0o777 });
    }
  }

  visit(sourceRoot);
  files.sort((a, b) => a.relativePath < b.relativePath ? -1 : a.relativePath > b.relativePath ? 1 : 0);

  const names = new Set(files.map((file) => file.relativePath));
  if (!names.has(expectedExecutable)) {
    throw new Error('Executável nativo obrigatório ausente: ' + expectedExecutable);
  }
  for (const relativePath of REQUIRED_RUNTIME_FILES) {
    if (!names.has(relativePath)) {
      throw new Error('Recurso obrigatório ausente no runtime: ' + relativePath);
    }
    const required = files.find((file) => file.relativePath === relativePath);
    if (fs.statSync(required.sourcePath).size === 0) {
      throw new Error('Recurso obrigatório está vazio: ' + relativePath);
    }
  }

  const executable = files.find((file) => file.relativePath === expectedExecutable);
  if (platform === 'linux' && (executable.mode & 0o111) === 0) {
    throw new Error('O executável Linux não possui permissão de execução: ' + expectedExecutable);
  }
  return files;
}

function hashFile(filePath) {
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

function lstatIfPresent(filePath) {
  try {
    return fs.lstatSync(filePath);
  } catch (error) {
    if (error && error.code === 'ENOENT') return null;
    throw error;
  }
}

function stageNativeRuntime({ sourceRoot, destinationRoot, platform }) {
  if (!Object.hasOwn(TARGETS, platform)) {
    throw new TypeError('Plataforma inválida. Use "linux" ou "windows".');
  }
  if (typeof sourceRoot !== 'string' || !sourceRoot
      || typeof destinationRoot !== 'string' || !destinationRoot) {
    throw new TypeError('A origem e o destino do runtime são obrigatórios.');
  }

  const source = path.resolve(sourceRoot);
  const destination = path.resolve(destinationRoot);
  if (source === destination
      || destination.startsWith(source + path.sep)
      || source.startsWith(destination + path.sep)) {
    throw new Error('A origem e o destino do runtime não podem estar contidos um no outro.');
  }
  const existingDestinationStat = lstatIfPresent(destination);
  if (existingDestinationStat
      && (existingDestinationStat.isSymbolicLink() || !existingDestinationStat.isDirectory())) {
    throw new Error('Destino do runtime não é uma pasta segura: ' + destination);
  }

  const target = TARGETS[platform];
  const files = inspectRuntimeTree(source, target.executable, platform);
  const parentDirectory = path.dirname(destination);
  fs.mkdirSync(parentDirectory, { recursive: true });
  const staging = path.join(parentDirectory, '.runtime-staging-' + process.pid + '-' + Date.now());
  const backup = path.join(parentDirectory, '.runtime-backup-' + process.pid + '-' + Date.now());
  fs.mkdirSync(staging, { recursive: false });

  try {
    for (const file of files) {
      const destinationPath = path.join(staging, ...file.relativePath.split('/'));
      fs.mkdirSync(path.dirname(destinationPath), { recursive: true });
      fs.copyFileSync(file.sourcePath, destinationPath, fs.constants.COPYFILE_EXCL);
      fs.chmodSync(destinationPath, file.mode);
    }

    // Fingerprint every staged file, not just the executable, so a data-only
    // runtime update also refreshes the launcher's writable copy.
    const manifestHash = crypto.createHash('sha256');
    for (const file of files) {
      manifestHash.update(file.relativePath + '\0' + hashFile(path.join(staging, ...file.relativePath.split('/'))) + '\n');
    }
    const buildId = manifestHash.digest('hex');
    fs.writeFileSync(path.join(staging, 'launcher-runtime-version.txt'), buildId + '\n', {
      encoding: 'utf8',
      flag: 'wx'
    });

    requireRealDirectory(staging, 'Runtime preparado');
    for (const relativePath of REQUIRED_RUNTIME_FILES) {
      const stagedPath = path.join(staging, ...relativePath.split('/'));
      const stat = fs.lstatSync(stagedPath);
      if (!stat.isFile() || stat.isSymbolicLink() || stat.size === 0) {
        throw new Error('Validação pós-cópia falhou para: ' + relativePath);
      }
    }
    const executablePath = path.join(staging, target.executable);
    const executableStat = fs.lstatSync(executablePath);
    if (!executableStat.isFile() || executableStat.isSymbolicLink()) {
      throw new Error('O executável nativo copiado não é um arquivo regular.');
    }
    if (platform === 'linux' && (executableStat.mode & 0o111) === 0) {
      throw new Error('O executável Linux perdeu a permissão de execução durante a cópia.');
    }

    let movedDestination = false;
    if (lstatIfPresent(destination)) {
      fs.renameSync(destination, backup);
      movedDestination = true;
    }
    try {
      fs.renameSync(staging, destination);
    } catch (error) {
      if (movedDestination && lstatIfPresent(backup) && !lstatIfPresent(destination)) {
        fs.renameSync(backup, destination);
      }
      throw error;
    }
    if (movedDestination) {
      // Installation already succeeded. A stale backup cleanup error should
      // not make a valid newly staged runtime look like a failed build.
      try { fs.rmSync(backup, { recursive: true, force: true }); } catch {}
    }
    return {
      platform,
      files: files.length,
      buildId,
      executable: path.join(destination, target.executable),
      destination
    };
  } catch (error) {
    try { fs.rmSync(staging, { recursive: true, force: true }); } catch {}
    if (lstatIfPresent(backup) && !lstatIfPresent(destination)) {
      try { fs.renameSync(backup, destination); } catch {}
    }
    throw error;
  }
}

if (require.main === module) {
  const platform = process.argv[2];
  if (!Object.hasOwn(TARGETS, platform)) {
    process.stderr.write('Uso: node scripts/stage-native-runtime.cjs <linux|windows>\n');
    process.exitCode = 2;
  } else {
    const repositoryRoot = path.resolve(__dirname, '..', '..');
    const target = TARGETS[platform];
    const sourceRoot = path.join(
      repositoryRoot,
      'vendor',
      'pokeplatinum-native',
      target.buildDirectory,
      'pokeplatinum'
    );
    const destinationRoot = path.join(repositoryRoot, 'launcher-app', 'runtime');
    try {
      const result = stageNativeRuntime({ sourceRoot, destinationRoot, platform });
      process.stdout.write(
        'Runtime ' + result.platform + ' preparado com ' + result.files
        + ' arquivos; fingerprint=' + result.buildId + '\n'
        + 'Destino: ' + result.destination + '\n'
      );
    } catch (error) {
      process.stderr.write('Falha ao preparar runtime: ' + error.message + '\n');
      process.exitCode = 1;
    }
  }
}

module.exports = { stageNativeRuntime, inspectRuntimeTree, TARGETS, REQUIRED_RUNTIME_FILES };
