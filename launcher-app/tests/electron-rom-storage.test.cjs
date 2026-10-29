'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { commitDesktopRom, recoverDesktopRom } = require('../electron/rom-storage.cjs');

async function digest(filePath) {
  const data = await fs.readFile(filePath);
  return crypto.createHash('sha256').update(data).digest('hex');
}

async function makeStore(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-desktop-rom-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const romDir = path.join(root, 'roms');
  const destinationPath = path.join(romDir, 'current.nds');
  const metadataPath = path.join(root, 'rom-import.json');
  return { root, romDir, destinationPath, metadataPath };
}

test('desktop ROM replacement commits verified ROM bytes and metadata together', async (t) => {
  const store = await makeStore(t);
  const sourcePath = path.join(store.root, 'selected.nds');
  const bytes = Buffer.from('valid-rom-fixture-data');
  await fs.writeFile(sourcePath, bytes);

  const expectedSha1 = crypto.createHash('sha1').update(bytes).digest('hex');
  const metadata = await commitDesktopRom({
    sourcePath,
    destinationPath: store.destinationPath,
    metadataPath: store.metadataPath,
    metadata: { name: 'selected.nds', size: bytes.length, importedAt: 'test-time' },
    expectedSha1
  });

  assert.deepEqual(await fs.readFile(store.destinationPath), bytes);
  assert.equal(metadata.name, 'selected.nds');
  assert.equal(metadata.size, bytes.length);
  assert.equal(metadata.sha256, await digest(store.destinationPath));
  assert.equal(metadata.sha1, expectedSha1);
  assert.deepEqual(JSON.parse(await fs.readFile(store.metadataPath, 'utf8')), metadata);
  for (const suffix of ['.importing', '.previous']) {
    await assert.rejects(fs.access(store.destinationPath + suffix));
    await assert.rejects(fs.access(store.metadataPath + suffix));
  }
});


test('desktop ROM import rejects a revision with the wrong full-image SHA-1 without replacing the previous ROM', async (t) => {
  const store = await makeStore(t);
  const previous = Buffer.from('known-good-previous-rom');
  const previousMetadata = {
    name: 'previous.nds',
    size: previous.length,
    sha256: crypto.createHash('sha256').update(previous).digest('hex'),
    storedName: 'current.nds',
    importedAt: 'previous-time'
  };
  const sourcePath = path.join(store.root, 'wrong-revision.nds');
  const sourceBytes = Buffer.from('same Nintendo DS header, different full image');
  await fs.mkdir(store.romDir, { recursive: true });
  await fs.writeFile(store.destinationPath, previous);
  await fs.writeFile(store.metadataPath, JSON.stringify(previousMetadata));
  await fs.writeFile(sourcePath, sourceBytes);

  const wrongExpectedSha1 = '0'.repeat(40);
  await assert.rejects(commitDesktopRom({
    sourcePath,
    destinationPath: store.destinationPath,
    metadataPath: store.metadataPath,
    metadata: { name: 'wrong-revision.nds', size: sourceBytes.length, importedAt: 'new-time' },
    expectedSha1: wrongExpectedSha1
  }), /SHA-1 esperado: .*Nenhuma ROM foi instalada/);

  assert.deepEqual(await fs.readFile(store.destinationPath), previous);
  assert.deepEqual(JSON.parse(await fs.readFile(store.metadataPath, 'utf8')), previousMetadata);
  await assert.rejects(fs.access(store.destinationPath + '.importing'));
  await assert.rejects(fs.access(store.metadataPath + '.importing'));
});

test('failed desktop ROM staging leaves the last committed ROM and metadata untouched', async (t) => {
  const store = await makeStore(t);
  const previous = Buffer.from('previous-valid-rom');
  const previousMetadata = {
    name: 'previous.nds', size: previous.length,
    sha256: crypto.createHash('sha256').update(previous).digest('hex'),
    storedName: 'current.nds', importedAt: 'previous-time'
  };
  await fs.mkdir(store.romDir, { recursive: true });
  await fs.writeFile(store.destinationPath, previous);
  await fs.writeFile(store.metadataPath, JSON.stringify(previousMetadata));

  await assert.rejects(commitDesktopRom({
    sourcePath: path.join(store.root, 'missing-source.nds'),
    destinationPath: store.destinationPath,
    metadataPath: store.metadataPath,
    metadata: { name: 'new.nds', size: 4096, importedAt: 'new-time' }
  }));

  assert.deepEqual(await fs.readFile(store.destinationPath), previous);
  assert.deepEqual(JSON.parse(await fs.readFile(store.metadataPath, 'utf8')), previousMetadata);
  await assert.rejects(fs.access(store.destinationPath + '.importing'));
  await assert.rejects(fs.access(store.metadataPath + '.importing'));
});

