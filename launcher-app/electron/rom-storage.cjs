'use strict';

const fs = require('node:fs/promises');
const crypto = require('node:crypto');
const path = require('node:path');
const { createReadStream } = require('node:fs');

function isMissingPathError(error) {
  return Boolean(error && (error.code === 'ENOENT' || error.code === 'ENOTDIR'));
}

async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch (error) {
    // Only absence should be treated as false. Permission and storage failures
    // must interrupt recovery instead of making a backup look nonexistent.
    if (isMissingPathError(error)) return false;
    throw error;
  }
}

async function removeIfPresent(filePath) {
  await fs.rm(filePath, { force: true });
}

async function cleanupBestEffort(paths) {
  // Cleanup must never turn an already-committed ROM into a reported import failure.
  await Promise.allSettled(paths.map((filePath) => removeIfPresent(filePath)));
}

function hashFileDigests(filePath, algorithms) {
  return new Promise((resolve, reject) => {
    const hashes = Object.fromEntries(algorithms.map((algorithm) => [
      algorithm, crypto.createHash(algorithm)
    ]));
    const stream = createReadStream(filePath);
    stream.on('data', (chunk) => {
      for (const hash of Object.values(hashes)) hash.update(chunk);
    });
    stream.once('error', reject);
    stream.once('end', () => {
      resolve(Object.fromEntries(Object.entries(hashes).map(([name, hash]) => [
        name, hash.digest('hex')
      ])));
    });
  });
}

function hashFile(filePath, algorithm) {
  return hashFileDigests(filePath, [algorithm]).then((digests) => digests[algorithm]);
}

function sha256File(filePath) {
  return hashFile(filePath, 'sha256');
}

function sha1File(filePath) {
  return hashFile(filePath, 'sha1');
}

async function matchesMetadata(romPath, metadataPath, expectedSha1) {
  let metadataText;
  let stat;
  let metadataStat;
  try {
    [metadataText, stat, metadataStat] = await Promise.all([
      fs.readFile(metadataPath, 'utf8'),
      fs.lstat(romPath),
      fs.lstat(metadataPath)
    ]);
  } catch (error) {
    if (isMissingPathError(error)) return false;
    throw error;
  }

  if (stat.isSymbolicLink() || !stat.isFile()
      || metadataStat.isSymbolicLink() || !metadataStat.isFile()) return false;

  let metadata;
  try {
    metadata = JSON.parse(metadataText);
  } catch {
    return false;
  }
  if (!Number.isSafeInteger(metadata.size) || stat.size !== metadata.size) return false;
  if (typeof metadata.sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(metadata.sha256)) {
    return false;
  }
  if (expectedSha1 !== undefined
      && (typeof metadata.sha1 !== 'string'
        || metadata.sha1.toLowerCase() !== expectedSha1.toLowerCase())) {
    return false;
  }

  try {
    const digests = await hashFileDigests(
      romPath,
      expectedSha1 === undefined ? ['sha256'] : ['sha256', 'sha1']
    );
    if (digests.sha256 !== metadata.sha256.toLowerCase()) return false;
    if (expectedSha1 !== undefined
        && digests.sha1 !== expectedSha1.toLowerCase()) return false;
    return true;
  } catch (error) {
    if (isMissingPathError(error)) return false;
    throw error;
  }
}

/**
 * Repair an interrupted ROM + metadata replacement, if enough information
 * remains to prove which pair is valid. Ambiguous files are preserved and
 * reported instead of silently deleting a possible last-good ROM.
 */
