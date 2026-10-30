'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

// The launcher waits for a real SDL first-frame marker before hiding itself.
const WINDOW_READY_TIMEOUT_MS = 60 * 1000;
// The runtime emits a heartbeat every five seconds; allow three intervals.
const HEARTBEAT_TIMEOUT_MS = 15 * 1000;
const STARTUP_OUTPUT_TAIL_CHARS = 8192;
let activeLaunch = null;
const idleCallbacks = new Set();

function appendLog(logPath, message) {
  try {
    fs.appendFileSync(logPath, message.endsWith('\n') ? message : message + '\n', 'utf8');
  } catch {
    // A logging error must not mask the primary process-launch result.
  }
}

function appendSafeDiagnostic(logPath, message) {
  if (typeof logPath !== 'string' || !path.isAbsolute(logPath)) return;
  try {
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    try {
      const stat = fs.lstatSync(logPath);
      if (stat.isSymbolicLink() || !stat.isFile()) return;
    } catch (error) {
      if (!error || error.code !== 'ENOENT') return;
    }
    const flags = fs.constants.O_APPEND | fs.constants.O_CREAT | fs.constants.O_WRONLY
      | (typeof fs.constants.O_NOFOLLOW === 'number' ? fs.constants.O_NOFOLLOW : 0);
    const descriptor = fs.openSync(logPath, flags, 0o600);
    try {
      fs.writeSync(descriptor, '\n' + new Date().toISOString() + ' ' + message + '\n');
    } finally {
      fs.closeSync(descriptor);
    }
  } catch {
    // Diagnostics are best-effort and must not replace the validation error.
  }
}

function notifyIdleCallbacks() {
  const callbacks = Array.from(idleCallbacks);
  idleCallbacks.clear();
  for (const callback of callbacks) {
    try { callback(); } catch {}
  }
}