test('metadata commit failure restores both the prior desktop ROM and its metadata', async (t) => {
  const store = await makeStore(t);
  const oldRom = Buffer.from('previous-valid-rom');
  const oldMetadata = {
    name: 'previous.nds', size: oldRom.length,
    sha256: crypto.createHash('sha256').update(oldRom).digest('hex'),
    storedName: 'current.nds', importedAt: 'previous-time'
  };
  const sourcePath = path.join(store.root, 'selected.nds');
  await fs.mkdir(store.romDir, { recursive: true });
  await fs.writeFile(store.destinationPath, oldRom);
  await fs.writeFile(store.metadataPath, JSON.stringify(oldMetadata));
  await fs.writeFile(sourcePath, Buffer.from('new-rom-with-more-bytes'));

  const originalRename = fs.rename;
  fs.rename = async (from, to) => {
    if (from === store.metadataPath + '.importing' && to === store.metadataPath) {
      throw new Error('simulated metadata commit failure');
    }
    return originalRename(from, to);
  };
  try {
    await assert.rejects(commitDesktopRom({
      sourcePath,
      destinationPath: store.destinationPath,
      metadataPath: store.metadataPath,
      metadata: { name: 'selected.nds', size: (await fs.stat(sourcePath)).size, importedAt: 'new-time' }
    }), /simulated metadata commit failure/);
  } finally {
    fs.rename = originalRename;
  }

  assert.deepEqual(await fs.readFile(store.destinationPath), oldRom);
  assert.deepEqual(JSON.parse(await fs.readFile(store.metadataPath, 'utf8')), oldMetadata);
  await assert.rejects(fs.access(store.destinationPath + '.previous'));
  await assert.rejects(fs.access(store.metadataPath + '.previous'));
});

test('backup cleanup failure does not report a committed ROM import as failed', async (t) => {
  const store = await makeStore(t);
  const oldRom = Buffer.from('previous-valid-rom');
  const oldMetadata = {
    name: 'previous.nds', size: oldRom.length,
    sha256: crypto.createHash('sha256').update(oldRom).digest('hex'),
    storedName: 'current.nds', importedAt: 'previous-time'
  };
  const sourcePath = path.join(store.root, 'selected.nds');
  await fs.mkdir(store.romDir, { recursive: true });
  await fs.writeFile(store.destinationPath, oldRom);
  await fs.writeFile(store.metadataPath, JSON.stringify(oldMetadata));
  const newRom = Buffer.from('new-rom-with-more-bytes');
  await fs.writeFile(sourcePath, newRom);

  const originalRm = fs.rm;
  fs.rm = async (target, options) => {
    if (target === store.destinationPath + '.previous'
        || target === store.metadataPath + '.previous') {
      throw new Error('simulated stale-backup cleanup failure');
    }
    return originalRm(target, options);
  };
  let metadata;
  try {
    metadata = await commitDesktopRom({
      sourcePath,
      destinationPath: store.destinationPath,
      metadataPath: store.metadataPath,
      metadata: { name: 'selected.nds', size: newRom.length, importedAt: 'new-time' }
    });
  } finally {
    fs.rm = originalRm;
  }

  assert.deepEqual(await fs.readFile(store.destinationPath), newRom);
  assert.equal(metadata.sha256, await digest(store.destinationPath));
  assert.deepEqual(JSON.parse(await fs.readFile(store.metadataPath, 'utf8')), metadata);
  assert.deepEqual(await fs.readFile(store.destinationPath + '.previous'), oldRom);
  assert.deepEqual(
    JSON.parse(await fs.readFile(store.metadataPath + '.previous', 'utf8')),
    oldMetadata
  );
});

test('desktop recovery finishes a first import interrupted after installing the ROM but before metadata', async (t) => {
  const store = await makeStore(t);
  await fs.mkdir(store.romDir, { recursive: true });
  const rom = Buffer.from('first-import-rom-data');
  const metadata = {
    name: 'first-import.nds',
    size: rom.length,
    sha256: crypto.createHash('sha256').update(rom).digest('hex'),
    storedName: 'current.nds',
    importedAt: 'first-import-time'
  };
  await fs.writeFile(store.destinationPath, rom);
  await fs.writeFile(store.metadataPath + '.importing', JSON.stringify(metadata));

  await recoverDesktopRom({
    destinationPath: store.destinationPath,
    metadataPath: store.metadataPath
  });

  assert.deepEqual(await fs.readFile(store.destinationPath), rom);
  assert.deepEqual(JSON.parse(await fs.readFile(store.metadataPath, 'utf8')), metadata);
  await assert.rejects(fs.access(store.metadataPath + '.importing'));
});

test('desktop recovery completes a verified first-import staging pair', async (t) => {
  const store = await makeStore(t);
  await fs.mkdir(store.romDir, { recursive: true });
  const rom = Buffer.from('staged-first-import-rom-data');
  const metadata = {
    name: 'first-import.nds',
    size: rom.length,
    sha256: crypto.createHash('sha256').update(rom).digest('hex'),
    storedName: 'current.nds',
    importedAt: 'first-import-time'
  };
  await fs.writeFile(store.destinationPath + '.importing', rom);
  await fs.writeFile(store.metadataPath + '.importing', JSON.stringify(metadata));

  await recoverDesktopRom({
    destinationPath: store.destinationPath,
    metadataPath: store.metadataPath
  });

  assert.deepEqual(await fs.readFile(store.destinationPath), rom);
  assert.deepEqual(JSON.parse(await fs.readFile(store.metadataPath, 'utf8')), metadata);
  await assert.rejects(fs.access(store.destinationPath + '.importing'));
  await assert.rejects(fs.access(store.metadataPath + '.importing'));
});

