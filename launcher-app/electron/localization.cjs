'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const LOCALIZATION_MANIFEST_FILE = 'localization-manifest.json';
const PTBR_BASE_ROM_SHA1 = '0862ec35b24de5c7e2dcb88c9eea0873110d755c';
const PTBR_SOURCE_ROM_SHA1 = '3d92f853eda6e70e9272809f01277db5fdb870ab';
const PTBR_RESOURCE_SHA256 = Object.freeze({
  'battle/graphic/pl_b_plist_gra.narc': 'bec3dbd9fd6493ec5c41e3907e6834ed548a0ba07d5243b2fc41b806f2c58cca',
  'data/slot.narc': '72fdd57fa2768e51880d13152d3877865bf574cd50436e056f3879eb734bbf41',
  'demo/title/op_demo.narc': 'ac6ba2bc74088fe27fdf37fdf27cf003d4453c423726cc913f5178c0b265ec52',
  'graphic/pl_bag_gra.narc': '0335b99b6341d5f4ec5ad077edb82424341346a79216601ca95230424d230cac',
  'graphic/pl_plist_gra.narc': 'ba7a1847c39dfc5972c4c0282dd2eacc67a0dfed38852dc8dff8b948ed21249b',
  'graphic/pl_pst_gra.narc': 'ab73a6b8984ace09419a2bb06efefa4419fc5a21c4c784224eaf7d2e623d2ab1',
  'msgdata/pl_msg.narc': 'a7206407d80ca5cff28ceeee9008beef72efa9ab4a3bbe9fafcbbbad9a8e0f77'
});

const DEFAULT_POLICY = Object.freeze({
  game: 'pokemon-platinum',
  locale: 'pt-BR',
  baseRomSha1: PTBR_BASE_ROM_SHA1,
  sourceRomSha1: PTBR_SOURCE_ROM_SHA1,
  resources: PTBR_RESOURCE_SHA256
});

function lstatRequired(filePath, label, expectedType) {
  const stat = fs.lstatSync(filePath);
  if (stat.isSymbolicLink()) throw new Error('Link simbólico não permitido: ' + label);
  if (expectedType === 'directory' && !stat.isDirectory()) {
    throw new Error('Diretório esperado: ' + label);
  }
  if (expectedType === 'file' && !stat.isFile()) {
    throw new Error('Arquivo regular esperado: ' + label);
  }
  return stat;
}

function safePackageFile(root, relativePath) {
  if (typeof relativePath !== 'string' || !relativePath
      || relativePath.includes('\\') || path.posix.isAbsolute(relativePath)
      || relativePath.split('/').some((part) => !part || part === '.' || part === '..')) {
    throw new Error('Caminho inseguro no pacote PT-BR: ' + String(relativePath));
  }
  const components = relativePath.split('/');
  let current = root;
  for (let index = 0; index < components.length; index += 1) {
    current = path.join(current, components[index]);
    lstatRequired(
      current,
      relativePath,
      index === components.length - 1 ? 'file' : 'directory'
    );
  }
  return current;
}

async function sha256File(filePath) {
  const hash = crypto.createHash('sha256');
  const input = fs.createReadStream(filePath);
  for await (const chunk of input) hash.update(chunk);
  return hash.digest('hex');
}

function collectPackageTree(root) {
  const files = new Set();
  const directories = new Set();

  function visit(directory, relativeDirectory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const childPath = path.join(directory, entry.name);
      const relativePath = relativeDirectory
        ? relativeDirectory + '/' + entry.name
        : entry.name;
      const stat = lstatRequired(childPath, relativePath);
      if (stat.isDirectory()) {
        directories.add(relativePath);
        visit(childPath, relativePath);
      } else if (stat.isFile()) {
        files.add(relativePath);
      } else {
        throw new Error('Entrada especial não permitida no pacote PT-BR: ' + relativePath);
      }
    }
  }

  visit(root, '');
  return { files, directories };
}

function assertSameSet(actual, expected, label) {
  if (actual.size !== expected.size) {
    throw new Error('A estrutura do pacote PT-BR contém arquivos ou diretórios inesperados: ' + label);
  }
  for (const value of expected) {
    if (!actual.has(value)) {
      throw new Error('Item ausente no pacote PT-BR: ' + value);
    }
  }
}