function onNativeProcessIdle(callback) {
  if (typeof callback !== 'function') {
    throw new TypeError('O callback de encerramento deve ser uma função.');
  }
  if (!activeLaunch) {
    callback();
    return () => {};
  }
  idleCallbacks.add(callback);
  return () => idleCallbacks.delete(callback);
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

  const cwdStat = fs.lstatSync(cwd);
  if (cwdStat.isSymbolicLink() || !cwdStat.isDirectory()) {
    throw new Error('A pasta de trabalho do jogo deve ser um diretório real, sem link simbólico.');
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
  romSha256 = 'unavailable',
  onProgress = () => {},
  onWindowReady = () => {},
  onStall = () => {},
  onRecovered = () => {},
  startupTimeoutMs = WINDOW_READY_TIMEOUT_MS,
  heartbeatTimeoutMs = HEARTBEAT_TIMEOUT_MS
}) {
  const absoluteLogPath = typeof logPath === 'string' ? path.resolve(logPath) : '';
  if (typeof onProgress !== 'function' || typeof onWindowReady !== 'function'
      || typeof onStall !== 'function' || typeof onRecovered !== 'function'
      || !Number.isFinite(startupTimeoutMs) || startupTimeoutMs < 1
      || !Number.isFinite(heartbeatTimeoutMs) || heartbeatTimeoutMs < 1) {
    return Promise.resolve({
      ok: false,
      message: 'Parâmetros inválidos para acompanhar a primeira imagem do processo nativo.',
      ...(absoluteLogPath ? { logPath: absoluteLogPath } : {})
    });
  }

  try {
    validateLaunchRequest({ executable, args, cwd, env, logPath: absoluteLogPath, platform });
  } catch (error) {
    if (absoluteLogPath) appendSafeDiagnostic(absoluteLogPath, 'pre-launch validation failed: ' + error.message);
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
    let heartbeatTimer = null;
    let lastHeartbeatAt = 0;
    let heartbeatStalled = false;
    let diagnosticTail = '';
    const pendingOutput = { stdout: '', stderr: '' };
    const token = {
      child: null,
      pid: null,
      startedAt: Date.now(),
      windowReady: false
    };
    activeLaunch = token;

    const closeLogDescriptor = () => {
      if (!descriptorOpen) return;
      descriptorOpen = false;
      try { fs.closeSync(logDescriptor); } catch {}
    };

    const writeLogChunk = (chunk) => {
      if (!descriptorOpen) return;
      try {
        fs.writeSync(logDescriptor, chunk);
      } catch (error) {
        appendSafeDiagnostic(absoluteLogPath, 'startup log write failed: ' + error.message);
      }
    };

    const releaseLaunch = () => {
      if (activeLaunch === token) {
        activeLaunch = null;
        notifyIdleCallbacks();
      }
    };

    const clearStartupTimer = () => {
      if (startupTimer !== null) {
        clearTimeout(startupTimer);
        startupTimer = null;
      }
    };

    const clearHeartbeatTimer = () => {
      if (heartbeatTimer !== null) {
        clearTimeout(heartbeatTimer);
        heartbeatTimer = null;
      }
    };

    const scheduleHeartbeatWatchdog = () => {
      clearHeartbeatTimer();
      if (!token.windowReady || !lastHeartbeatAt || heartbeatStalled) return;
      heartbeatTimer = setTimeout(() => {
        heartbeatTimer = null;
        if (!token.windowReady || heartbeatStalled) return;
        const silentForMs = Date.now() - lastHeartbeatAt;
        if (silentForMs < heartbeatTimeoutMs) {
          scheduleHeartbeatWatchdog();
          return;
        }
        heartbeatStalled = true;
        appendLog(
          absoluteLogPath,
          'renderer heartbeat missing for ' + silentForMs + ' ms; native process remains active'
        );
        try {
          onStall({
            pid: token.pid,
            silentForMs,
            lastHeartbeatAt: new Date(lastHeartbeatAt).toISOString()
          });
        } catch (error) {
          appendLog(absoluteLogPath, 'heartbeat stall callback failed: ' + error.message);
        }
      }, heartbeatTimeoutMs);
    };

    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearStartupTimer();
      resolve({ ...result, logPath: absoluteLogPath });
    };

    const diagnosticSummary = () => diagnosticTail
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !/^\[Platina-Progress\]/.test(line))
      .slice(-3)
      .join(' | ');

    const processLine = (line) => {
      const match = /^\[Platina-Progress\]\s+([a-z][a-z0-9_-]*)\b/i.exec(line.trim());
      if (!match) return;
      const stage = match[1].toLowerCase();
      try { onProgress(stage); } catch (error) {
        appendLog(absoluteLogPath, 'startup progress callback failed: ' + error.message);
      }

      if (stage === 'heartbeat' && token.windowReady) {
        lastHeartbeatAt = Date.now();
        if (heartbeatStalled) {
          heartbeatStalled = false;
          appendLog(absoluteLogPath, 'renderer heartbeat resumed; completed game frames are being presented again');
          try {
            onRecovered({
              pid: token.pid,
              resumedAt: new Date(lastHeartbeatAt).toISOString()
            });
          } catch (error) {
            appendLog(absoluteLogPath, 'heartbeat recovery callback failed: ' + error.message);
          }
        }
        scheduleHeartbeatWatchdog();
        return;
      }

      if (stage !== 'window-ready' || token.windowReady) return;

      token.windowReady = true;
      lastHeartbeatAt = Date.now();
      scheduleHeartbeatWatchdog();
      clearStartupTimer();
      appendLog(absoluteLogPath, 'first game frame presented; native window is now visible');
      try {
        onWindowReady({ pid: token.pid, elapsedMs: Date.now() - token.startedAt });
      } catch (error) {
        appendLog(absoluteLogPath, 'window-ready callback failed: ' + error.message);
      }
      finish({
        ok: true,
        pid: token.pid,
        windowReady: true,
        message: 'O runtime apresentou a primeira imagem do jogo. A janela nativa está pronta.'
      });
    };

    const handleOutput = (streamName, chunk) => {
      const output = chunk.toString('utf8');
      writeLogChunk(output);
      diagnosticTail = (diagnosticTail + output).slice(-STARTUP_OUTPUT_TAIL_CHARS);
      const combined = pendingOutput[streamName] + output;
      const lines = combined.split(/\r?\n/);
      pendingOutput[streamName] = lines.pop() || '';
      for (const line of lines) processLine(line);
    };

    const flushPendingOutput = () => {
      for (const streamName of ['stdout', 'stderr']) {
        if (pendingOutput[streamName]) {
          processLine(pendingOutput[streamName]);
          pendingOutput[streamName] = '';
        }
      }
    };

    let child;
    try {
      child = spawn(executable, args, {
        cwd,
        detached: true,
        stdio: ['ignore', 'pipe', 'pipe'],
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

    child.stdout.on('data', (chunk) => handleOutput('stdout', chunk));
    child.stderr.on('data', (chunk) => handleOutput('stderr', chunk));

    child.once('error', (error) => {
      clearStartupTimer();
      clearHeartbeatTimer();
      closeLogDescriptor();
      releaseLaunch();
      appendLog(absoluteLogPath, 'spawn error: ' + (error.stack || error.message));
      finish({
        ok: false,
        message: 'Falha ao iniciar o executável nativo: ' + error.message
          + '. Consulte o log: ' + absoluteLogPath
      });
    });

    child.once('close', (code, signal) => {
      flushPendingOutput();
      clearStartupTimer();
      clearHeartbeatTimer();
      closeLogDescriptor();
      appendLog(absoluteLogPath, 'process exit: code=' + code + ' signal=' + (signal || 'none'));
      releaseLaunch();
      if (!settled) {
        const diagnostic = diagnosticSummary();
        finish({
          ok: false,
          pid: token.pid,
          message: 'O processo nativo encerrou antes de apresentar a primeira imagem (código '
            + code + ', sinal ' + (signal || 'nenhum') + ').'
            + (diagnostic ? ' Último diagnóstico: ' + diagnostic + '.' : '')
            + ' Consulte o log: ' + absoluteLogPath
        });
      }
    });

    child.once('spawn', () => {
      token.pid = child.pid || null;
      appendLog(absoluteLogPath, 'spawn succeeded; PID=' + child.pid);
      if (settled || token.windowReady) return;

      startupTimer = setTimeout(() => {
        if (settled || token.windowReady) return;
        const diagnostic = diagnosticSummary();
        appendLog(
          absoluteLogPath,
          'first-frame timeout after ' + startupTimeoutMs + ' ms; requesting process termination'
        );
        finish({
          ok: false,
          pid: child.pid || null,
          startupTimedOut: true,
          message: 'O runtime não apresentou a primeira imagem em '
            + Math.ceil(startupTimeoutMs / 1000)
            + ' segundos. Para evitar uma janela preta aparentemente congelada, o launcher solicitou o encerramento do processo e permaneceu disponível.'
            + (diagnostic ? ' Último diagnóstico: ' + diagnostic + '.' : '')
            + ' Consulte o log: ' + absoluteLogPath
        });
        try {
          if (!child.kill()) {
            appendLog(absoluteLogPath, 'process termination request was not accepted');
          }
        } catch (error) {
          appendLog(absoluteLogPath, 'process termination request failed: ' + error.message);
        }
      }, startupTimeoutMs);
    });
  });
}

