'use strict';

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { createReadStream } = require('node:fs');

const BLACK_ROM_SIZE = 268435456;
const BLACK_ROM_SHA1 = '26ad0b9967aa279c4a266ee69f52b9b2332399a5';

function blackPaths({ platform = process.platform, env = process.env, home = os.homedir() } = {}) {
  let root;
  if (platform === 'win32') {
    const localAppData = env.LOCALAPPDATA && path.isAbsolute(env.LOCALAPPDATA)
      ? env.LOCALAPPDATA
      : path.join(home, 'AppData', 'Local');
    root = path.join(localAppData, 'Platina-Reluzente', 'PokemonBlack');
  } else {
    const xdgData = env.XDG_DATA_HOME && path.isAbsolute(env.XDG_DATA_HOME)
      ? env.XDG_DATA_HOME
      : path.join(home, '.local', 'share');
    root = path.join(xdgData, 'platina-reluzente', 'pokemon-black');
  }

  const romDir = path.join(root, 'roms');
  const logsDir = path.join(root, 'logs');
  return {
    root,
    romDir,
    romPath: path.join(romDir, 'current.nds'),
    romMetadataPath: path.join(root, 'rom-import.json'),
    eidosHome: path.join(root, 'eidos-home'),
    extractDir: path.join(root, 'extract'),
    processAppData: path.join(root, 'process-appdata'),
    processXdgDataHome: path.join(root, 'process-data'),
    logsDir,
    logPath: path.join(logsDir, 'native-startup.log')
  };
}

async function ensureBlackDirectories(paths) {
  const directories = [
    paths.root, paths.romDir, paths.eidosHome, paths.extractDir,
    paths.processAppData, paths.processXdgDataHome, paths.logsDir
  ];
  await Promise.all(directories.map((directory) => fs.promises.mkdir(directory, { recursive: true })));
}

function validateBlackRomIdentity(size, sha1) {
  return size === BLACK_ROM_SIZE
    && typeof sha1 === 'string'
    && sha1.toLowerCase() === BLACK_ROM_SHA1;
}

function isBlackImportedMetadataValid(metadata, fileSize) {
  return Boolean(metadata)
    && Number.isSafeInteger(fileSize)
    && fileSize === BLACK_ROM_SIZE
    && metadata.size === BLACK_ROM_SIZE
    && typeof metadata.sha1 === 'string'
    && metadata.sha1.toLowerCase() === BLACK_ROM_SHA1
    && typeof metadata.sha256 === 'string'
    && /^[a-f0-9]{64}$/i.test(metadata.sha256);
}

function digestFile(filePath, algorithm) {
  return new Promise((resolve, reject) => {
    const digest = crypto.createHash(algorithm);
    const stream = createReadStream(filePath);
    stream.on('data', (chunk) => digest.update(chunk));
    stream.once('error', reject);
    stream.once('end', () => resolve(digest.digest('hex')));
  });
}

async function inspectBlackRom(sourcePath) {
  if (typeof sourcePath !== 'string' || !path.isAbsolute(sourcePath)) {
    throw new Error('Selecione um caminho absoluto para a ROM de Pokémon Black.');
  }
  if (path.extname(sourcePath).toLowerCase() !== '.nds') {
    throw new Error('A ROM de Pokémon Black precisa ter a extensão .nds.');
  }

  const stat = await fs.promises.lstat(sourcePath);
  if (stat.isSymbolicLink() || !stat.isFile()) {
    throw new Error('A ROM selecionada precisa ser um arquivo regular, não um link simbólico.');
  }
  if (stat.size !== BLACK_ROM_SIZE) {
    throw new Error('Tamanho inesperado para Pokémon Black USA/Europe NDSi Enhanced. A imagem suportada tem 268435456 bytes.');
  }

  const file = await fs.promises.open(sourcePath, 'r');
  const header = Buffer.alloc(0x200);
  let offset = 0;
  try {
    while (offset < header.length) {
      const { bytesRead } = await file.read(header, offset, header.length - offset, offset);
      if (bytesRead === 0) break;
      offset += bytesRead;
    }
  } finally {
    await file.close();
  }
  if (offset !== header.length) {
    throw new Error('Não foi possível ler o cabeçalho completo da ROM de Pokémon Black.');
  }

  const title = header.subarray(0, 12).toString('ascii').replace(/\0/g, '').trim();
  const gameCode = header.subarray(0x0c, 0x10).toString('ascii');
  const hasNintendoLogoCrc = header[0x15c] === 0x56 && header[0x15d] === 0xcf;
  if (!title || !/^[A-Z0-9]{4}$/.test(gameCode) || !hasNintendoLogoCrc) {
    throw new Error('O cabeçalho não é uma imagem Nintendo DS válida.');
  }

  const sha1 = await digestFile(sourcePath, 'sha1');
  if (!validateBlackRomIdentity(stat.size, sha1)) {
    throw new Error(
      'A imagem não corresponde ao dump Pokémon Black USA/Europe NDSi Enhanced suportado. ' +
      'SHA-1 esperado: ' + BLACK_ROM_SHA1 + '; recebido: ' + sha1 + '. Nenhum arquivo foi instalado.'
    );
  }
  return { size: stat.size, sha1, title, gameCode };
}