async function verifyLocalizationPackage(packageRoot, policy = DEFAULT_POLICY) {
  if (!policy || !policy.resources || typeof policy.resources !== 'object') {
    throw new TypeError('Política de localização inválida.');
  }
  const root = path.resolve(packageRoot);
  lstatRequired(root, root, 'directory');

  const manifestPath = safePackageFile(root, LOCALIZATION_MANIFEST_FILE);
  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  } catch (error) {
    throw new Error('Manifesto do pacote PT-BR ausente ou inválido: ' + error.message);
  }
  const manifestKeys = [
    'schemaVersion', 'game', 'locale', 'baseRomSha1',
    'sourceRomSha1', 'resourceCount', 'resources'
  ];
  if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)
      || Object.keys(manifest).sort().join('|') !== manifestKeys.slice().sort().join('|')
      || manifest.schemaVersion !== 1
      || manifest.game !== policy.game
      || manifest.locale !== policy.locale
      || manifest.baseRomSha1 !== policy.baseRomSha1
      || manifest.sourceRomSha1 !== policy.sourceRomSha1) {
    throw new Error('Identidade ou compatibilidade do pacote PT-BR é inválida.');
  }

  const expectedPaths = Object.keys(policy.resources);
  if (!Array.isArray(manifest.resources)
      || manifest.resourceCount !== expectedPaths.length
      || manifest.resources.length !== expectedPaths.length) {
    throw new Error('A quantidade de recursos do pacote PT-BR é inválida.');
  }

  const expectedFiles = new Set([LOCALIZATION_MANIFEST_FILE]);
  const expectedDirectories = new Set();
  for (let index = 0; index < expectedPaths.length; index += 1) {
    const expectedPath = expectedPaths[index];
    const entry = manifest.resources[index];
    const entryKeys = ['path', 'sizeBytes', 'fatSizeBytes', 'sizeRecoveredFromNarcHeader', 'sha256'];
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)
        || Object.keys(entry).sort().join('|') !== entryKeys.slice().sort().join('|')
        || entry.path !== expectedPath
        || entry.sha256 !== policy.resources[expectedPath]
        || !Number.isSafeInteger(entry.sizeBytes) || entry.sizeBytes <= 0
        || !Number.isSafeInteger(entry.fatSizeBytes) || entry.fatSizeBytes < 0
        || typeof entry.sizeRecoveredFromNarcHeader !== 'boolean'
        || entry.sizeRecoveredFromNarcHeader !== (entry.sizeBytes !== entry.fatSizeBytes)) {
      throw new Error('Metadados ou hash de referência inválidos no pacote PT-BR: ' + expectedPath);
    }

    const resourcePath = safePackageFile(root, expectedPath);
    const stat = fs.statSync(resourcePath);
    if (stat.size !== entry.sizeBytes) {
      throw new Error('Tamanho divergente no pacote PT-BR: ' + expectedPath);
    }
    if (await sha256File(resourcePath) !== policy.resources[expectedPath]) {
      throw new Error('Conteúdo divergente no pacote PT-BR: ' + expectedPath);
    }
    expectedFiles.add(expectedPath);

    let parent = path.posix.dirname(expectedPath);
    while (parent !== '.') {
      expectedDirectories.add(parent);
      parent = path.posix.dirname(parent);
    }
  }

  const actualTree = collectPackageTree(root);
  assertSameSet(actualTree.files, expectedFiles, 'arquivos');
  assertSameSet(actualTree.directories, expectedDirectories, 'diretórios');
  return { root, manifest };
}

function assertDirectoryPathWithoutSymlinks(directoryPath) {
  const absolute = path.resolve(directoryPath);
  const parsed = path.parse(absolute);
  let current = parsed.root;
  for (const component of absolute.slice(parsed.root.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, component);
    try {
      lstatRequired(current, current, 'directory');
    } catch (error) {
      if (!error || error.code !== 'ENOENT') throw error;
      fs.mkdirSync(current);
      lstatRequired(current, current, 'directory');
    }
  }
  return absolute;
}

function pathExists(filePath) {
  try {
    fs.lstatSync(filePath);
    return true;
  } catch (error) {
    if (error && error.code === 'ENOENT') return false;
    throw error;
  }
}