test('desktop recovery validates the ROM SHA-256 even when no temporary files remain', async (t) => {
  const store = await makeStore(t);
  await fs.mkdir(store.romDir, { recursive: true });
  const expectedRom = Buffer.from('valid-ROM-content');
  const corruptedRom = Buffer.from('wrong-ROM-content');
  assert.equal(expectedRom.length, corruptedRom.length);
  const metadata = {
    name: 'current.nds',
    size: expectedRom.length,
    sha256: crypto.createHash('sha256').update(expectedRom).digest('hex'),
    storedName: 'current.nds',
    importedAt: 'test-time'
  };
  await fs.writeFile(store.destinationPath, corruptedRom);
  await fs.writeFile(store.metadataPath, JSON.stringify(metadata));

  assert.equal(
    await recoverDesktopRom({
      destinationPath: store.destinationPath,
      metadataPath: store.metadataPath
    }),
    false
  );

  assert.deepEqual(await fs.readFile(store.destinationPath), corruptedRom);
  assert.deepEqual(JSON.parse(await fs.readFile(store.metadataPath, 'utf8')), metadata);
});

test('explicit ROM import can replace an unverified prior pair after staging a valid source', async (t) => {
  const store = await makeStore(t);
  await fs.mkdir(store.romDir, { recursive: true });
  const expectedOldRom = Buffer.from('valid-ROM-content');
  const corruptOldRom = Buffer.from('wrong-ROM-content');
  const oldMetadata = {
    name: 'old.nds',
    size: expectedOldRom.length,
    sha256: crypto.createHash('sha256').update(expectedOldRom).digest('hex'),
    storedName: 'current.nds',
    importedAt: 'old-time'
  };
  const sourcePath = path.join(store.root, 'replacement.nds');
  const newRom = Buffer.from('new-valid-rom-source');
  await fs.writeFile(store.destinationPath, corruptOldRom);
  await fs.writeFile(store.metadataPath, JSON.stringify(oldMetadata));
  await fs.writeFile(sourcePath, newRom);

  const metadata = await commitDesktopRom({
    sourcePath,
    destinationPath: store.destinationPath,
    metadataPath: store.metadataPath,
    metadata: { name: 'replacement.nds', size: newRom.length, importedAt: 'new-time' }
  });

  assert.deepEqual(await fs.readFile(store.destinationPath), newRom);
  assert.equal(metadata.sha256, await digest(store.destinationPath));
  assert.deepEqual(JSON.parse(await fs.readFile(store.metadataPath, 'utf8')), metadata);
  await assert.rejects(fs.access(store.destinationPath + '.previous'));
  await assert.rejects(fs.access(store.metadataPath + '.previous'));
});

test('desktop recovery propagates permission errors instead of treating protected files as absent', async (t) => {
  const store = await makeStore(t);
  const originalAccess = fs.access;
  fs.access = async (filePath, ...args) => {
    if (filePath === store.destinationPath) {
      throw Object.assign(new Error('permission denied'), { code: 'EACCES' });
    }
    return originalAccess.call(fs, filePath, ...args);
  };
  try {
    await assert.rejects(
      recoverDesktopRom({
        destinationPath: store.destinationPath,
        metadataPath: store.metadataPath
      }),
      { code: 'EACCES' }
    );
  } finally {
    fs.access = originalAccess;
  }
});

test('desktop ROM recovery restores a matching backup after an interrupted metadata commit', async (t) => {
  const store = await makeStore(t);
  await fs.mkdir(store.romDir, { recursive: true });
  const previous = Buffer.from('previous-valid-rom');
  const newer = Buffer.from('new-rom-not-fully-committed');
  const previousMetadata = {
    name: 'previous.nds', size: previous.length,
    sha256: crypto.createHash('sha256').update(previous).digest('hex'),
    storedName: 'current.nds', importedAt: 'previous-time'
  };
  await fs.writeFile(store.destinationPath + '.previous', previous);
  await fs.writeFile(store.metadataPath + '.previous', JSON.stringify(previousMetadata));
  await fs.writeFile(store.destinationPath, newer);

  await recoverDesktopRom({
    destinationPath: store.destinationPath,
    metadataPath: store.metadataPath
  });

  assert.deepEqual(await fs.readFile(store.destinationPath), previous);
  assert.deepEqual(JSON.parse(await fs.readFile(store.metadataPath, 'utf8')), previousMetadata);
  await assert.rejects(fs.access(store.destinationPath + '.previous'));
  await assert.rejects(fs.access(store.metadataPath + '.previous'));
});
