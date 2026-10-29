'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const STARTUP_CONFIRMATION_MS = 750;
let activeLaunch = null;

function appendLog(logPath, message) {
  try {
    fs.appendFileSync(logPath, message.endsWith('\n') ? message : message + '\n', 'utf8');
  } catch {
    // A logging error must not mask the primary process-launch result.
  }
}

function validateLaunchRequest({ executable, args, cwd, env, logPath, platform }) {
  if (typeof executable !== 'string' || !path.isAbsolute(executable)
      || !Array.isArray(args) || args.some((arg) => typeof arg !== 'string' || arg.includes('\0'))
      || typeof cwd !== 'string' || !path.isAbsolute(cwd)
      || typeof logPath !== 'string' || !path.isAbsolute(logPath)
      || !env || typeof env !== 'object' || Array.isArray(env)) {
    throw new TypeError('Parâmetros inválidos para iniciar o executável nativo.');
  }

  const executableStat = fs.lstatSync(executable);
  if (executableStat.isSymbolicLink() || !executableStat.isFile() || executableStat.size === 0) {
    throw new Error('O executável do jogo não é um arquivo regular válido.');
  }
  if (platform !== 'win32') {
    fs.accessSync(executable, fs.constants.X_OK);
  }

  const cwdStat = fs.statSync(cwd);
  if (!cwdStat.isDirectory()) {
    throw new Error('A pasta de trabalho do jogo não existe ou não é um diretório.');
  }

  try {
    const logStat = fs.lstatSync(logPath);
    if (logStat.isSymbolicLink() || !logStat.isFile()) {
      throw new Error('O caminho de log não pode ser link simbólico nem arquivo especial.');
    }
  } catch (error) {
    if (!error || error.code !== 'ENOENT') throw error;
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
  const absoluteLogPath = typeof logPath === 'string' ? path.resolve(logPath) : '';
  try {
    validateLaunchRequest({ executable, args, cwd, env, logPath: absoluteLogPath, platform });
  } catch (error) {
    return Promise.resolve({
      ok: false,
      message: 'A preparação segura do processo falhou: ' + error.message,
      ...(absoluteLogPath ? { logPath: absoluteLogPath } : {})
    });
  }

  if (activeLaunch) {
    return Promise.resolve({
      ok: false,
      message: 'Outro jogo desta instalação já está em execução. Feche a sessão atual antes de iniciar outro jogo.',
      logPath: absoluteLogPath,
      activePid: activeLaunch.pid || null
    });
  }

  try {
    fs.mkdirSync(path.dirname(absoluteLogPath), { recursive: true });
    const flags = fs.constants.O_APPEND | fs.constants.O_CREAT | fs.constants.O_WRONLY
      | (typeof fs.constants.O_NOFOLLOW === 'number' ? fs.constants.O_NOFOLLOW : 0);
    const descriptor = fs.openSync(absoluteLogPath, flags, 0o600);
    const header = [
      '',
      '--- Native launch request: ' + new Date().toISOString() + ' ---',
      'platform=' + platform,
      'executable=' + executable,
      'working_directory=' + cwd,
      'rom_sha256=' + (typeof romSha256 === 'string' ? romSha256 : 'unavailable')
    ].join('\n') + '\n';
    fs.writeSync(descriptor, header);
    fs.closeSync(descriptor);
  } catch (error) {
    return Promise.resolve({
      ok: false,
      message: 'Não foi possível preparar o log de inicialização: ' + error.message,
      logPath: absoluteLogPath
    });
  }

  let logDescriptor;
  try {
    const flags = fs.constants.O_APPEND | fs.constants.O_CREAT | fs.constants.O_WRONLY
      | (typeof fs.constants.O_NOFOLLOW === 'number' ? fs.constants.O_NOFOLLOW : 0);
    logDescriptor = fs.openSync(absoluteLogPath, flags, 0o600);
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
    let startupTimer = null;
    const token = { child: null, pid: null, startedAt: Date.now() };
    activeLaunch = token;

    const closeLogDescriptor = () => {
      if (!descriptorOpen) return;
      descriptorOpen = false;
      try { fs.closeSync(logDescriptor); } catch {}
    };

    const releaseLaunch = () => {
      if (activeLaunch === token) activeLaunch = null;
    };

    const clearStartupTimer = () => {
      if (startupTimer !== null) {
        clearTimeout(startupTimer);
        startupTimer = null;
      }
    };

    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearStartupTimer();
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
      token.child = child;
    } catch (error) {
      closeLogDescriptor();
      releaseLaunch();
      appendLog(absoluteLogPath, 'spawn threw: ' + (error.stack || error.message));
      finish({
        ok: false,
        message: 'Falha ao iniciar o executável nativo: ' + error.message
          + '. Consulte o log: ' + absoluteLogPath
      });
      return;
    }

    child.once('error', (error) => {
      closeLogDescriptor();
      releaseLaunch();
      appendLog(absoluteLogPath, 'spawn error: ' + (error.stack || error.message));
      finish({
        ok: false,
        message: 'Falha ao iniciar o executável nativo: ' + error.message
          + '. Consulte o log: ' + absoluteLogPath
      });
    });

    child.once('exit', (code, signal) => {
      clearStartupTimer();
      closeLogDescriptor();
      appendLog(absoluteLogPath, 'process exit: code=' + code + ' signal=' + (signal || 'none'));
      releaseLaunch();
      if (!settled) {
        finish({
          ok: false,
          message: 'O processo nativo encerrou durante a verificação inicial (código '
            + code + ', sinal ' + (signal || 'nenhum') + '). Consulte o log: ' + absoluteLogPath
        });
      }
    });

    child.once('spawn', () => {
      token.pid = child.pid || null;
      appendLog(absoluteLogPath, 'spawn succeeded; PID=' + child.pid);
      closeLogDescriptor();

      // Catch immediate loader/runtime failures rather than displaying a
      // successful launch for a process that dies as soon as it starts.
      startupTimer = setTimeout(() => {
        if (settled) return;
        child.unref();
        finish({
          ok: true,
          pid: child.pid,
          message: 'O processo nativo permaneceu ativo durante a verificação inicial. Isso não comprova que a tela de título apareceu. Consulte o log: '
            + absoluteLogPath
        });
      }, STARTUP_CONFIRMATION_MS);
    });
  });
}

function hasActiveNativeProcess() {
  return Boolean(activeLaunch);
}

module.exports = { launchNativeProcess, hasActiveNativeProcess };