async function inspectBlackRuntime(runtimeDirectory, platform = process.platform) {
  if (typeof runtimeDirectory !== 'string' || !path.isAbsolute(runtimeDirectory)) {
    throw new Error('Selecione a pasta absoluta do build local Eidos.');
  }
  const directory = path.resolve(runtimeDirectory);
  const rootStat = await fs.promises.lstat(directory);
  if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) {
    throw new Error('A pasta do runtime Eidos precisa ser um diretório real, não um link simbólico.');
  }

  // Eidos portable mode writes saves beside its executable before consulting APPDATA.
  // Refuse it so the launcher's per-game save root cannot be bypassed.
  let portableMode = false;
  try {
    await fs.promises.lstat(path.join(directory, 'portable.txt'));
    portableMode = true;
  } catch (error) {
    if (!error || error.code !== 'ENOENT') throw error;
  }
  if (portableMode) {
    throw new Error('O runtime Eidos contém portable.txt; remova esse marcador para manter os saves do Black isolados.');
  }

  const executableName = platform === 'win32' ? 'eidos.exe' : 'eidos';
  const executable = path.join(directory, executableName);
  const executableStat = await fs.promises.lstat(executable);
  if (executableStat.isSymbolicLink() || !executableStat.isFile() || executableStat.size === 0) {
    throw new Error('O diretório selecionado não contém o executável local esperado (' + executableName + ').');
  }
  if (platform !== 'win32') {
    await fs.promises.access(executable, fs.constants.X_OK);
  } else {
    const sdlPath = path.join(directory, 'SDL3.dll');
    const sdlStat = await fs.promises.lstat(sdlPath);
    if (sdlStat.isSymbolicLink() || !sdlStat.isFile() || sdlStat.size === 0) {
      throw new Error('O runtime Windows precisa conter SDL3.dll junto de eidos.exe.');
    }
  }
  return {
    directory,
    executable,
    executableName,
    executableSize: executableStat.size,
    executableMtimeMs: executableStat.mtimeMs
  };
}

function createBlackLaunchSpec({ runtime, paths, romPath, romSha256, platform = process.platform, env = process.env }) {
  if (!runtime || typeof runtime.executable !== 'string' || !path.isAbsolute(runtime.executable)
      || typeof runtime.directory !== 'string' || !path.isAbsolute(runtime.directory)) {
    throw new TypeError('O runtime Eidos deve ser validado antes da inicialização.');
  }
  if (!paths || !path.isAbsolute(paths.eidosHome) || !path.isAbsolute(paths.extractDir)
      || !path.isAbsolute(paths.processAppData) || !path.isAbsolute(paths.processXdgDataHome)
      || !path.isAbsolute(paths.logPath) || !path.isAbsolute(romPath)) {
    throw new TypeError('Os diretórios e o caminho da ROM Black devem ser absolutos.');
  }
  const childEnv = { ...env, EIDOS_HOME: paths.eidosHome };
  if (platform === 'win32') {
    childEnv.APPDATA = paths.processAppData;
  } else {
    childEnv.XDG_DATA_HOME = paths.processXdgDataHome;

    // Eidos may link against SDL3 or other pinned shared libraries outside the
    // system library directories. Search the runtime's own folder first, then
    // preserve the caller's loader path so staged native dependencies resolve
    // on Linux without relying on the build machine's absolute RPATH.
    const inheritedLibraryPath = typeof env.LD_LIBRARY_PATH === 'string'
      ? env.LD_LIBRARY_PATH.split(':').filter(Boolean)
      : [];
    childEnv.LD_LIBRARY_PATH = Array.from(new Set([
      runtime.directory,
      ...inheritedLibraryPath
    ])).join(':');
  }
  return {
    executable: runtime.executable,
    args: ['--rom', romPath, '--data-root', paths.extractDir],
    cwd: runtime.directory,
    env: childEnv,
    logPath: paths.logPath,
    romSha256: romSha256 || 'unavailable'
  };
}

module.exports = {
  BLACK_ROM_SIZE,
  BLACK_ROM_SHA1,
  blackPaths,
  ensureBlackDirectories,
  validateBlackRomIdentity,
  isBlackImportedMetadataValid,
  inspectBlackRom,
  inspectBlackRuntime,
  createBlackLaunchSpec
};
