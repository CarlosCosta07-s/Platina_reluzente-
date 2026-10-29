'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { resolveRuntimeDirectory, findBundledExecutable, hasRequiredRuntimeData, validateNdsHeader } = require('../electron/runtime.cjs');

test('runtime resolves under Electron resources when packaged', () => {
  assert.equal(resolveRuntimeDirectory(true, '/app/resources', '/app'), path.join('/app/resources', 'runtime'));
});
test('runtime finds the included Windows/Linux executable names', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-runtime-'));
  try {
    fs.writeFileSync(path.join(directory, 'main'), 'fake binary');
    fs.chmodSync(path.join(directory, 'main'), 0o755);
    assert.equal(findBundledExecutable(directory, 'linux'), path.join(directory, 'main'));
    assert.equal(findBundledExecutable(directory, 'win32'), null);
    fs.writeFileSync(path.join(directory, 'main.exe'), 'fake binary');
    assert.equal(findBundledExecutable(directory, 'win32'), path.join(directory, 'main.exe'));
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});
test('runtime data status rejects missing or empty required game assets', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-runtime-data-'));
  const required = [
    'header.bin',
    'firmware.bin',
    'wazaeffect/we.arc',
    'battle/skill/waza_seq.narc'
  ];
  try {
    for (const relative of required) {
      const destination = path.join(directory, relative);
      fs.mkdirSync(path.dirname(destination), { recursive: true });
      fs.writeFileSync(destination, 'fixture');
    }
    assert.equal(hasRequiredRuntimeData(directory), true);

    fs.unlinkSync(path.join(directory, 'battle/skill/waza_seq.narc'));
    assert.equal(hasRequiredRuntimeData(directory), false);

    fs.writeFileSync(path.join(directory, 'battle/skill/waza_seq.narc'), '');
    assert.equal(hasRequiredRuntimeData(directory), false);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('runtime rejects symlinked executables and required game assets', (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-runtime-symlink-'));
  const outsideFile = path.join(directory, 'outside.bin');
  const outsideDirectory = path.join(directory, 'outside-data');
  const runtime = path.join(directory, 'runtime');
  fs.mkdirSync(runtime);
  fs.writeFileSync(outsideFile, 'outside runtime file');
  fs.chmodSync(outsideFile, 0o755);

  try {
    try {
      fs.symlinkSync(outsideFile, path.join(runtime, 'main'), 'file');
    } catch (error) {
      if (error && ['EPERM', 'EACCES', 'ENOTSUP', 'ENOSYS'].includes(error.code)) {
        t.skip('This platform does not permit creating symlinks for tests.');
        return;
      }
      throw error;
    }

    assert.equal(findBundledExecutable(runtime, 'linux'), null);
    fs.unlinkSync(path.join(runtime, 'main'));

    const required = [
      'header.bin',
      'firmware.bin',
      'wazaeffect/we.arc',
      'battle/skill/waza_seq.narc'
    ];
    for (const relative of required) {
      const destination = path.join(runtime, relative);
      fs.mkdirSync(path.dirname(destination), { recursive: true });
      fs.writeFileSync(destination, 'fixture');
    }

    fs.unlinkSync(path.join(runtime, 'header.bin'));
    fs.symlinkSync(outsideFile, path.join(runtime, 'header.bin'), 'file');
    assert.equal(hasRequiredRuntimeData(runtime), false);

    fs.unlinkSync(path.join(runtime, 'header.bin'));
    fs.writeFileSync(path.join(runtime, 'header.bin'), 'fixture');
    fs.mkdirSync(outsideDirectory);
    fs.writeFileSync(path.join(outsideDirectory, 'we.arc'), 'outside archive');
    fs.rmSync(path.join(runtime, 'wazaeffect'), { recursive: true, force: true });
    fs.symlinkSync(outsideDirectory, path.join(runtime, 'wazaeffect'), 'dir');
    assert.equal(hasRequiredRuntimeData(runtime), false);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('ROM header validation checks a plausible Nintendo DS title, code and size', () => {
  const header = Buffer.alloc(0x200);
  header.write('POKEMON PLAT', 0, 'ascii');
  header.write('CPUE', 0x0c, 'ascii');
  header[0x1e] = 1;
  assert.equal(validateNdsHeader(header, 1024), true);
  assert.equal(validateNdsHeader(header, 0x100), false);
  assert.equal(validateNdsHeader(header, 512 * 1024 * 1024 + 1), false);
  assert.equal(validateNdsHeader(header, Number.NaN), false);
  header[0x1e] = 0;
  assert.equal(validateNdsHeader(header, 1024), false);
  header[0x1e] = 1;
  header.write('CPUP', 0x0c, 'ascii');
  assert.equal(validateNdsHeader(header, 1024), false);
  header.write('@@!!', 0x0c, 'ascii');
  assert.equal(validateNdsHeader(header, 1024), false);
});
