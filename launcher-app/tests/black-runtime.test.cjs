'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {
  BLACK_ROM_SIZE,
  BLACK_ROM_SHA1,
  blackPaths,
  validateBlackRomIdentity,
  isBlackImportedMetadataValid,
  inspectBlackRom,
  inspectBlackRuntime,
  createBlackLaunchSpec
} = require('../electron/black-runtime.cjs');

test('Black data paths are isolated from Platinum and use local user storage', () => {
  const windows = blackPaths({
    platform: 'win32',
    env: { LOCALAPPDATA: '/tmp/local-appdata' },
    home: '/tmp/home'
  });
  assert.equal(windows.root, path.join('/tmp/local-appdata', 'Platina-Reluzente', 'PokemonBlack'));
  assert.equal(windows.romPath, path.join(windows.root, 'roms', 'current.nds'));
  assert.equal(windows.processAppData, path.join(windows.root, 'process-appdata'));
  assert.notEqual(windows.romPath, path.join('/tmp/roaming-appdata', 'platina-reluzente-launcher', 'roms', 'current.nds'));

  const linux = blackPaths({
    platform: 'linux',
    env: { XDG_DATA_HOME: '/tmp/user-data' },
    home: '/tmp/home'
  });
  assert.equal(linux.root, path.join('/tmp/user-data', 'platina-reluzente', 'pokemon-black'));
  assert.equal(linux.processXdgDataHome, path.join(linux.root, 'process-data'));
  assert.notEqual(linux.extractDir, path.join('/tmp/user-data', 'platina-reluzente', 'platinum', 'extract'));
});

test('Black ROM identity requires the exact known SHA-1 and file size', () => {
  assert.equal(BLACK_ROM_SIZE, 268435456);
  assert.equal(validateBlackRomIdentity(BLACK_ROM_SIZE, BLACK_ROM_SHA1), true);
  assert.equal(validateBlackRomIdentity(BLACK_ROM_SIZE - 1, BLACK_ROM_SHA1), false);
  assert.equal(validateBlackRomIdentity(BLACK_ROM_SIZE, '0'.repeat(40)), false);
  assert.equal(validateBlackRomIdentity(BLACK_ROM_SIZE, null), false);
});

test('Black import metadata must identify the exact supported ROM revision', () => {
  const metadata = {
    size: BLACK_ROM_SIZE,
    sha1: BLACK_ROM_SHA1,
    sha256: 'a'.repeat(64)
  };
  assert.equal(isBlackImportedMetadataValid(metadata, BLACK_ROM_SIZE), true);
  assert.equal(isBlackImportedMetadataValid({ ...metadata, sha1: '0'.repeat(40) }, BLACK_ROM_SIZE), false);
  assert.equal(isBlackImportedMetadataValid(metadata, BLACK_ROM_SIZE - 1), false);
  assert.equal(isBlackImportedMetadataValid({ ...metadata, sha256: 'not-a-hash' }, BLACK_ROM_SIZE), false);
});

test('ROM inspection rejects a wrong file size before digesting the entire image', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-black-rom-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const file = path.join(root, 'selected.nds');
  await fs.writeFile(file, Buffer.alloc(0x200));
  await assert.rejects(inspectBlackRom(file), /Tamanho inesperado/);
  await assert.rejects(inspectBlackRom(path.join(root, 'missing.nds')), /ENOENT/);
  await assert.rejects(inspectBlackRom(path.join(root, 'wrong.bin')), /extensão \.nds/);
});

test('Black runtime discovery requires the expected local executable and Windows SDL3 DLL', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-black-runtime-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));

  const windows = path.join(root, 'windows');
  await fs.mkdir(windows);
  await fs.writeFile(path.join(windows, 'eidos.exe'), 'local user build');
  await assert.rejects(inspectBlackRuntime(windows, 'win32'), /SDL3\.dll/);
  await fs.writeFile(path.join(windows, 'SDL3.dll'), 'local dependency');
  await fs.writeFile(path.join(windows, 'portable.txt'), '');
  await assert.rejects(inspectBlackRuntime(windows, 'win32'), /portable\.txt/);
  await fs.rm(path.join(windows, 'portable.txt'));
  const winRuntime = await inspectBlackRuntime(windows, 'win32');
  assert.equal(winRuntime.executableName, 'eidos.exe');
  assert.equal(winRuntime.directory, windows);

  const linux = path.join(root, 'linux');
  await fs.mkdir(linux);
  await fs.writeFile(path.join(linux, 'eidos'), 'local user build');
  await fs.chmod(path.join(linux, 'eidos'), 0o755);
  const linuxRuntime = await inspectBlackRuntime(linux, 'linux');
  assert.equal(linuxRuntime.executableName, 'eidos');
  assert.equal(linuxRuntime.executable, path.join(linux, 'eidos'));

  await assert.rejects(inspectBlackRuntime(path.join(root, 'missing'), 'linux'), /ENOENT/);
});

test('Black launch spec keeps ROM, extraction, config and save paths separate', () => {
  const paths = blackPaths({
    platform: 'linux',
    env: { XDG_DATA_HOME: '/tmp/black-data' },
    home: '/tmp/home'
  });
  const runtime = {
    directory: '/tmp/eidos/build64/host',
    executable: '/tmp/eidos/build64/host/eidos',
    executableName: 'eidos'
  };
  const spec = createBlackLaunchSpec({
    runtime,
    paths,
    romPath: paths.romPath,
    romSha256: 'b'.repeat(64),
    platform: 'linux',
    env: { PATH: '/usr/bin', LD_LIBRARY_PATH: '/opt/custom/lib:/opt/another/lib' }
  });
  assert.deepEqual(spec.args, ['--rom', paths.romPath, '--data-root', paths.extractDir]);
  assert.equal(spec.cwd, runtime.directory);
  assert.equal(spec.env.EIDOS_HOME, paths.eidosHome);
  assert.equal(spec.env.XDG_DATA_HOME, paths.processXdgDataHome);
  assert.equal(spec.logPath, paths.logPath);
  assert.equal(spec.romSha256, 'b'.repeat(64));
  assert.equal(spec.env.PATH, '/usr/bin');
  assert.equal(
    spec.env.LD_LIBRARY_PATH,
    [runtime.directory, '/opt/custom/lib', '/opt/another/lib'].join(':')
  );
  assert.equal(spec.env.APPDATA, undefined);
});
