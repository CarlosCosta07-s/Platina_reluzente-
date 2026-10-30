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
    args: ['-e', "process.stdout.write('" + message + "-stdout\\n'); process.stderr.write('" + message + "-stderr\\n'); setTimeout(() => process.stderr.write('[Platina-Progress] renderer-ready\\n'), 100); setTimeout(() => process.stdout.write('[Platina-Progress] window-ready\\n'), 250); setTimeout(() => process.exit(0), 1500);"],
    cwd: workingDirectory,
    env: process.env,
    logPath,
    platform: process.platform,
    romSha256: 'test-hash'
  });

  assert.equal(result.ok, true);
  assert.equal(result.windowReady, true);
  assert.equal(result.logPath, logPath);
  const log = await waitForLog(logPath, [message + '-stdout', message + '-stderr', 'renderer-ready', 'window-ready', 'spawn succeeded', 'process exit: code=0']);
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
    args: ['-e', "process.stderr.write('[Platina-Progress] native-boot-start\\n[Platina-Progress] renderer-ready\\n'); setTimeout(() => process.exit(7), 1200);"],
    cwd: root,
    env: process.env,
    logPath,
    platform: process.platform
  });

  assert.equal(result.ok, false);
  assert.equal(result.logPath, logPath);
  assert.match(result.message, /encerrou antes de apresentar a primeira imagem/);
  assert.match(result.message, /Última etapa confirmada: renderer-ready/);
  const log = await fs.readFile(logPath, 'utf8');
  assert.match(log, /process exit: code=7/);
});

test('native launch times out without a first-frame marker and stops the hidden process', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-native-first-frame-timeout-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const logPath = path.join(root, 'first-frame-timeout.log');
  let sawRendererReadyWhileProcessWasActive = false;

  const result = await launchNativeProcess({
    executable: process.execPath,
    args: ['-e', "process.stderr.write('[Platina-Progress] renderer-ready\\nrenderer initialized; waiting for first frame\\n'); setTimeout(() => process.exit(0), 5000);"],
    cwd: root,
    env: process.env,
    logPath,
    platform: process.platform,
    startupTimeoutMs: 150,
    onProgress: (stage) => {
      if (stage === 'renderer-ready') {
        sawRendererReadyWhileProcessWasActive = hasActiveNativeProcess();
      }
    }
  });

  assert.equal(result.ok, false);
  assert.equal(result.startupTimedOut, true);
  assert.equal(sawRendererReadyWhileProcessWasActive, true);
  assert.match(result.message, /não apresentou a primeira imagem/);
  assert.match(result.message, /janela preta aparentemente congelada/);
  assert.match(result.message, /Última etapa confirmada: renderer-ready/);
  await waitForLog(logPath, ['first-frame timeout', 'process exit:']);
  assert.equal(hasActiveNativeProcess(), false);
  const log = await fs.readFile(logPath, 'utf8');
  assert.match(log, /renderer initialized; waiting for first frame/);
  assert.match(log, /process exit:/);
});

test('native heartbeat watchdog detects a render stall and reports recovery without killing the process', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-native-heartbeat-recovery-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const logPath = path.join(root, 'heartbeat-recovery.log');
  let resolveStall;
  let resolveRecovery;
  const stalled = new Promise((resolve) => { resolveStall = resolve; });
  const recovered = new Promise((resolve) => { resolveRecovery = resolve; });
  let processWasActiveAtStall = false;
  let processWasActiveAtRecovery = false;

  const result = await launchNativeProcess({
    executable: process.execPath,
    args: ['-e', "process.stderr.write('[Platina-Progress] window-ready\\n[Platina-Progress] heartbeat frame=1\\n'); setTimeout(() => process.stderr.write('[Platina-Progress] heartbeat frame=2\\n'), 450); setTimeout(() => process.exit(0), 850);"],
    cwd: root,
    env: process.env,
    logPath,
    platform: process.platform,
    heartbeatTimeoutMs: 150,
    onStall: (details) => {
      processWasActiveAtStall = hasActiveNativeProcess();
      resolveStall(details);
    },
    onRecovered: (details) => {
      processWasActiveAtRecovery = hasActiveNativeProcess();
      resolveRecovery(details);
    }
  });

  assert.equal(result.ok, true);
  assert.equal(result.windowReady, true);
  const stallDetails = await stalled;
  const recoveryDetails = await recovered;
  assert.equal(processWasActiveAtStall, true);
  assert.equal(processWasActiveAtRecovery, true);
  assert.ok(stallDetails.silentForMs >= 150);
  assert.equal(stallDetails.lastProgressStage, 'heartbeat');
  assert.equal(stallDetails.lastHeartbeatFrame, 1);
  assert.ok(recoveryDetails.resumedAt);
  await waitForLog(logPath, [
    'renderer heartbeat missing',
    'renderer heartbeat resumed',
    'process exit: code=0'
  ]);
  assert.equal(hasActiveNativeProcess(), false);
});

test('steady native heartbeats do not trigger the renderer-stall callback', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-native-heartbeat-steady-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const logPath = path.join(root, 'heartbeat-steady.log');
  let stalled = false;

  const result = await launchNativeProcess({
    executable: process.execPath,
    args: ['-e', "process.stderr.write('[Platina-Progress] window-ready\\n[Platina-Progress] heartbeat frame=1\\n'); let frame=1; const timer=setInterval(() => process.stderr.write('[Platina-Progress] heartbeat frame='+(++frame)+'\\n'), 35); setTimeout(() => { clearInterval(timer); process.exit(0); }, 250);"],
    cwd: root,
    env: process.env,
    logPath,
    platform: process.platform,
    heartbeatTimeoutMs: 100,
    onStall: () => { stalled = true; }
  });

  assert.equal(result.ok, true);
  await waitForLog(logPath, ['process exit: code=0']);
  assert.equal(stalled, false);
  assert.equal(hasActiveNativeProcess(), false);
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
    args: ['-e', "process.stdout.write('[Platina-Progress] window-ready\\n'); setTimeout(() => process.exit(0), 5000);"],
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
  await waitForLog(logPath, ['process exit: code=0'], 10000);
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
  assert.match(result.message, /encerrou antes de apresentar a primeira imagem/);
  assert.match(await fs.readFile(result.logPath, 'utf8'), /process exit: code=7/);
});
