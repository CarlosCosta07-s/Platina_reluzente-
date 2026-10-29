'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const PERSONAL_FILES = new Set([
  'save.bin',
  'sim_config.ini',
  'launcher-runtime-version.txt',
  'launcher-runtime-manifest.json',
  'platinum-data-paths.txt'
]);

// Never package a local ROM, save dump, or patch by accident.
const FORBIDDEN_EXTENSIONS = new Set([
  '.nds', '.3ds', '.cia', '.cci', '.iso', '.gba', '.gbc', '.gb',
  '.n64', '.z64', '.v64', '.gcm', '.wbfs', '.dsv', '.sav',
  '.xdelta', '.ips', '.bps', '.zip', '.rar', '.7z'
]);

const TARGETS = Object.freeze({
  // The AppImage bundles the Linux executable and its shared libraries. It is
  // renamed to "main" in the launcher's writable runtime so assets can be
  // extracted from the imported ROM into the current working directory.
  linux: Object.freeze({ buildDirectory: 'build_linux', executable: 'main', sourceExecutable: 'pokeplatinum.AppImage' }),
  windows: Object.freeze({ buildDirectory: 'build_win64', executable: 'main.exe', sourceExecutable: 'main.exe' })
});

function requireRealDirectory(directory, label) {
  const stat = fs.lstatSync(directory);
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error(label + ' precisa ser uma pasta real, sem link simbólico: ' + directory);
  }
}

function inspectRuntimeTree(sourceRoot, expectedExecutable, platform) {
  requireRealDirectory(sourceRoot, 'Runtime de origem');
  const discoveredFiles = [];

  // Only inspect files that can enter the package. The upstream Linux build
  // also creates an AppDir containing intentional symlinks; we never package
  // that directory, only its self-contained AppImage file. On Windows, only
  // native executables and DLL dependencies are copied, never extracted data.
  function visitWindows(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const sourcePath = path.join(directory, entry.name);
      const stat = fs.lstatSync(sourcePath);
      const relativePath = path.relative(sourceRoot, sourcePath).split(path.sep).join('/');
      if (stat.isSymbolicLink()) {
        throw new Error('Runtime contém link simbólico; não será empacotado: ' + relativePath);
      }
      if (stat.isDirectory()) {
        visitWindows(sourcePath);
        continue;
      }
      if (!stat.isFile()) {
        throw new Error('Runtime contém uma entrada especial não suportada: ' + relativePath);
      }
      const extension = path.extname(entry.name).toLowerCase();
      if (FORBIDDEN_EXTENSIONS.has(extension)) {
        throw new Error('Arquivo ROM/save/patch proibido na pasta de runtime: ' + relativePath);
      }
      if (PERSONAL_FILES.has(entry.name.toLowerCase())) continue;
      if (extension === '.exe' || extension === '.dll') {
        discoveredFiles.push({ sourcePath, relativePath, mode: stat.mode & 0o777 });
      }
    }
  }

  let files;
  if (platform === 'linux') {
    const appImagePath = path.join(sourceRoot, 'pokeplatinum.AppImage');
    let stat;
    try {
      stat = fs.lstatSync(appImagePath);
    } catch (error) {
      if (error && error.code === 'ENOENT') {
        throw new Error('Executável nativo portátil Linux ausente: pokeplatinum.AppImage');
      }
      throw error;
    }
    if (stat.isSymbolicLink() || !stat.isFile()) {
      throw new Error('O AppImage Linux precisa ser um arquivo regular, não um link simbólico.');
    }
    if ((stat.mode & 0o111) === 0) {
      throw new Error('O AppImage Linux não possui permissão de execução.');
    }
    files = [{
      sourcePath: appImagePath,
      relativePath: expectedExecutable,
      mode: stat.mode & 0o777
    }];
  } else {
    visitWindows(sourceRoot);
    discoveredFiles.sort((a, b) => a.relativePath < b.relativePath ? -1 : a.relativePath > b.relativePath ? 1 : 0);
    const executable = discoveredFiles.find((file) => file.relativePath === expectedExecutable);
    if (!executable) {
      throw new Error('Executável nativo obrigatório ausente: ' + expectedExecutable);
    }
    files = discoveredFiles;
  }

  files.sort((a, b) => a.relativePath < b.relativePath ? -1 : a.relativePath > b.relativePath ? 1 : 0);
  const names = new Set(files.map((file) => file.relativePath));
  if (!names.has(expectedExecutable)) {
    throw new Error('Executável nativo obrigatório ausente: ' + expectedExecutable);
  }
  const executable = files.find((file) => file.relativePath === expectedExecutable);
  if (platform === 'linux' && (executable.mode & 0o111) === 0) {
    throw new Error('O executável Linux não possui permissão de execução: ' + expectedExecutable);
  }
  return files;
}

