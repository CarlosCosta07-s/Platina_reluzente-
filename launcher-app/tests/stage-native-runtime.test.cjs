'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { stageNativeRuntime, createExtractedPathManifest } = require('../scripts/stage-native-runtime.cjs');

function createFilesysCsv(root, entries = 340) {
  const file = path.join(root, 'platinum.us', 'filesys.csv');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const lines = ['Source File,Target File'];
  for (let index = 0; index < entries; index += 1) {
    const name = 'file-' + String(index).padStart(3, '0') + '.bin';
    lines.push('res/prebuilt/data/' + name + ',/data/' + name);
  }
  fs.writeFileSync(file, lines.join('\n') + '\n');
  return file;
}

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
  // Windows filesystems/runners do not expose POSIX executable bits in
  // fs.stat.mode. The Linux AppImage staging test must run on Unix; Windows
  // staging is covered independently below.
  if (process.platform === 'win32') {
    t.skip('Linux AppImage permission checks require POSIX file mode bits.');
    return;
  }
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-stage-runtime-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sourceRoot = path.join(root, 'build_linux', 'pokeplatinum');
  const destinationRoot = path.join(root, 'launcher-app', 'runtime');
  const dataManifestPath = createFilesysCsv(root);
  createRuntime(sourceRoot, 'linux');
  fs.writeFileSync(path.join(sourceRoot, 'save.bin'), 'user save should not be packaged');
  fs.writeFileSync(path.join(sourceRoot, 'sim_config.ini'), 'user settings should not be packaged');

  const result = stageNativeRuntime({ sourceRoot, destinationRoot, platform: 'linux', dataManifestPath });
  assert.equal(result.platform, 'linux');
  assert.equal(result.destination, destinationRoot);
  assert.equal(result.files, 2);
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
  assert.match(result.buildId, /^[a-f0-9]{64}$/);
  assert.notEqual(fs.statSync(path.join(destinationRoot, 'main')).mode & 0o111, 0);
  const manifest = JSON.parse(fs.readFileSync(path.join(destinationRoot, 'launcher-runtime-manifest.json'), 'utf8'));
  assert.equal(manifest.schemaVersion, 1);
  assert.equal(manifest.platform, 'linux');
  assert.equal(manifest.buildId, result.buildId);
  assert.deepEqual(manifest.files.map((entry) => entry.path), ['main', 'platinum-data-paths.txt']);
  const dataPaths = fs.readFileSync(path.join(destinationRoot, 'platinum-data-paths.txt'), 'utf8').split('\n');
  assert.equal(dataPaths[0], 'PLATINA_DATA_PATHS_V1');
  assert.equal(Number(dataPaths[1]), dataPaths.slice(2).filter(Boolean).length);
  assert.ok(dataPaths.includes('wazaeffect/we.arc'));
  assert.ok(dataPaths.includes('battle/skill/waza_seq.narc'));
  assert.equal(fs.existsSync(path.join(destinationRoot, 'data', 'file-000.bin')), false);
  assert.equal(manifest.files[0].sha256, require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(destinationRoot, 'main'))).digest('hex'));
});

test('stages a Windows runtime with main.exe without requiring Unix executable bits', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-stage-runtime-win-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sourceRoot = path.join(root, 'build_win64', 'pokeplatinum');
  const destinationRoot = path.join(root, 'launcher-app', 'runtime');
  const dataManifestPath = createFilesysCsv(root);
  createRuntime(sourceRoot, 'windows');

  const result = stageNativeRuntime({ sourceRoot, destinationRoot, platform: 'windows', dataManifestPath });
  assert.equal(result.executable, path.join(destinationRoot, 'main.exe'));
  assert.equal(result.files, 3);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'main.exe')), true);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'SDL2.dll')), true);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'header.bin')), false);
  assert.equal(fs.existsSync(path.join(destinationRoot, 'wazaeffect', 'we.arc')), false);
  const manifest = JSON.parse(fs.readFileSync(path.join(destinationRoot, 'launcher-runtime-manifest.json'), 'utf8'));
  assert.equal(manifest.platform, 'windows');
  assert.equal(manifest.buildId, result.buildId);
  assert.deepEqual(manifest.files.map((entry) => entry.path), ['SDL2.dll', 'main.exe', 'platinum-data-paths.txt']);
  assert.ok(fs.readFileSync(path.join(destinationRoot, 'platinum-data-paths.txt'), 'utf8').includes('data/file-000.bin'));
});

test('refuses to stage a Windows runtime that contains a ROM or patch and preserves the previous destination', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-stage-runtime-forbidden-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sourceRoot = path.join(root, 'build_win64', 'pokeplatinum');
  const destinationRoot = path.join(root, 'launcher-app', 'runtime');
  createRuntime(sourceRoot, 'windows');
  fs.writeFileSync(path.join(sourceRoot, 'local-rom.nds'), 'must never enter the packaged runtime');
  fs.mkdirSync(destinationRoot, { recursive: true });
  fs.writeFileSync(path.join(destinationRoot, 'preserve.txt'), 'previous destination');

  assert.throws(
    () => stageNativeRuntime({ sourceRoot, destinationRoot, platform: 'windows' }),
    /ROM\/save\/patch proibido/
  );
  assert.equal(fs.readFileSync(path.join(destinationRoot, 'preserve.txt'), 'utf8'), 'previous destination');
  assert.equal(fs.existsSync(path.join(destinationRoot, 'main.exe')), false);
});

test('refuses symbolic links in the native Windows runtime source', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-stage-runtime-link-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sourceRoot = path.join(root, 'build_win64', 'pokeplatinum');
  const destinationRoot = path.join(root, 'launcher-app', 'runtime');
  const outside = path.join(root, 'outside.txt');
  createRuntime(sourceRoot, 'windows');
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
    () => stageNativeRuntime({ sourceRoot, destinationRoot, platform: 'windows' }),
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

test('extracted path manifest rejects truncated, duplicated and traversing paths', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-data-paths-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const csv = createFilesysCsv(root, 340);
  const content = createExtractedPathManifest(csv);
  assert.match(content, /^PLATINA_DATA_PATHS_V1\n\d+\n/);
  assert.ok(content.includes('wazaeffect/we.arc'));
  assert.ok(content.includes('battle/skill/waza_seq.narc'));

  const truncated = path.join(root, 'truncated.csv');
  fs.writeFileSync(truncated, 'Source File,Target File\nres/a.bin,/data/a.bin\n');
  assert.throws(() => createExtractedPathManifest(truncated), /incompleto/);

  const duplicate = path.join(root, 'duplicate.csv');
  fs.writeFileSync(duplicate, 'Source File,Target File\nres/a.bin,/data/a.bin\nres/b.bin,/data/a.bin\n');
  assert.throws(() => createExtractedPathManifest(duplicate), /Destino duplicado/);

  const unsafe = path.join(root, 'unsafe.csv');
  const rows = ['Source File,Target File'];
  for (let index = 0; index < 300; index += 1) {
    rows.push('res/file-' + index + '.bin,/data/file-' + index + '.bin');
  }
  rows[1] = 'res/escape.bin,/data/../outside.bin';
  fs.writeFileSync(unsafe, rows.join('\n') + '\n');
  assert.throws(() => createExtractedPathManifest(unsafe), /Caminho inseguro/);
});
