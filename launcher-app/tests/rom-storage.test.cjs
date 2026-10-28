'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

async function loadPersistence() {
  return import('../web/rom-storage.js');
}

function makeFile(value) {
  const file = new Blob([value]);
  Object.defineProperty(file, 'name', { value: 'test.nds' });
  return file;
}

function memoryFilesystem(initialFiles = {}, behavior = {}) {
  const files = new Map(
    Object.entries(initialFiles).map(([name, value]) => [name, Buffer.from(value)])
  );
  let failAppend = Boolean(behavior.failAppend);
  let failInstallRename = Boolean(behavior.failInstallRename);

  return {
    files,
    async stat({ path }) {
      const value = files.get(path);
      if (!value) throw new Error('ENOENT: ' + path);
      return { size: value.length };
    },
    async writeFile({ path, data }) {
      files.set(path, Buffer.from(data, 'base64'));
    },
    async appendFile({ path, data }) {
      if (failAppend) {
        failAppend = false;
        throw new Error('simulated interrupted write');
      }
      const previous = files.get(path);
      if (!previous) throw new Error('ENOENT: ' + path);
      files.set(path, Buffer.concat([previous, Buffer.from(data, 'base64')]));
    },
    async rename({ from, to }) {
      if (failInstallRename && from === 'roms/current.nds.importing' && to === 'roms/current.nds') {
        failInstallRename = false;
        throw new Error('simulated staged install failure');
      }
      if (!files.has(from)) throw new Error('ENOENT: ' + from);
      files.set(to, files.get(from));
      files.delete(from);
    },
    async deleteFile({ path }) {
      if (!files.has(path)) throw new Error('ENOENT: ' + path);
      files.delete(path);
    }
  };
}

const common = {
  directory: 'DATA',
  encoding: 'BASE64',
  chunkSize: 4,
  toBase64: (buffer) => Buffer.from(buffer).toString('base64')
};

test('replaces the ROM only after all chunks have been written', async () => {
  const { persistRomAtomically } = await loadPersistence();
  const oldRom = Buffer.from('previous-valid-rom');
  const newRom = Buffer.from('new-rom-data-123');
  const filesystem = memoryFilesystem({ 'roms/current.nds': oldRom });

  const result = await persistRomAtomically({
    ...common, filesystem, file: makeFile(newRom)
  });

  assert.deepEqual(filesystem.files.get('roms/current.nds'), newRom);
  assert.equal(result.path, 'roms/current.nds');
  assert.equal(result.size, newRom.length);
  assert.equal(filesystem.files.has('roms/current.nds.importing'), false);
  assert.equal(filesystem.files.has('roms/current.nds.previous'), false);
});

test('preserves the previous ROM if a chunk write fails', async () => {
  const { persistRomAtomically } = await loadPersistence();
  const oldRom = Buffer.from('previous-valid-rom');
  const filesystem = memoryFilesystem(
    { 'roms/current.nds': oldRom },
    { failAppend: true }
  );

  await assert.rejects(
    persistRomAtomically({ ...common, filesystem, file: makeFile('new-rom-data') }),
    /simulated interrupted write/
  );

  assert.deepEqual(filesystem.files.get('roms/current.nds'), oldRom);
  assert.equal(filesystem.files.has('roms/current.nds.importing'), false);
});

test('restores the previous ROM if the staged file cannot be installed', async () => {
  const { persistRomAtomically } = await loadPersistence();
  const oldRom = Buffer.from('previous-valid-rom');
  const filesystem = memoryFilesystem(
    { 'roms/current.nds': oldRom },
    { failInstallRename: true }
  );

  await assert.rejects(
    persistRomAtomically({ ...common, filesystem, file: makeFile('new-rom-data') }),
    /simulated staged install failure/
  );

  assert.deepEqual(filesystem.files.get('roms/current.nds'), oldRom);
  assert.equal(filesystem.files.has('roms/current.nds.previous'), false);
  assert.equal(filesystem.files.has('roms/current.nds.importing'), false);
});

test('recovers a backup left by an earlier interrupted replacement', async () => {
  const { persistRomAtomically } = await loadPersistence();
  const recoveredRom = Buffer.from('recovered-valid-rom');
  const filesystem = memoryFilesystem({
    'roms/current.nds.previous': recoveredRom
  });
  const newRom = Buffer.from('new-rom-data');

  await persistRomAtomically({
    ...common, filesystem, file: makeFile(newRom)
  });

  assert.deepEqual(filesystem.files.get('roms/current.nds'), newRom);
  assert.equal(filesystem.files.has('roms/current.nds.previous'), false);
});