const GAME_DATA_PATHS_FILE = 'platinum-data-paths.txt';
const REQUIRED_EXTRACTED_PATHS = [
  'header.bin',
  'arm9.bin',
  'arm7.bin',
  'arm9ovt.bin',
  'arm7ovt.bin',
  'banner.bin',
  'fnt.bin',
  'fat.bin',
  'rsasig.bin',
  'wazaeffect/we.arc',
  'battle/skill/waza_seq.narc'
];

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (character === '"') {
      if (inQuotes && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (character === ',' && !inQuotes) {
      row.push(field);
      field = '';
    } else if ((character === '\n' || character === '\r') && !inQuotes) {
      if (character === '\r' && text[index + 1] === '\n') index += 1;
      row.push(field);
      field = '';
      if (row.some((value) => value.trim() !== '')) rows.push(row);
      row = [];
    } else {
      field += character;
    }
  }
  if (inQuotes) throw new Error('O filesys.csv contém aspas CSV sem fechamento.');
  if (field.length || row.length) {
    row.push(field);
    if (row.some((value) => value.trim() !== '')) rows.push(row);
  }
  return rows;
}

function normalizeManifestPath(value, label) {
  let normalized = String(value || '').trim();
  if (label === 'target' && normalized.startsWith('/') && !normalized.startsWith('//')) {
    normalized = normalized.slice(1);
  }
  if (!normalized || normalized.includes('\\') || normalized.includes('\0')
      || normalized.includes(':') || path.posix.isAbsolute(normalized)
      || normalized.split('/').some((part) => !part || part === '.' || part === '..')) {
    throw new Error('Caminho inseguro no filesys.csv (' + label + '): ' + JSON.stringify(value));
  }
  return normalized;
}

function createExtractedPathManifest(filesysCsvPath) {
  if (typeof filesysCsvPath !== 'string' || !path.isAbsolute(filesysCsvPath)) {
    throw new TypeError('O caminho absoluto de platinum.us/filesys.csv é obrigatório para o pacote de produção.');
  }
  const stat = fs.lstatSync(filesysCsvPath);
  if (stat.isSymbolicLink() || !stat.isFile()) {
    throw new Error('platinum.us/filesys.csv precisa ser um arquivo regular, não um link simbólico.');
  }
  const rows = parseCsv(fs.readFileSync(filesysCsvPath, 'utf8').replace(/^\uFEFF/, ''));
  const header = rows.shift();
  if (!header || header.length !== 2
      || header[0].trim() !== 'Source File' || header[1].trim() !== 'Target File') {
    throw new Error('Cabeçalho de platinum.us/filesys.csv inesperado.');
  }

  const targets = new Set(REQUIRED_EXTRACTED_PATHS);
  const seen = new Set();
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    if (row.length !== 2) {
      throw new Error('Linha ' + (index + 2) + ' de filesys.csv deveria conter duas colunas.');
    }
    normalizeManifestPath(row[0], 'source');
    const target = normalizeManifestPath(row[1], 'target');
    const key = target.toLowerCase();
    const reservedRootNames = new Set([
      'main', 'main.exe', 'save.bin', 'sim_config.ini', 'header.bin', 'firmware.bin',
      'launcher-runtime-version.txt', 'launcher-runtime-manifest.json',
      'platina-data-paths.txt', 'platina-rom-extraction.manifest'
    ]);
    if (!target.includes('/') && reservedRootNames.has(key)) {
      throw new Error('filesys.csv tenta sobrescrever um arquivo reservado do runtime: ' + target);
    }
    if (seen.has(key)) throw new Error('Destino duplicado em filesys.csv: ' + target);
    seen.add(key);
    targets.add(target);
  }

  // The pinned upstream revision currently maps 340 extracted assets. A much
  // smaller input usually means the manifest was truncated or the wrong file
  // was staged; fail the packaging step rather than ship a partial cache contract.
  if (seen.size < 300) {
    throw new Error('Manifesto de dados do jogo incompleto: ' + seen.size + ' destinos encontrados; esperado pelo menos 300.');
  }
  const paths = Array.from(targets).sort((a, b) => a < b ? -1 : a > b ? 1 : 0);
  return 'PLATINA_DATA_PATHS_V1\n' + paths.length + '\n' + paths.join('\n') + '\n';
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

