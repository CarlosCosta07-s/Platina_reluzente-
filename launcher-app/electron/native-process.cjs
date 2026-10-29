'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

function appendLog(logPath, message) {
  try {
    fs.appendFileSync(logPath, message.endsWith('\n') ? message : message + '\n', 'utf8');
  } catch {
    // A logging error must not mask the primary process-launch result.
  }
}

function launchNativeProcess({
  executable,
  args = [],
  cwd,
  env = process.env,
  logPath,
  platform = process.platform,
  romSha256 = 'unavailable'
}) {
  if (typeof executable !== 'string' || !executable
      || !Array.isArray(args) || args.some((arg) => typeof arg !== 'string')
      || typeof cwd !== 'string' || !cwd
      || typeof logPath !== 'string' || !logPath) {
    return Promise.resolve({
      ok: false,
      message: 'Parâmetros inválidos para iniciar o executável nativo.'
    });
  }

  const absoluteLogPath = path.resolve(logPath);
  try {
    fs.mkdirSync(path.dirname(absoluteLogPath), { recursive: true });
    appendLog(absoluteLogPath, [
      '',
      '--- Native launch request: ' + new Date().toISOString() + ' ---',
      'platform=' + platform,
      'executable=' + executable,
      'working_directory=' + cwd,
      'rom_sha256=' + romSha256
    ].join('\n'));
  } catch (error) {
    return Promise.resolve({
      ok: false,
      message: 'Não foi possível preparar o log de inicialização: ' + error.message,
      logPath: absoluteLogPath
    });
  }

  let logDescriptor;
  try {
    logDescriptor = fs.openSync(absoluteLogPath, 'a');
  } catch (error) {
    appendLog(absoluteLogPath, 'log open failed: ' + error.message);
    return Promise.resolve({
      ok: false,
      message: 'Não foi possível abrir o log do jogo: ' + error.message,
      logPath: absoluteLogPath
    });
  }

  return new Promise((resolve) => {
    let descriptorOpen = true;
    let settled = false;

    const closeLogDescriptor = () => {
      if (!descriptorOpen) return;
      descriptorOpen = false;
      try { fs.closeSync(logDescriptor); } catch {}
    };

    const finish = (result) => {
      if (settled) return;
      settled = true;
      resolve({ ...result, logPath: absoluteLogPath });
    };

    let child;
    try {
      child = spawn(executable, args, {
        cwd,
        detached: true,
        stdio: ['ignore', logDescriptor, logDescriptor],
        shell: false,
        windowsHide: false,
        env
      });
    } catch (error) {
      closeLogDescriptor();
      appendLog(absoluteLogPath, 'spawn threw: ' + error.stack);
      finish({
        ok: false,
        message: 'Falha ao iniciar o executável nativo: ' + error.message
          + '. Consulte o log: ' + absoluteLogPath
      });
      return;
    }

    child.once('error', (error) => {
      closeLogDescriptor();
      appendLog(absoluteLogPath, 'spawn error: ' + (error.stack || error.message));
      finish({
        ok: false,
        message: 'Falha ao iniciar o executável nativo: ' + error.message
          + '. Consulte o log: ' + absoluteLogPath
      });
    });

    child.once('spawn', () => {
      closeLogDescriptor();
      child.unref();
      appendLog(absoluteLogPath, 'spawn succeeded; PID=' + child.pid);
      finish({
        ok: true,
        pid: child.pid,
        message: 'O processo nativo foi iniciado. Isso ainda não confirma a tela de título. '
          + 'Se a janela não aparecer, consulte o log: ' + absoluteLogPath
      });
    });
  });
}

module.exports = { launchNativeProcess };
