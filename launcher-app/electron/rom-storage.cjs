'use strict';

const fs = require('node:fs/promises');
const crypto = require('node:crypto');
const path = require('node:path');
const { createReadStream } = require('node:fs');

async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch (error) {
    // Only absence should be treated as false. Permission and storage failures
    // must interrupt recovery instead of making a backup look nonexistent.
    if (error && (error.code === 'ENOENT' || error.code === 'ENOTDIR')) return false;
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

function sha256File(filePath) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash('sha256');
    const stream = createReadStream(filePath);
    stream.on('data', (chunk) => hash.update(chunk));
    stream.once('error', reject);
    stream.once('end', () => resolve(hash.digest('hex')));
  });
}

async function matchesMetadata(romPath, metadataPath) {
  try {
    const [metadataText, stat] = await Promise.all([
      fs.readFile(metadataPath, 'utf8'),
      fs.stat(romPath)
    ]);
    const metadata = JSON.parse(metadataText);
    if (!stat.isFile() || !Number.isSafeInteger(metadata.size) || stat.size !== metadata.size) {
      return false;
    }
    if (typeof metadata.sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(metadata.sha256)) {
      return false;
    }
    return (await sha256File(romPath)) === metadata.sha256.toLowerCase();
  } catch {
    return false;
  }
}

/**
 * Repair an interrupted ROM + metadata replacement, if enough information
 * remains to prove which pair is valid. Ambiguous files are preserved and
 * reported instead of silently deleting a possible last-good ROM.
 */
async function recoverDesktopRom({ destinationPath, metadataPath }) {
  const romBackup = destinationPath + '.previous';
  const romStaging = destinationPath + '.importing';
  const metadataBackup = metadataPath + '.previous';
  const metadataStaging = metadataPath + '.importing';
  const [hasRom, hasMetadata, hasRomBackup, hasMetadataBackup, hasRomStaging, hasMetadataStaging] =
    await Promise.all([
      exists(destinationPath), exists(metadataPath), exists(romBackup), exists(metadataBackup),
      exists(romStaging), exists(metadataStaging)
    ]);

  if (![hasRomBackup, hasMetadataBackup, hasRomStaging, hasMetadataStaging].some(Boolean)) return;

  if (hasRom && hasMetadata && await matchesMetadata(destinationPath, metadataPath)) {
    await cleanupBestEffort([
      romBackup, metadataBackup, romStaging, metadataStaging
    ]);
    return;
  }

  // First-import crash after the ROM rename but before the metadata rename.
  // The temporary metadata carries the expected SHA-256, so recover only if
  // it proves that the installed ROM is exactly the staged version.
  if (hasRom && !hasMetadata && !hasRomBackup && !hasMetadataBackup
      && hasMetadataStaging && await matchesMetadata(destinationPath, metadataStaging)) {
    await fs.rename(metadataStaging, metadataPath);
    await cleanupBestEffort([romStaging, romBackup, metadataBackup]);
    return;
  }

  // First-import crash before the first rename: if both staging files match,
  // finish the commit. Otherwise no committed ROM exists, so stale staging
  // files can be discarded without touching a last-good destination.
  if (!hasRom && !hasMetadata && !hasRomBackup && !hasMetadataBackup) {
    if (hasRomStaging && hasMetadataStaging
        && await matchesMetadata(romStaging, metadataStaging)) {
      await fs.rename(romStaging, destinationPath);
      await fs.rename(metadataStaging, metadataPath);
      await cleanupBestEffort([romBackup, metadataBackup]);
      return;
    }
    await cleanupBestEffort([romStaging, metadataStaging]);
    return;
  }

  if (hasRomBackup && hasMetadataBackup && await matchesMetadata(romBackup, metadataBackup)) {
    await removeIfPresent(destinationPath);
    await removeIfPresent(metadataPath);
    await fs.rename(romBackup, destinationPath);
    await fs.rename(metadataBackup, metadataPath);
    await cleanupBestEffort([romStaging, metadataStaging]);
    return;
  }

  if (!hasRom && hasRomBackup && hasMetadata && await matchesMetadata(romBackup, metadataPath)) {
    await fs.rename(romBackup, destinationPath);
    await Promise.all([removeIfPresent(metadataBackup), removeIfPresent(romStaging), removeIfPresent(metadataStaging)]);
    return;
  }

  if (hasRom && !hasMetadata && hasMetadataBackup && await matchesMetadata(destinationPath, metadataBackup)) {
    await fs.rename(metadataBackup, metadataPath);
    await Promise.all([removeIfPresent(romBackup), removeIfPresent(romStaging), removeIfPresent(metadataStaging)]);
    return;
  }

  throw new Error(
    'A importação anterior da ROM foi interrompida e não foi possível identificar com segurança a cópia válida. ' +
    'Os arquivos temporários e backups foram preservados.'
  );
}

async function commitDesktopRom({ sourcePath, destinationPath, metadataPath, metadata }) {
  if (!sourcePath || !destinationPath || !metadataPath || !metadata || typeof metadata.name !== 'string') {
    throw new TypeError('Origem, destino, metadados e nome da ROM são obrigatórios.');
  }

  const romDirectory = path.dirname(destinationPath);
  await fs.mkdir(romDirectory, { recursive: true });
  await fs.mkdir(path.dirname(metadataPath), { recursive: true });
  await recoverDesktopRom({ destinationPath, metadataPath });

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
    const [stagedStat, sourceHash, stagedHash] = await Promise.all([
      fs.stat(romStaging), sha256File(sourcePath), sha256File(romStaging)
    ]);
    if (!stagedStat.isFile() || stagedStat.size !== sourceStat.size || sourceHash !== stagedHash) {
      throw new Error('A cópia temporária da ROM não corresponde ao arquivo de origem.');
    }

    const committedMetadata = {
      ...metadata,
      size: stagedStat.size,
      sha256: stagedHash,
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

module.exports = { commitDesktopRom, recoverDesktopRom, sha256File };
