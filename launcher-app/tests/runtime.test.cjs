'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { resolveRuntimeDirectory, findBundledExecutable, hasRequiredRuntimeData, isRuntimeUsable, verifyRuntimeManifest, prepareWritableRuntime, ensureHorizontalScreenLayout, validateNdsHeader, createPlatinumLaunchSpec } = require('../electron/runtime.cjs');

test('runtime resolves under Electron resources when packaged', () => {
  assert.equal(resolveRuntimeDirectory(true, '/app/resources', '/app'), path.join('/app/resources', 'runtime'));
});

test('Platinum launch contract passes the verified ROM and Linux AppImage extraction flag', () => {
  const runtime = { root: '/tmp/platinum-runtime', executable: '/tmp/platinum-runtime/main' };
  const rom = { filePath: '/tmp/private-rom/current.nds', sha256: 'a'.repeat(64) };
  const spec = createPlatinumLaunchSpec({
    runtime,
    rom,
    logPath: '/tmp/platinum-logs/native-startup.log',
    platform: 'linux',
    env: { PATH: '/usr/bin', DISPLAY: ':7' }
  });

  assert.equal(spec.executable, runtime.executable);
  assert.deepEqual(spec.args, ['--appimage-extract-and-run']);
  assert.equal(spec.cwd, runtime.root);
  assert.equal(spec.env.PLATINA_IMPORTED_ROM, rom.filePath);
  assert.equal(spec.env.PLATINA_IMPORTED_ROM_SHA256, rom.sha256);
  assert.equal(spec.env.PATH, '/usr/bin');
  assert.equal(spec.env.DISPLAY, ':7');
  assert.equal(spec.logPath, '/tmp/platinum-logs/native-startup.log');
  assert.equal(spec.romSha256, rom.sha256);
  assert.equal(spec.platform, 'linux');
});

test('Platinum launch contract omits Linux-only arguments on Windows', () => {
  const spec = createPlatinumLaunchSpec({
    runtime: { root: 'C:\\Platina\\runtime', executable: 'C:\\Platina\\runtime\\main.exe' },
    rom: { filePath: 'C:\\Users\\tester\\roms\\current.nds', sha256: 'b'.repeat(64) },
    logPath: 'C:\\Users\\tester\\logs\\native-startup.log',
    platform: 'win32',
    env: { PATH: 'C:\\Windows\\System32' }
  });

  assert.deepEqual(spec.args, []);
  assert.equal(spec.cwd, 'C:\\Platina\\runtime');
  assert.equal(spec.env.PATH, 'C:\\Windows\\System32');
  assert.equal(spec.platform, 'win32');
});