function stageNativeRuntime({ sourceRoot, destinationRoot, platform, dataManifestPath }) {
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
  if (dataManifestPath !== undefined) {
    const normalizedManifestPath = path.resolve(dataManifestPath);
    if (files.some((file) => file.relativePath === GAME_DATA_PATHS_FILE)) {
      throw new Error('O pacote de origem contém um nome reservado: ' + GAME_DATA_PATHS_FILE);
    }
    files.push({
      sourcePath: null,
      relativePath: GAME_DATA_PATHS_FILE,
      mode: 0o644,
      generatedContents: createExtractedPathManifest(normalizedManifestPath)
    });
    files.sort((a, b) => a.relativePath < b.relativePath ? -1 : a.relativePath > b.relativePath ? 1 : 0);
  }
  const parentDirectory = path.dirname(destination);
  fs.mkdirSync(parentDirectory, { recursive: true });
  const staging = path.join(parentDirectory, '.runtime-staging-' + process.pid + '-' + Date.now());
  const backup = path.join(parentDirectory, '.runtime-backup-' + process.pid + '-' + Date.now());
  fs.mkdirSync(staging, { recursive: false });

  try {
    for (const file of files) {
      const destinationPath = path.join(staging, ...file.relativePath.split('/'));
      fs.mkdirSync(path.dirname(destinationPath), { recursive: true });
      if (typeof file.generatedContents === 'string') {
        fs.writeFileSync(destinationPath, file.generatedContents, { encoding: 'utf8', flag: 'wx', mode: file.mode });
      } else {
        fs.copyFileSync(file.sourcePath, destinationPath, fs.constants.COPYFILE_EXCL);
        fs.chmodSync(destinationPath, file.mode);
      }
    }

    // Record a content hash for every packaged binary and library. The
    // writable copy verifies these entries again before any game is launched.
    const manifestFiles = files.map((file) => {
      const stagedPath = path.join(staging, ...file.relativePath.split('/'));
      const stat = fs.lstatSync(stagedPath);
      if (stat.isSymbolicLink() || !stat.isFile() || stat.size <= 0) {
        throw new Error('Arquivo nativo staged não é um arquivo regular não vazio: ' + file.relativePath);
      }
      return {
        path: file.relativePath,
        size: stat.size,
        sha256: hashFile(stagedPath)
      };
    });
    const manifestHash = crypto.createHash('sha256');
    for (const entry of manifestFiles) {
      manifestHash.update(entry.path + '\0' + entry.sha256 + '\n');
    }
    const buildId = manifestHash.digest('hex');
    fs.writeFileSync(path.join(staging, 'launcher-runtime-manifest.json'), JSON.stringify({
      schemaVersion: 1,
      platform,
      buildId,
      files: manifestFiles
    }, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' });
    fs.writeFileSync(path.join(staging, 'launcher-runtime-version.txt'), buildId + '\n', {
      encoding: 'utf8',
      flag: 'wx'
    });

    requireRealDirectory(staging, 'Runtime preparado');
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
    const dataManifestPath = path.resolve(sourceRoot, '..', '..', 'platinum.us', 'filesys.csv');
    try {
      const result = stageNativeRuntime({ sourceRoot, destinationRoot, platform, dataManifestPath });
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

module.exports = { stageNativeRuntime, inspectRuntimeTree, createExtractedPathManifest, parseCsv, TARGETS };
