'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { launchNativeProcess, runNativePrepare, hasActiveNativeProcess, onNativeProcessIdle } = require('../electron/native-process.cjs');

async function waitForLog(logPath, expectedFragments, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  let lastContent = '';
  while (Date.now() < deadline) {
    try {
      lastContent = await fs.readFile(logPath, 'utf8');
    } catch {}
    if (expectedFragments.every((fragment) => lastContent.includes(fragment))) {
      return lastContent;
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  assert.fail('Expected log fragments were not captured. Last log content:\n' + lastContent);
}

test('native preparation includes the last stderr diagnostic when it fails', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-native-prepare-diagnostic-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const logPath = path.join(root, 'logs', 'native-prepare.log');

  const result = await runNativePrepare({
    executable: process.execPath,
    args: ['-e', "process.stderr.write('[Platina] test diagnostic: overlay 9 unavailable\\n'); process.exit(4);"],
    cwd: root,
    env: process.env,
    logPath,
    platform: process.platform,
    timeoutMs: 5000
  });

  assert.equal(result.ok, false);
  assert.equal(result.code, 4);
  assert.match(result.message, /Detalhe: \[Platina\] test diagnostic: overlay 9 unavailable/);
  assert.match(result.message, /Consulte o log completo:/);
  const log = await fs.readFile(logPath, 'utf8');
  assert.match(log, /test diagnostic: overlay 9 unavailable/);
  assert.match(log, /prepare exit: code=4/);
});

test('native process startup handles working directories with spaces and accents', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-native-log-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const workingDirectory = path.join(root, 'Dados São João', 'Platiná Reluzente');
  await fs.mkdir(workingDirectory, { recursive: true });
  const logPath = path.join(workingDirectory, 'logs locais', 'native-startup.log');
  const message = 'native-process-test';

  const result = await launchNativeProcess({
    executable: process.execPath,
    args: ['-e', "process.stdout.write('" + message + "-stdout\\n'); process.stderr.write('" + message + "-stderr\\n'); setTimeout(() => process.exit(0), 3500);"],
    cwd: workingDirectory,
    env: process.env,
    logPath,
    platform: process.platform,
    romSha256: 'test-hash'
  });

  assert.equal(result.ok, true);
  assert.equal(result.logPath, logPath);
  assert.match(result.message, /janela do jogo não foi confirmada/);
  const log = await waitForLog(logPath, [message + '-stdout', message + '-stderr', 'spawn succeeded', 'process exit: code=0']);
  assert.match(log, /platform=/);
  assert.match(log, /rom_sha256=test-hash/);
  assert.match(log, /working_directory=.*Dados São João.*Platiná Reluzente/);
});

test('native process that exits during the initial startup window is reported as a failure', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-native-early-exit-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const logPath = path.join(root, 'logs', 'native-startup.log');

  const result = await launchNativeProcess({
    executable: process.execPath,
    args: ['-e', "setTimeout(() => process.exit(7), 1200);"],
    cwd: root,
    env: process.env,
    logPath,
    platform: process.platform
  });

  assert.equal(result.ok, false);
  assert.equal(result.logPath, logPath);
  assert.match(result.message, /encerrou durante a verificação inicial/);
  const log = await fs.readFile(logPath, 'utf8');
  assert.match(log, /process exit: code=7/);
});

test('native process startup failure is returned and recorded in the log', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-native-log-error-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const logPath = path.join(root, 'logs', 'native-startup.log');
  const result = await launchNativeProcess({
    executable: path.join(root, 'missing-native-executable'),
    cwd: root,
    env: process.env,
    logPath,
    platform: process.platform
  });

  assert.equal(result.ok, false);
  assert.equal(result.logPath, logPath);
  assert.match(result.message, /preparação segura do processo falhou/);
  const log = await fs.readFile(logPath, 'utf8');
  assert.match(log, /pre-launch validation failed/);
});

test('native launch rejects a symlink executable and a non-executable file', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-native-safe-path-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const target = path.join(root, 'target');
  const link = path.join(root, 'linked-executable');
  const nonExecutable = path.join(root, 'not-executable');
  await fs.writeFile(target, 'placeholder');
  await fs.writeFile(nonExecutable, 'placeholder');
  await fs.chmod(nonExecutable, 0o600);
  try {
    await fs.symlink(target, link);
  } catch (error) {
    if (error && ['EPERM', 'EACCES', 'ENOTSUP', 'ENOSYS'].includes(error.code)) {
      t.skip('This platform does not permit creating symlinks for tests.');
      return;
    }
    throw error;
  }

  const common = {
    args: [],
    cwd: root,
    env: process.env,
    platform: process.platform
  };
  const linked = await launchNativeProcess({
    ...common, executable: link, logPath: path.join(root, 'linked.log')
  });
  assert.equal(linked.ok, false);
  assert.match(linked.message, /arquivo regular válido/);

  if (process.platform !== 'win32') {
    const noExec = await launchNativeProcess({
      ...common, executable: nonExecutable, logPath: path.join(root, 'not-executable.log')
    });
    assert.equal(noExec.ok, false);
  }
});

test('native launch rejects a symlink used as the working directory', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-native-cwd-symlink-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const target = path.join(root, 'real-runtime');
  const link = path.join(root, 'runtime-link');
  await fs.mkdir(target);
  try {
    await fs.symlink(target, link, 'junction');
  } catch (error) {
    if (error && ['EPERM', 'EACCES', 'ENOTSUP', 'ENOSYS'].includes(error.code)) {
      t.skip('This platform does not permit creating directory symlinks for tests.');
      return;
    }
    throw error;
  }

  const result = await launchNativeProcess({
    executable: process.execPath,
    args: ['-e', 'process.exit(0);'],
    cwd: link,
    env: process.env,
    logPath: path.join(root, 'cwd-symlink.log'),
    platform: process.platform
  });

  assert.equal(result.ok, false);
  assert.match(result.message, /diretório real, sem link simbólico/);
});

test('native launcher does not start a second game while the first process is alive', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-native-single-game-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const logPath = path.join(root, 'first.log');
  const first = await launchNativeProcess({
    executable: process.execPath,
    args: ['-e', "setTimeout(() => process.exit(0), 5000);"],
    cwd: root,
    env: process.env,
    logPath,
    platform: process.platform
  });
  assert.equal(first.ok, true);
  assert.equal(hasActiveNativeProcess(), true);
  let idleNotified = false;
  onNativeProcessIdle(() => { idleNotified = true; });

  const second = await launchNativeProcess({
    executable: process.execPath,
    args: ['-e', 'process.exit(0);'],
    cwd: root,
    env: process.env,
    logPath: path.join(root, 'second.log'),
    platform: process.platform
  });
  assert.equal(second.ok, false);
  assert.match(second.message, /Outro jogo desta instalação já está em execução/);
  await waitForLog(logPath, ['process exit: code=0']);
  assert.equal(hasActiveNativeProcess(), false);
  assert.equal(idleNotified, true);
});

test('native launch reports an executable that exits during startup instead of a false success', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-native-early-exit-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const result = await launchNativeProcess({
    executable: process.execPath,
    args: ['-e', 'process.exit(7);'],
    cwd: root,
    env: process.env,
    logPath: path.join(root, 'early-exit.log'),
    platform: process.platform
  });
  assert.equal(result.ok, false);
  assert.match(result.message, /encerrou durante a verificação inicial/);
  assert.match(await fs.readFile(result.logPath, 'utf8'), /process exit: code=7/);
});
