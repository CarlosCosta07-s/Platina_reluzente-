'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { resolveRuntimeDirectory, findBundledExecutable, validateNdsHeader } = require('../electron/runtime.cjs');

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
test('ROM header validation checks a plausible Nintendo DS title, code and size', () => {
  const header = Buffer.alloc(0x200);
  header.write('POKEMON PLAT', 0, 'ascii');
  header.write('CPUE', 0x0c, 'ascii');
  assert.equal(validateNdsHeader(header, 1024), true);
  assert.equal(validateNdsHeader(header, 0x100), false);
  assert.equal(validateNdsHeader(header, 512 * 1024 * 1024 + 1), false);
  assert.equal(validateNdsHeader(header, Number.NaN), false);
  header.write('CPUP', 0x0c, 'ascii');
  assert.equal(validateNdsHeader(header, 1024), false);
  header.write('@@!!', 0x0c, 'ascii');
  assert.equal(validateNdsHeader(header, 1024), false);
});