test('Platinum launch contract rejects missing or malformed ROM identity', () => {
  const runtime = { root: '/tmp/platinum-runtime', executable: '/tmp/platinum-runtime/main' };
  const logPath = '/tmp/platinum-logs/native-startup.log';
  assert.throws(() => createPlatinumLaunchSpec({
    runtime, rom: { filePath: '/tmp/rom.nds', sha256: 'invalid' }, logPath, platform: 'linux', env: {}
  }), /ROM verificada/);
  assert.throws(() => createPlatinumLaunchSpec({
    runtime, rom: null, logPath, platform: 'linux', env: {}
  }), /ROM verificada/);
  assert.throws(() => createPlatinumLaunchSpec({
    runtime, rom: { filePath: 'relative.nds', sha256: 'a'.repeat(64) }, logPath, platform: 'linux', env: {}
  }), /ROM verificada/);
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


function writeRuntimeManifest(directory, platform = 'linux') {
  const executableName = platform === 'win32' ? 'main.exe' : 'main';
  const executablePath = path.join(directory, executableName);
  const stat = fs.statSync(executablePath);
  const sha256 = crypto.createHash('sha256').update(fs.readFileSync(executablePath)).digest('hex');
  const manifestHash = crypto.createHash('sha256');
  manifestHash.update(executableName + '\0' + sha256 + '\n');
  const buildId = manifestHash.digest('hex');
  fs.writeFileSync(path.join(directory, 'launcher-runtime-manifest.json'), JSON.stringify({
    schemaVersion: 1,
    platform: platform === 'win32' ? 'windows' : platform,
    buildId,
    files: [{ path: executableName, size: stat.size, sha256 }]
  }, null, 2) + '\n');
  fs.writeFileSync(path.join(directory, 'launcher-runtime-version.txt'), buildId + '\n');
  return buildId;
}

function makeRuntimeFixture(directory, platform = 'linux', label = 'test-build') {
  fs.mkdirSync(directory, { recursive: true });
  const executable = path.join(directory, platform === 'win32' ? 'main.exe' : 'main');
  fs.writeFileSync(executable, 'fake native executable:' + label);
  fs.chmodSync(executable, 0o755);
  for (const relative of [
    'header.bin',
    'firmware.bin',
    'wazaeffect/we.arc',
    'battle/skill/waza_seq.narc'
  ]) {
    const destination = path.join(directory, relative);
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.writeFileSync(destination, 'fixture:' + relative);
  }
  return writeRuntimeManifest(directory, platform);
}

test('prepares a writable runtime, preserves local game data and refreshes bundled files', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-writable-runtime-'));
  const source = path.join(temp, 'bundled-runtime');
  const destination = path.join(temp, 'user-data', 'runtime');
  try {
    const buildOneId = makeRuntimeFixture(source, 'linux', 'build-1');
    const first = prepareWritableRuntime(source, destination, 'linux');
    assert.equal(first.root, destination);
    assert.equal(first.executable, path.join(destination, 'main'));
    assert.equal(first.buildId, buildOneId);
    assert.equal(first.reused, false);
    assert.equal(fs.existsSync(path.join(destination, 'header.bin')), true);

    fs.writeFileSync(path.join(destination, 'sim_config.ini'), 'user settings');
    fs.writeFileSync(path.join(destination, 'save.bin'), 'local save');
    const reused = prepareWritableRuntime(source, destination, 'linux');
    assert.equal(reused.reused, true);
    assert.equal(fs.readFileSync(path.join(destination, 'sim_config.ini'), 'utf8'), 'user settings');

    fs.writeFileSync(path.join(source, 'main'), 'updated native executable');
    const buildTwoId = writeRuntimeManifest(source, 'linux');
    const refreshed = prepareWritableRuntime(source, destination, 'linux');
    assert.equal(refreshed.buildId, buildTwoId);
    assert.equal(refreshed.reused, false);
    assert.equal(fs.readFileSync(path.join(destination, 'main'), 'utf8'), 'updated native executable');
    assert.equal(fs.readFileSync(path.join(destination, 'sim_config.ini'), 'utf8'), 'user settings');
    assert.equal(fs.readFileSync(path.join(destination, 'save.bin'), 'utf8'), 'local save');
    assert.equal(fs.existsSync(destination + '.previous'), false);
    assert.equal(fs.existsSync(destination + '.staging'), false);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test('allows an executable-only runtime and preserves assets extracted from the imported ROM', (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-runtime-rom-extraction-'));
  const source = path.join(temp, 'bundled-runtime');
  const destination = path.join(temp, 'user-data', 'runtime');
  try {
    fs.mkdirSync(source, { recursive: true });
    fs.writeFileSync(path.join(source, 'main'), 'portable native executable');
    fs.chmodSync(path.join(source, 'main'), 0o755);
    writeRuntimeManifest(source, 'linux');

    assert.equal(hasRequiredRuntimeData(source), false);
    assert.equal(verifyRuntimeManifest(source, 'linux'), true);
    assert.equal(isRuntimeUsable(source, 'linux'), true);

    const first = prepareWritableRuntime(source, destination, 'linux');
    assert.equal(first.executable, path.join(destination, 'main'));
    assert.equal(first.reused, false);
    assert.equal(hasRequiredRuntimeData(destination), false);

    // The native engine writes extracted files relative to its working
    // directory. A later launch should keep these files when refreshing code.
    for (const relative of [
      'header.bin',
      'firmware.bin',
      'wazaeffect/we.arc',
      'battle/skill/waza_seq.narc'
    ]) {
      const target = path.join(destination, relative);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, 'extracted-from-user-rom:' + relative);
    }
    assert.equal(hasRequiredRuntimeData(destination), true);

    const reused = prepareWritableRuntime(source, destination, 'linux');
    assert.equal(reused.reused, true);
    assert.equal(fs.readFileSync(path.join(destination, 'battle', 'skill', 'waza_seq.narc'), 'utf8'),
      'extracted-from-user-rom:battle/skill/waza_seq.narc');
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test('writable runtime preparation rejects a linked bundled runtime tree', (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-writable-runtime-symlink-'));
  const source = path.join(temp, 'bundled-runtime');
  const outside = path.join(temp, 'outside');
  const destination = path.join(temp, 'user-data', 'runtime');
  try {
    makeRuntimeFixture(source);
    fs.mkdirSync(outside);
    try {
      fs.symlinkSync(outside, path.join(source, 'external-link'), 'dir');
    } catch (error) {
      if (error && ['EPERM', 'EACCES', 'ENOTSUP', 'ENOSYS'].includes(error.code)) {
        t.skip('This platform does not permit creating symlinks for tests.');
        return;
      }
      throw error;
    }
    assert.throws(() => prepareWritableRuntime(source, destination, 'linux'), /Symbolic links are not allowed/);
    assert.equal(fs.existsSync(destination), false);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test('runtime status rejects an unsafe extra file before enabling launch', (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-runtime-extra-link-'));
  const outside = path.join(directory, 'outside.txt');
  const runtime = path.join(directory, 'runtime');
  fs.mkdirSync(runtime);
  try {
    fs.writeFileSync(path.join(runtime, 'main'), 'native executable');
    fs.chmodSync(path.join(runtime, 'main'), 0o755);
    for (const relative of [
      'header.bin',
      'firmware.bin',
      'wazaeffect/we.arc',
      'battle/skill/waza_seq.narc'
    ]) {
      const target = path.join(runtime, relative);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, 'fixture');
    }
    fs.writeFileSync(outside, 'outside');
    try {
      fs.symlinkSync(outside, path.join(runtime, 'unexpected-link'), 'file');
    } catch (error) {
      if (error && ['EPERM', 'EACCES', 'ENOTSUP', 'ENOSYS'].includes(error.code)) {
        t.skip('This platform does not permit creating symlinks for tests.');
        return;
      }
      throw error;
    }

    assert.equal(hasRequiredRuntimeData(runtime), true);
    assert.equal(findBundledExecutable(runtime, 'linux'), path.join(runtime, 'main'));
    assert.equal(isRuntimeUsable(runtime, 'linux'), false);
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


test('horizontal screen layout is created on a fresh writable runtime', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-screen-layout-'));
  try {
    const configPath = ensureHorizontalScreenLayout(directory);
    assert.equal(configPath, path.join(directory, 'sim_config.ini'));
    assert.equal(fs.readFileSync(configPath, 'utf8'), '[General]\nScreenLayout=horizontal\n');
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('horizontal layout preserves user settings and other config sections', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-screen-layout-preserve-'));
  const configPath = path.join(directory, 'sim_config.ini');
  try {
    fs.writeFileSync(configPath, [
      '[General]',
      'MasterVolume=100',
      'ScreenLayout=vertical',
      'FullScreen=false',
      '[PAD]',
      'AKey=122',
      '',
    ].join('\r\n'), 'utf8');

    ensureHorizontalScreenLayout(directory);
    const content = fs.readFileSync(configPath, 'utf8');
    assert.match(content, /MasterVolume=100/);
    assert.match(content, /ScreenLayout=horizontal/);
    assert.match(content, /FullScreen=false/);
    assert.match(content, /\[PAD\]\r\nAKey=122/);
    assert.equal((content.match(/ScreenLayout=/g) || []).length, 1);
    assert.equal(content.includes('ScreenLayout=vertical'), false);
    assert.equal((content.match(/\[General\]/g) || []).length, 1);
    assert.equal(ensureHorizontalScreenLayout(directory), configPath);
    assert.equal(fs.readFileSync(configPath, 'utf8'), content);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('horizontal layout refuses a symlinked config file', (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-screen-layout-link-'));
  const target = path.join(directory, 'outside.ini');
  const configPath = path.join(directory, 'sim_config.ini');
  try {
    fs.writeFileSync(target, '[General]\nScreenLayout=vertical\n');
    try {
      fs.symlinkSync(target, configPath, 'file');
    } catch (error) {
      if (error && ['EPERM', 'EACCES', 'ENOTSUP', 'ENOSYS'].includes(error.code)) {
        t.skip('This platform does not permit creating symlinks for tests.');
        return;
      }
      throw error;
    }
    assert.throws(() => ensureHorizontalScreenLayout(directory), /arquivo regular/);
    assert.equal(fs.readFileSync(target, 'utf8'), '[General]\nScreenLayout=vertical\n');
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});


test('runtime integrity check refuses a tampered native executable even when the old marker remains', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-runtime-manifest-tamper-'));
  const source = path.join(temp, 'bundled-runtime');
  const destination = path.join(temp, 'user-data', 'runtime');
  try {
    makeRuntimeFixture(source, 'linux', 'known-build');
    const first = prepareWritableRuntime(source, destination, 'linux');
    assert.equal(verifyRuntimeManifest(destination, 'linux'), true);

    fs.writeFileSync(path.join(destination, 'main'), 'altered executable with the same marker');
    assert.equal(verifyRuntimeManifest(destination, 'linux'), false);
    assert.equal(isRuntimeUsable(destination, 'linux'), false);

    // Startup preparation repairs only the app-managed native payload from
    // the trusted bundled copy and preserves local saves/config/extracted data.
    fs.writeFileSync(path.join(destination, 'save.bin'), 'user save');
    fs.writeFileSync(path.join(destination, 'sim_config.ini'), 'user config');
    const repaired = prepareWritableRuntime(source, destination, 'linux');
    assert.equal(repaired.reused, false);
    assert.equal(verifyRuntimeManifest(destination, 'linux'), true);
    assert.equal(fs.readFileSync(path.join(destination, 'main'), 'utf8'), 'fake native executable:known-build');
    assert.equal(fs.readFileSync(path.join(destination, 'save.bin'), 'utf8'), 'user save');
    assert.equal(fs.readFileSync(path.join(destination, 'sim_config.ini'), 'utf8'), 'user config');
    assert.equal(first.buildId, repaired.buildId);

    fs.writeFileSync(path.join(destination, 'untrusted.so'), 'unmanifested native library');
    assert.equal(verifyRuntimeManifest(destination, 'linux'), false);
    assert.equal(isRuntimeUsable(destination, 'linux'), false);
    assert.throws(
      () => prepareWritableRuntime(source, destination, 'linux'),
      /post-copy validation/
    );
    assert.equal(fs.existsSync(path.join(destination, 'untrusted.so')), true);
    fs.unlinkSync(path.join(destination, 'untrusted.so'));
    assert.equal(verifyRuntimeManifest(destination, 'linux'), true);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});
