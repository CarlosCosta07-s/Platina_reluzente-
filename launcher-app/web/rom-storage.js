/**
 * Store a user-selected ROM without destroying the last valid copy on a failed import.
 *
 * The staging and backup files stay in the same private directory so filesystem
 * renames remain on one volume. The native runtime always reads roms/current.nds.
 */
export async function persistRomAtomically({
  filesystem,
  directory,
  file,
  toBase64,
  chunkSize = 1024 * 1024,
}) {
  if (!filesystem || !directory || !file || typeof toBase64 !== 'function') {
    throw new TypeError('Filesystem, directory, file and toBase64 are required.');
  }
  if (!Number.isSafeInteger(chunkSize) || chunkSize <= 0) {
    throw new TypeError('chunkSize must be a positive safe integer.');
  }

  const destination = 'roms/current.nds';
  const staging = 'roms/current.nds.importing';
  const backup = 'roms/current.nds.previous';
  const options = (path) => ({ path, directory });

  async function exists(path) {
    try {
      await filesystem.stat(options(path));
      return true;
    } catch {
      return false;
    }
  }

  async function removeIfPresent(path) {
    if (await exists(path)) await filesystem.deleteFile(options(path));
  }

  // Recover a previous interrupted replacement before starting a new one.
  const hasDestination = await exists(destination);
  const hasBackup = await exists(backup);
  if (!hasDestination && hasBackup) {
    await filesystem.rename({ from: backup, to: destination, directory });
  } else if (hasDestination && hasBackup) {
    await filesystem.deleteFile(options(backup));
  }
  await removeIfPresent(staging);

  try {
    const firstChunkSize = Math.min(chunkSize, file.size);
    const firstChunk = file.slice(0, firstChunkSize);
    // Capacitor interprets Base64 strings as binary only when encoding is omitted.
    // Its Encoding enum is for text encodings, not a BASE64 value.
    await filesystem.writeFile({
      path: staging,
      data: toBase64(await firstChunk.arrayBuffer()),
      directory,
      recursive: true,
    });

    for (let offset = firstChunkSize; offset < file.size; offset += chunkSize) {
      const chunk = file.slice(offset, Math.min(offset + chunkSize, file.size));
      await filesystem.appendFile({
        path: staging,
        data: toBase64(await chunk.arrayBuffer()),
        directory,
      });
    }

    const stagedStat = await filesystem.stat(options(staging));
    if (Number(stagedStat.size) !== file.size) {
      throw new Error(
        'A importação da ROM ficou incompleta: o arquivo salvo tem ' +
        stagedStat.size + ' bytes, mas eram esperados ' + file.size + '.'
      );
    }

    const hadPrevious = await exists(destination);
    if (hadPrevious) {
      await removeIfPresent(backup);
      await filesystem.rename({ from: destination, to: backup, directory });
    }

    try {
      await filesystem.rename({ from: staging, to: destination, directory });
    } catch (installError) {
      if (hadPrevious) {
        try {
          await filesystem.rename({ from: backup, to: destination, directory });
        } catch (restoreError) {
          throw new Error(
            'A nova ROM não pôde ser instalada e a cópia anterior permaneceu em ' +
            backup + '. Falha ao restaurar: ' + restoreError.message,
            { cause: installError }
          );
        }
      }
      throw installError;
    }

    // Installation has succeeded; a leftover backup is only a cleanup issue.
    try {
      await removeIfPresent(backup);
    } catch {
      // Keep the valid newly-installed ROM even if stale-backup cleanup fails.
    }
    return { path: destination, size: file.size };
  } catch (error) {
    try {
      await removeIfPresent(staging);
    } catch {
      // Preserve the original failure; a stale staging file is harmless and recoverable.
    }
    throw error;
  }
}