async function recoverDesktopRom({ destinationPath, metadataPath, expectedSha1 }) {
  if (expectedSha1 !== undefined
      && (typeof expectedSha1 !== 'string' || !/^[a-f0-9]{40}$/i.test(expectedSha1))) {
    throw new TypeError('O SHA-1 esperado para recuperação deve conter exatamente 40 dígitos hexadecimais.');
  }
  const romBackup = destinationPath + '.previous';
  const romStaging = destinationPath + '.importing';
  const metadataBackup = metadataPath + '.previous';
  const metadataStaging = metadataPath + '.importing';
  const [hasRom, hasMetadata, hasRomBackup, hasMetadataBackup, hasRomStaging, hasMetadataStaging] =
    await Promise.all([
      exists(destinationPath), exists(metadataPath), exists(romBackup), exists(metadataBackup),
      exists(romStaging), exists(metadataStaging)
    ]);

  if (hasRom && hasMetadata && await matchesMetadata(destinationPath, metadataPath, expectedSha1)) {
    await cleanupBestEffort([
      romBackup, metadataBackup, romStaging, metadataStaging
    ]);
    return;
  }

  // No transaction residue remains, but there is no SHA-256-verified ROM pair
  // to expose. Preserve any files so a later explicit import can replace them
  // after verifying its staged source.
  if (![hasRomBackup, hasMetadataBackup, hasRomStaging, hasMetadataStaging].some(Boolean)) {
    return false;
  }

  // First-import crash after the ROM rename but before the metadata rename.
  // The temporary metadata carries the expected SHA-256, so recover only if
  // it proves that the installed ROM is exactly the staged version.
  if (hasRom && !hasMetadata && !hasRomBackup && !hasMetadataBackup
      && hasMetadataStaging && await matchesMetadata(destinationPath, metadataStaging, expectedSha1)) {
    await fs.rename(metadataStaging, metadataPath);
    await cleanupBestEffort([romStaging, romBackup, metadataBackup]);
    return;
  }

  // First-import crash before the first rename: if both staging files match,
  // finish the commit. Otherwise no committed ROM exists, so stale staging
  // files can be discarded without touching a last-good destination.
  if (!hasRom && !hasMetadata && !hasRomBackup && !hasMetadataBackup) {
    if (hasRomStaging && hasMetadataStaging
        && await matchesMetadata(romStaging, metadataStaging, expectedSha1)) {
      await fs.rename(romStaging, destinationPath);
      await fs.rename(metadataStaging, metadataPath);
      await cleanupBestEffort([romBackup, metadataBackup]);
      return;
    }
    await cleanupBestEffort([romStaging, metadataStaging]);
    return;
  }

  if (hasRomBackup && hasMetadataBackup && await matchesMetadata(romBackup, metadataBackup, expectedSha1)) {
    await removeIfPresent(destinationPath);
    await removeIfPresent(metadataPath);
    await fs.rename(romBackup, destinationPath);
    await fs.rename(metadataBackup, metadataPath);
    await cleanupBestEffort([romStaging, metadataStaging]);
    return;
  }

  if (!hasRom && hasRomBackup && hasMetadata && await matchesMetadata(romBackup, metadataPath, expectedSha1)) {
    await fs.rename(romBackup, destinationPath);
    await cleanupBestEffort([metadataBackup, romStaging, metadataStaging]);
    return;
  }

  if (hasRom && !hasMetadata && hasMetadataBackup && await matchesMetadata(destinationPath, metadataBackup, expectedSha1)) {
    await fs.rename(metadataBackup, metadataPath);
    await cleanupBestEffort([romBackup, romStaging, metadataStaging]);
    return;
  }

  throw new Error(
    'A importação anterior da ROM foi interrompida e não foi possível identificar com segurança a cópia válida. ' +
    'Os arquivos temporários e backups foram preservados.'
  );
}

