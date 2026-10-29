'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { stageNativeRuntime } = require('../scripts/stage-native-runtime.cjs');

function createRuntime(sourceRoot, platform = 'linux') {
  fs.mkdirSync(sourceRoot, { recursive: true });
  const executable = path.join(
    sourceRoot,
    platform === 'windows' ? 'main.exe' : 'pokeplatinum.AppImage'
  );
  fs.writeFileSync(executable, platform === 'windows' ? 'native-runtime-test-binary' : 'portable-linux-appimage');
  if (platform === 'linux') {
    fs.chmodSync(executable, 0o755);
    // The build tree also contains the raw executable, but the portable
    // AppImage is what the launcher stages to keep its shared libraries intact.
    fs.writeFileSync(path.join(sourceRoot, 'main'), 'raw-linux-executable-not-staged');
    fs.chmodSync(path.join(sourceRoot, 'main'), 0o755);
  } else {
    fs.writeFileSync(path.join(sourceRoot, 'SDL2.dll'), 'native-runtime-test-library');
  }
  for (const relative of [
    'header.bin',
    'firmware.bin',
    'wazaeffect/we.arc',
    'battle/skill/waza_seq.narc',
    'msgdata/pl_msg.narc'
  ]) {
    const target = path.join(sourceRoot, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, 'fixture:' + relative);
  }
}

test('stages a Linux runtime, fingerprints all files, and omits local save/config files', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-stage-runtime-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sourceRoot = path.join(root, 'build_linux', 'pokeplatinum');
  const destinationRoot = path.join(root, 'launcher-app', 'runtime');
  createRuntime(sourceRoot, 'linux');
  fs.writeFileSync(path.join(sourceRoot, 'save.bin'), 'user save should not be packaged');
  fs.writeFileSync(path.join(sourceRoot, 'sim_config.ini'), 'user settings should not be packaged');

  const result = stageNativeRuntime({ sourceRoot, destinationRoot, platform: 'linux' });
  assert.equal(result.platform, 'linux');
  assert.equal(result.destination, destinationRoot);
  assert.equal(result.files, 1);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'main')), true);
  assert.equal(fs.readFileSync(path.join(destinationRoot, 'main'), 'utf8'), 'portable-linux-appimage');
  assert.equal(fs.existsSync(path.join(destinationRoot, 'msgdata', 'pl_msg.narc')), false);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'header.bin')), false);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'firmware.bin')), false);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'save.bin')), false);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'sim_config.ini')), false);
  assert.equal(
    fs.readFileSync(path.join(destinationRoot, 'launcher-runtime-version.txt'), 'utf8').trim(),
    result.buildId
  );
  assert.notEqual(result.buildId, '');
  assert.notEqual(fs.statSync(path.join(destinationRoot, 'main')).mode & 0o111, 0);
});

test('stages a Windows runtime with main.exe without requiring Unix executable bits', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-stage-runtime-win-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sourceRoot = path.join(root, 'build_win64', 'pokeplatinum');
  const destinationRoot = path.join(root, 'launcher-app', 'runtime');
  createRuntime(sourceRoot, 'windows');

  const result = stageNativeRuntime({ sourceRoot, destinationRoot, platform: 'windows' });
  assert.equal(result.executable, path.join(destinationRoot, 'main.exe'));
  assert.equal(result.files, 2);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'main.exe')), true);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'SDL2.dll')), true);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'header.bin')), false);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'wazaeffect', 'we.arc')), false);
});

test('refuses to stage a runtime that contains a ROM or patch and preserves the previous destination', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-stage-runtime-forbidden-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sourceRoot = path.join(root, 'build_linux', 'pokeplatinum');
  const destinationRoot = path.join(root, 'launcher-app', 'runtime');
  createRuntime(sourceRoot, 'linux');
  fs.writeFileSync(path.join(sourceRoot, 'local-rom.nds'), 'must never enter the packaged runtime');
  fs.mkdirSync(destinationRoot, { recursive: true });
  fs.writeFileSync(path.join(destinationRoot, 'preserve.txt'), 'previous destination');

  assert.throws(
    () => stageNativeRuntime({ sourceRoot, destinationRoot, platform: 'linux' }),
    /ROM\/save\/patch proibido/
  );
  assert.equal(fs.readFileSync(path.join(destinationRoot, 'preserve.txt'), 'utf8'), 'previous destination');
  assert.equal(fs.existsSync(path.join(destinationRoot, 'main')), false);
});

test('refuses symbolic links in the native runtime source', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-stage-runtime-link-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sourceRoot = path.join(root, 'build_linux', 'pokeplatinum');
  const destinationRoot = path.join(root, 'launcher-app', 'runtime');
  const outside = path.join(root, 'outside.txt');
  createRuntime(sourceRoot, 'linux');
  fs.writeFileSync(outside, 'external file');
  try {
    fs.symlinkSync(outside, path.join(sourceRoot, 'external.txt'), 'file');
  } catch (error) {
    if (error && ['EPERM', 'EACCES', 'ENOTSUP', 'ENOSYS'].includes(error.code)) {
      t.skip('Symlinks are unavailable in this environment.');
      return;
    }
    throw error;
  }

  assert.throws(
    () => stageNativeRuntime({ sourceRoot, destinationRoot, platform: 'linux' }),
    /link simbólico/
  );
  assert.equal(fs.existsSync(destinationRoot), false);
});

test('does not replace a previous runtime when the portable executable is missing', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-stage-runtime-incomplete-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sourceRoot = path.join(root, 'build_linux', 'pokeplatinum');
  const destinationRoot = path.join(root, 'launcher-app', 'runtime');
  createRuntime(sourceRoot, 'linux');
  fs.unlinkSync(path.join(sourceRoot, 'pokeplatinum.AppImage'));
  fs.mkdirSync(destinationRoot, { recursive: true });
  fs.writeFileSync(path.join(destinationRoot, 'preserve.txt'), 'previous destination');

  assert.throws(
    () => stageNativeRuntime({ sourceRoot, destinationRoot, platform: 'linux' }),
    /Executável nativo portátil Linux ausente/
  );
  assert.equal(fs.readFileSync(path.join(destinationRoot, 'preserve.txt'), 'utf8'), 'previous destination');
});
