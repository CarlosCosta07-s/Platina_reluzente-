'use strict';

(function () {
  const $ = (id) => document.getElementById(id);
  const romButton = $('rom-button');
  const romPicker = $('rom-picker');
  const executableButton = $('executable-button');
  const executableButtonSecondary = $('executable-button-secondary');
  const launchButton = $('launch-button');
  const launchLabel = $('launch-label');
  const launchStatus = $('launch-status');
  const platformLabel = $('platform-label');
  const romSummary = $('rom-summary');
  const executableSummary = $('executable-summary');

  const state = {
    platform: 'unknown',
    romName: '',
    romSize: 0,
    executablePath: ''
  };

  function formatSize(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0) return '';
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function setStatus(message, bad) {
    launchStatus.textContent = message;
    launchStatus.style.color = bad ? '#f1a7a7' : '#8c9cb1';
  }

  function renderRom() {
    if (!state.romName) {
      romSummary.textContent = 'Nenhuma ROM selecionada.';
      return;
    }
    romSummary.textContent = state.romName + (state.romSize ? ' · ' + formatSize(state.romSize) : '');
  }

  function renderExecutable() {
    if (!state.executablePath) {
      executableSummary.textContent = 'Nenhum executável selecionado.';
      return;
    }
    const parts = state.executablePath.split(/[\\/]/);
    executableSummary.textContent = parts[parts.length - 1] || state.executablePath;
  }

  async function initialize() {
    if (window.platina && typeof window.platina.getPlatform === 'function') {
      const value = await window.platina.getPlatform();
      state.platform = value === 'win32' ? 'Windows x64' : value === 'linux' ? 'Linux desktop' : value === 'darwin' ? 'macOS' : value;
      platformLabel.textContent = state.platform;
      state.executablePath = localStorage.getItem('platinaExecutablePath') || '';
      executableButton.disabled = false;
      executableButtonSecondary.disabled = false;
      launchButton.disabled = false;
      launchLabel.textContent = 'Iniciar jogo';
      setStatus('Launcher desktop pronto. Selecione o executável do pacote nativo.');
    } else if (/Android/i.test(navigator.userAgent)) {
      state.platform = 'Android · launcher';
      platformLabel.textContent = state.platform;
      executableButton.hidden = true;
      executableButtonSecondary.hidden = true;
      launchButton.disabled = true;
      launchLabel.textContent = 'Motor Android pendente';
      setStatus('Este APK serve para testar a interface. O motor gráfico Android ainda não está integrado.');
    } else {
      state.platform = 'Web de teste';
      platformLabel.textContent = state.platform;
      executableButton.hidden = true;
      executableButtonSecondary.hidden = true;
      launchButton.disabled = true;
      launchLabel.textContent = 'Disponível no desktop';
      setStatus('Abra o pacote desktop para iniciar um executável nativo.');
    }
    renderRom();
    renderExecutable();
  }

  async function chooseExecutable() {
    if (!window.platina) return;
    try {
      const result = await window.platina.selectExecutable();
      if (!result || result.canceled) return;
      state.executablePath = result.path;
      localStorage.setItem('platinaExecutablePath', state.executablePath);
      renderExecutable();
      setStatus('Executável selecionado. O launcher vai iniciá-lo a partir da pasta dele.');
    } catch (error) {
      setStatus('Erro ao selecionar executável: ' + error.message, true);
    }
  }

  async function chooseRom() {
    if (window.platina) {
      try {
        const result = await window.platina.selectRom();
        if (!result || result.canceled) return;
        state.romName = result.name;
        state.romSize = result.size || 0;
        renderRom();
        setStatus('ROM escolhida localmente. Ela não foi enviada nem importada para o motor.');
      } catch (error) {
        setStatus('Erro ao selecionar ROM: ' + error.message, true);
      }
      return;
    }
    romPicker.click();
  }

  async function launchGame() {
    if (!window.platina) {
      setStatus('O pacote atual não pode iniciar um executável nativo.', true);
      return;
    }
    if (!state.executablePath) {
      await chooseExecutable();
      if (!state.executablePath) return;
    }
    launchButton.disabled = true;
    setStatus('Iniciando o executável selecionado…');
    try {
      const result = await window.platina.launchGame(state.executablePath);
      setStatus(result.message, !result.ok);
    } catch (error) {
      setStatus('Falha ao iniciar: ' + error.message, true);
    } finally {
      launchButton.disabled = false;
    }
  }

  romButton.addEventListener('click', chooseRom);
  executableButton.addEventListener('click', chooseExecutable);
  executableButtonSecondary.addEventListener('click', chooseExecutable);
  launchButton.addEventListener('click', launchGame);
  romPicker.addEventListener('change', () => {
    const file = romPicker.files && romPicker.files[0];
    if (!file) return;
    state.romName = file.name;
    state.romSize = file.size;
    renderRom();
    setStatus('Arquivo selecionado no dispositivo. Nenhum dado foi enviado; a importação para o motor está pendente.');
  });

  initialize();
}());
