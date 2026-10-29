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

  const metadata = await commitDesktopRom({
    sourcePath,
    destinationPath: store.destinationPath,
    metadataPath: store.metadataPath,
    metadata: { name: 'selected.nds', size: bytes.length, importedAt: 'test-time' }
  });

  assert.deepEqual(await fs.readFile(store.destinationPath), bytes);
  assert.equal(metadata.name, 'selected.nds');
  assert.equal(metadata.size, bytes.length);
  assert.equal(metadata.sha256, await digest(store.destinationPath));
  assert.deepEqual(JSON.parse(await fs.readFile(store.metadataPath, 'utf8')), metadata);
  for (const suffix of ['.importing', '.previous']) {
    await assert.rejects(fs.access(store.destinationPath + suffix));
    await assert.rejects(fs.access(store.metadataPath + suffix));
  }
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