const PREPARE_TIMEOUT_MS = 20 * 60 * 1000;
let preparing = false;

/**
 * Run the native executable in its "--platina-prepare" mode: verify/extract the
 * game data from the imported ROM BEFORE any game window exists (the approach
 * used by gen1recomp: a separate import/prepare phase with visible progress,
 * then launch). Output is appended to the same startup log. Resolves with
 * { ok, code, message }.
 */
function runNativePrepare({ executable, args = [], cwd, env = process.env, logPath, platform = process.platform, romSha256 = 'unavailable', onProgress = () => {}, timeoutMs = PREPARE_TIMEOUT_MS }) {
  const absoluteLogPath = typeof logPath === 'string' ? path.resolve(logPath) : '';
  try {
    validateLaunchRequest({ executable, args, cwd, env, logPath: absoluteLogPath, platform });
  } catch (error) {
    if (absoluteLogPath) appendSafeDiagnostic(absoluteLogPath, 'prepare validation failed: ' + error.message);
    return Promise.resolve({ ok: false, code: null, message: 'A preparação segura do processo falhou: ' + error.message });
  }
  if (preparing || activeLaunch) {
    return Promise.resolve({ ok: false, code: null, message: 'Já existe uma preparação ou um jogo em execução.' });
  }
  appendSafeDiagnostic(absoluteLogPath, '--- Native prepare phase --- platform=' + platform + ' rom_sha256=' + romSha256);

  preparing = true;
  return new Promise((resolve) => {
    let settled = false;
    let pending = '';
    let stderrTail = '';
    let timer = null;
    const done = (result) => {
      if (settled) return;
      settled = true;
      preparing = false;
      if (timer) clearTimeout(timer);
      resolve(result);
    };
    const handleText = (text, fromStderr = false) => {
      appendLog(absoluteLogPath, text);
      if (fromStderr) stderrTail = (stderrTail + text).slice(-4096);
      pending += text;
      const lines = pending.split(/\r?\n/);
      pending = lines.pop();
      for (const line of lines) {
        const match = /^\[Platina-Progress\]\s+(\w+)/.exec(line);
        if (match) { try { onProgress(match[1]); } catch {} }
      }
    };
    let child;
    try {
      child = spawn(executable, args, { cwd, shell: false, windowsHide: true, env, stdio: ['ignore', 'pipe', 'pipe'] });
    } catch (error) {
      appendLog(absoluteLogPath, 'prepare spawn threw: ' + error.message);
      done({ ok: false, code: null, message: 'Falha ao iniciar a preparação: ' + error.message });
      return;
    }
    child.stdout.on('data', (chunk) => handleText(chunk.toString('utf8')));
    child.stderr.on('data', (chunk) => handleText(chunk.toString('utf8'), true));
    child.once('error', (error) => {
      appendLog(absoluteLogPath, 'prepare error: ' + error.message);
      done({ ok: false, code: null, message: 'Falha ao iniciar a preparação: ' + error.message });
    });
    child.once('exit', (code, signal) => {
      appendLog(absoluteLogPath, 'prepare exit: code=' + code + ' signal=' + (signal || 'none'));
      if (code === 0) {
        done({ ok: true, code });
      } else {
        const diagnosticLines = stderrTail
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter((line) => line && !/^\[Platina-Progress\]/.test(line));
        const diagnostic = diagnosticLines.slice(-3).join(' | ');
        done({
          ok: false,
          code,
          message: 'A preparação dos dados do jogo falhou (código ' + code + ').'
            + (diagnostic ? ' Detalhe: ' + diagnostic : '')
            + ' Consulte o log completo: ' + absoluteLogPath
        });
      }
    });
    timer = setTimeout(() => {
      appendLog(absoluteLogPath, 'prepare timeout after ' + timeoutMs + ' ms; killing process');
      try { child.kill(); } catch {}
      done({ ok: false, code: null, message: 'A preparação dos dados excedeu o tempo limite. Consulte o log: ' + absoluteLogPath });
    }, timeoutMs);
  });
}

function hasActiveNativeProcess() {
  return Boolean(activeLaunch);
}

module.exports = { launchNativeProcess, runNativePrepare, hasActiveNativeProcess, onNativeProcessIdle };
