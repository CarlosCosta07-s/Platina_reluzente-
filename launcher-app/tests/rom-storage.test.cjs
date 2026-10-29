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

  const writeOptions = [];
  const appendOptions = [];
  return {
    files,
    writeOptions,
    appendOptions,
    async stat({ path }) {
      const value = files.get(path);
      if (!value) throw new Error('ENOENT: ' + path);
      return { size: value.length };
    },
    async writeFile(options) {
      writeOptions.push(options);
      files.set(options.path, Buffer.from(options.data, 'base64'));
    },
    async appendFile(options) {
      appendOptions.push(options);
      if (failAppend) {
        failAppend = false;
        throw new Error('simulated interrupted write');
      }
      const previous = files.get(options.path);
      if (!previous) throw new Error('ENOENT: ' + options.path);
      files.set(options.path, Buffer.concat([previous, Buffer.from(options.data, 'base64')]));
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
  chunkSize: 4,
  toBase64: (buffer) => Buffer.from(buffer).toString('base64')
};

test('rejects empty and oversized files before touching the stored ROM', async () => {
  const { persistRomAtomically } = await loadPersistence();
  const oldRom = Buffer.from('previous-valid-rom');
  const filesystem = memoryFilesystem({ 'roms/current.nds': oldRom });

  await assert.rejects(
    persistRomAtomically({ ...common, filesystem, file: makeFile('') }),
    /ROM size must be a positive safe integer/
  );

  const oversized = makeFile('unused');
  Object.defineProperty(oversized, 'size', { value: 512 * 1024 * 1024 + 1 });
  await assert.rejects(
    persistRomAtomically({ ...common, filesystem, file: oversized }),
    /ROM size must be a positive safe integer/
  );

  assert.deepEqual(filesystem.files.get('roms/current.nds'), oldRom);
  assert.equal(filesystem.writeOptions.length, 0);
});

test('does not mistake a storage permission error for a missing previous ROM', async () => {
  const { persistRomAtomically } = await loadPersistence();
  const oldRom = Buffer.from('previous-valid-rom');
  const filesystem = memoryFilesystem({ 'roms/current.nds': oldRom });
  const originalStat = filesystem.stat.bind(filesystem);
  filesystem.stat = async (options) => {
    if (options.path === 'roms/current.nds') {
      throw new Error('EACCES: permission denied');
    }
    return originalStat(options);
  };

  await assert.rejects(
    persistRomAtomically({ ...common, filesystem, file: makeFile('new-rom-data') }),
    /EACCES: permission denied/
  );

  assert.deepEqual(filesystem.files.get('roms/current.nds'), oldRom);
  assert.equal(filesystem.writeOptions.length, 0);
});

test('allows a first import when the ROM directory does not exist yet', async () => {
  const { persistRomAtomically } = await loadPersistence();
  const filesystem = memoryFilesystem();
  const originalStat = filesystem.stat.bind(filesystem);
  filesystem.stat = async (options) => {
    if (options.path === 'roms/current.nds') {
      throw new Error('Directory does not exist: roms');
    }
    return originalStat(options);
  };

  const rom = Buffer.from('new-rom-data');
  const result = await persistRomAtomically({
    ...common, filesystem, file: makeFile(rom)
  });

  assert.equal(result.path, 'roms/current.nds');
  assert.deepEqual(filesystem.files.get('roms/current.nds'), rom);
});

test('writes Base64 chunks as binary and replaces the ROM only after completion', async () => {
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
  assert.ok(filesystem.writeOptions.length > 0);
  assert.ok(filesystem.appendOptions.length > 0);
  assert.equal(filesystem.writeOptions.every((options) => !('encoding' in options)), true);
  assert.equal(filesystem.appendOptions.every((options) => !('encoding' in options)), true);
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


test('does not replace the previous ROM when staged size validation fails', async () => {
  const { persistRomAtomically } = await loadPersistence();
  const oldRom = Buffer.from('previous-valid-rom');
  const filesystem = memoryFilesystem({ 'roms/current.nds': oldRom });
  const originalStat = filesystem.stat.bind(filesystem);
  filesystem.stat = async (options) => {
    const result = await originalStat(options);
    return options.path === 'roms/current.nds.importing'
      ? { ...result, size: result.size - 1 }
      : result;
  };

  await assert.rejects(
    persistRomAtomically({ ...common, filesystem, file: makeFile('new-rom-data') }),
    /importação da ROM ficou incompleta/
  );

  assert.deepEqual(filesystem.files.get('roms/current.nds'), oldRom);
  assert.equal(filesystem.files.has('roms/current.nds.importing'), false);
  assert.equal(filesystem.files.has('roms/current.nds.previous'), false);
});