async function commitDesktopRom({ sourcePath, destinationPath, metadataPath, metadata, expectedSha1 }) {
  if (!sourcePath || !destinationPath || !metadataPath || !metadata || typeof metadata.name !== 'string') {
    throw new TypeError('Origem, destino, metadados e nome da ROM são obrigatórios.');
  }
  if (expectedSha1 !== undefined
      && (typeof expectedSha1 !== 'string' || !/^[a-f0-9]{40}$/i.test(expectedSha1))) {
    throw new TypeError('O SHA-1 esperado deve conter exatamente 40 dígitos hexadecimais.');
  }

  const romDirectory = path.dirname(destinationPath);
  await fs.mkdir(romDirectory, { recursive: true });
  await fs.mkdir(path.dirname(metadataPath), { recursive: true });
  await recoverDesktopRom({ destinationPath, metadataPath, expectedSha1 });

  const romStaging = destinationPath + '.importing';
  const romBackup = destinationPath + '.previous';
  const metadataStaging = metadataPath + '.importing';
  const metadataBackup = metadataPath + '.previous';

  await Promise.all([removeIfPresent(romStaging), removeIfPresent(metadataStaging)]);
  try {
    const sourceStat = await fs.stat(sourcePath);
    if (!sourceStat.isFile()) throw new Error('A origem selecionada não é um arquivo.');
    if (Number.isSafeInteger(metadata.size) && sourceStat.size !== metadata.size) {
      throw new Error('O tamanho da ROM mudou durante a importação; tente novamente.');
    }

    await fs.copyFile(sourcePath, romStaging);
    const [stagedStat, sourceHash, stagedHash, stagedSha1] = await Promise.all([
      fs.stat(romStaging),
      sha256File(sourcePath),
      sha256File(romStaging),
      expectedSha1 !== undefined ? hashFile(romStaging, 'sha1') : Promise.resolve(null)
    ]);
    if (!stagedStat.isFile() || stagedStat.size !== sourceStat.size || sourceHash !== stagedHash) {
      throw new Error('A cópia temporária da ROM não corresponde ao arquivo de origem.');
    }
    if (expectedSha1 !== undefined && stagedSha1 !== expectedSha1.toLowerCase()) {
      throw new Error(
        'A imagem não corresponde à ROM original esperada. SHA-1 esperado: '
        + expectedSha1.toLowerCase() + '; recebido: ' + stagedSha1
        + '. Nenhuma ROM foi instalada.'
      );
    }

    const committedMetadata = {
      ...metadata,
      size: stagedStat.size,
      sha256: stagedHash,
      ...(stagedSha1 ? { sha1: stagedSha1 } : {}),
      storedName: path.basename(destinationPath)
    };
    await fs.writeFile(metadataStaging, JSON.stringify(committedMetadata, null, 2), 'utf8');

    const hadRom = await exists(destinationPath);
    const hadMetadata = await exists(metadataPath);
    let romBackedUp = false;
    let metadataBackedUp = false;
    let romInstalled = false;
    let metadataInstalled = false;

    try {
      if (hadRom) {
        await fs.rename(destinationPath, romBackup);
        romBackedUp = true;
      }
      if (hadMetadata) {
        await fs.rename(metadataPath, metadataBackup);
        metadataBackedUp = true;
      }
      await fs.rename(romStaging, destinationPath);
      romInstalled = true;
      await fs.rename(metadataStaging, metadataPath);
      metadataInstalled = true;
    } catch (installError) {
      const restoreErrors = [];
      if (metadataInstalled) {
        try { await removeIfPresent(metadataPath); } catch (error) { restoreErrors.push(error); }
      }
      if (romInstalled) {
        try { await removeIfPresent(destinationPath); } catch (error) { restoreErrors.push(error); }
      }
      if (metadataBackedUp) {
        try { await fs.rename(metadataBackup, metadataPath); } catch (error) { restoreErrors.push(error); }
      }
      if (romBackedUp) {
        try { await fs.rename(romBackup, destinationPath); } catch (error) { restoreErrors.push(error); }
      }
      if (restoreErrors.length) {
        throw new Error(
          'A instalação falhou e a restauração automática não terminou. ' +
          'Os backups restantes foram preservados para recuperação.',
          { cause: installError }
        );
      }
      throw installError;
    }

    // The new ROM and its metadata are both committed. Cleanup failures are non-fatal:
    // recovery checks the pair's SHA-256 and can safely remove stale backups later.
    await cleanupBestEffort([romBackup, metadataBackup]);
    return committedMetadata;
  } catch (error) {
    try {
      await cleanupBestEffort([romStaging, metadataStaging]);
    } catch {
      // Keep the original import failure; recovery will handle any staged files.
    }
    throw error;
  }
}

module.exports = { commitDesktopRom, recoverDesktopRom, sha256File, sha1File };
