'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { launchNativeProcess } = require('../electron/native-process.cjs');

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

test('native process startup writes stdout and stderr to a persistent local log', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platina-native-log-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const logPath = path.join(root, 'logs', 'native-startup.log');
  const message = 'native-process-test';

  const result = await launchNativeProcess({
    executable: process.execPath,
    args: ['-e', "process.stdout.write('" + message + "-stdout\\n'); process.stderr.write('" + message + "-stderr\\n');"],
    cwd: root,
    env: process.env,
    logPath,
    platform: process.platform,
    romSha256: 'test-hash'
  });

  assert.equal(result.ok, true);
  assert.equal(result.logPath, logPath);
  assert.match(result.message, /não confirma a tela de título/);
  const log = await waitForLog(logPath, [message + '-stdout', message + '-stderr', 'spawn succeeded']);
  assert.match(log, /platform=/);
  assert.match(log, /rom_sha256=test-hash/);
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
  assert.match(result.message, /Falha ao iniciar o executável nativo/);
  const log = await fs.readFile(logPath, 'utf8');
  assert.match(log, /spawn error:/);
});