async function installLocalizationPackage(sourceRoot, destinationRoot, policy = DEFAULT_POLICY) {
  const source = path.resolve(sourceRoot);
  const destination = path.resolve(destinationRoot);
  const destinationFromSource = path.relative(source, destination);
  const sourceFromDestination = path.relative(destination, source);
  const isWithin = (relativePath) => relativePath === ''
    || (relativePath !== '..' && !relativePath.startsWith('..' + path.sep)
        && !path.isAbsolute(relativePath));
  if (isWithin(destinationFromSource) || isWithin(sourceFromDestination)) {
    throw new Error('A origem e a pasta de instalação do pacote não podem se sobrepor.');
  }

  await verifyLocalizationPackage(source, policy);
  const parent = assertDirectoryPathWithoutSymlinks(path.dirname(destination));

  let existing = false;
  if (pathExists(destination)) {
    lstatRequired(destination, destination, 'directory');
    await verifyLocalizationPackage(destination, policy);
    existing = true;
  }

  const staging = fs.mkdtempSync(path.join(parent, '.pt-br-package-staging-'));
  const backup = destination + '.previous-' + crypto.randomBytes(8).toString('hex');
  let movedPrevious = false;
  let promotedStaging = false;
  try {
    const filesToCopy = [
      LOCALIZATION_MANIFEST_FILE,
      ...Object.keys(policy.resources)
    ];
    for (const relativePath of filesToCopy) {
      const sourcePath = safePackageFile(source, relativePath);
      const destinationPath = path.join(staging, ...relativePath.split('/'));
      fs.mkdirSync(path.dirname(destinationPath), { recursive: true });
      fs.copyFileSync(sourcePath, destinationPath, fs.constants.COPYFILE_EXCL);
    }

    await verifyLocalizationPackage(staging, policy);
    if (existing) {
      fs.renameSync(destination, backup);
      movedPrevious = true;
    }
    fs.renameSync(staging, destination);
    promotedStaging = true;
    await verifyLocalizationPackage(destination, policy);

    if (movedPrevious) {
      try { fs.rmSync(backup, { recursive: true, force: true }); } catch {}
      movedPrevious = false;
    }
    return await verifyLocalizationPackage(destination, policy);
  } catch (error) {
    if (promotedStaging && pathExists(destination)) {
      try { fs.rmSync(destination, { recursive: true, force: true }); } catch {}
    }
    if (movedPrevious && pathExists(backup)) {
      try { fs.renameSync(backup, destination); } catch (rollbackError) {
        throw new Error(error.message + ' A restauração do pacote anterior falhou; a cópia anterior foi preservada em: '
          + backup + '. ' + rollbackError.message);
      }
    }
    throw error;
  } finally {
    if (pathExists(staging)) {
      try { fs.rmSync(staging, { recursive: true, force: true }); } catch {}
    }
  }
}

function readLanguagePreference(filePath) {
  try {
    lstatRequired(filePath, filePath, 'file');
  } catch (error) {
    if (error && error.code === 'ENOENT') return 'en';
    throw error;
  }
  const value = fs.readFileSync(filePath, 'utf8').trim();
  if (value !== 'en' && value !== 'pt-BR') {
    throw new Error('A preferência de idioma de Pokémon Platinum é inválida.');
  }
  return value;
}

function writeLanguagePreference(filePath, language) {
  if (language !== 'en' && language !== 'pt-BR') {
    throw new TypeError('Idioma de Pokémon Platinum não suportado.');
  }
  const parent = assertDirectoryPathWithoutSymlinks(path.dirname(filePath));
  if (pathExists(filePath)) lstatRequired(filePath, filePath, 'file');

  const suffix = crypto.randomBytes(8).toString('hex');
  const staging = path.join(parent, '.platinum-language-' + suffix + '.tmp');
  const backup = path.join(parent, '.platinum-language-' + suffix + '.previous');
  let movedPrevious = false;
  try {
    fs.writeFileSync(staging, language + '\n', { encoding: 'utf8', flag: 'wx', mode: 0o600 });
    if (pathExists(filePath)) {
      fs.renameSync(filePath, backup);
      movedPrevious = true;
    }
    fs.renameSync(staging, filePath);
    if (movedPrevious) {
      fs.rmSync(backup, { force: true });
      movedPrevious = false;
    }
    return language;
  } catch (error) {
    if (pathExists(staging)) {
      try { fs.rmSync(staging, { force: true }); } catch {}
    }
    if (movedPrevious && pathExists(backup)) {
      try { fs.renameSync(backup, filePath); } catch (rollbackError) {
        throw new Error(error.message + ' A preferência anterior foi preservada em: ' + backup
          + '. ' + rollbackError.message);
      }
    }
    throw error;
  }
}

module.exports = {
  LOCALIZATION_MANIFEST_FILE,
  PTBR_BASE_ROM_SHA1,
  PTBR_SOURCE_ROM_SHA1,
  PTBR_RESOURCE_SHA256,
  verifyLocalizationPackage,
  installLocalizationPackage,
  readLanguagePreference,
  writeLanguagePreference
};
