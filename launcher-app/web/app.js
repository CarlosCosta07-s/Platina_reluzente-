'use strict';

(function () {
  const $ = (id) => document.getElementById(id);
  const romButton = $('rom-button');
  const launchButton = $('launch-button');
  const launchLabel = $('launch-label');
  const launchStatus = $('launch-status');
  const platformLabel = $('platform-label');
  const romSummary = $('rom-summary');
  const state = {
    romImported: false,
    romName: '',
    romSize: 0,
    runtimeAvailable: false,
    runtimeDataAvailable: false,
    importing: false
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
    romSummary.textContent = state.romImported
      ? state.romName + (state.romSize ? ' · ' + formatSize(state.romSize) : '')
      : 'Nenhuma ROM importada.';
  }

  function renderPrimaryAction() {
    if (state.importing) {
      launchLabel.textContent = 'Importando ROM…';
      launchButton.disabled = true;
    } else if (!state.romImported) {
      launchLabel.textContent = 'Importar ROM';
      launchButton.disabled = false;
    } else if (!state.runtimeAvailable) {
      launchLabel.textContent = 'Motor nativo indisponível';
      launchButton.disabled = true;
    } else {
      launchLabel.textContent = 'Iniciar jogo';
      launchButton.disabled = false;
    }
  }

  async function chooseRom() {
    if (!window.platina || typeof window.platina.importRom !== 'function') {
      setStatus('Abra o launcher desktop de Windows ou Linux para importar uma ROM.', true);
      return;
    }
    state.importing = true;
    renderPrimaryAction();
    try {
      const result = await window.platina.importRom();
      if (!result || result.canceled) return;
      if (!result.ok) throw new Error(result.message || 'Não foi possível importar a ROM.');
      state.romName = result.name;
      state.romSize = result.size;
      state.romImported = true;
      localStorage.setItem('platinaRom', JSON.stringify({
        name: result.name,
        size: result.size,
        sha256: result.sha256
      }));
      renderRom();
      setStatus(state.runtimeDataAvailable
        ? 'ROM validada e copiada para os dados privados do aplicativo. Os dados locais do jogo já estão disponíveis.'
        : 'ROM validada e copiada. Os recursos do jogo serão extraídos localmente na primeira inicialização.');
    } catch (error) {
      setStatus('Falha ao importar ROM: ' + error.message, true);
    } finally {
      state.importing = false;
      renderPrimaryAction();
    }
  }

  async function launchGame() {
    if (!state.romImported) {
      await chooseRom();
      return;
    }
    if (!window.platina || typeof window.platina.launchGame !== 'function') {
      setStatus('Abra o launcher desktop de Windows ou Linux para iniciar o jogo.', true);
      return;
    }
    if (!state.runtimeAvailable) {
      setStatus('O pacote desktop está incompleto: o executável nativo não está disponível.', true);
      return;
    }
    launchButton.disabled = true;
    setStatus('Iniciando o executável nativo incluído no pacote…');
    try {
      const result = await window.platina.launchGame();
      setStatus(result.message || 'O motor nativo foi iniciado.', !result.ok);
    } catch (error) {
      setStatus('Falha ao iniciar o jogo: ' + error.message, true);
    } finally {
      renderPrimaryAction();
    }
  }

  async function initialize() {
    if (!window.platina || typeof window.platina.getPlatform !== 'function') {
      platformLabel.textContent = 'Windows / Linux desktop';
      renderRom();
      renderPrimaryAction();
      setStatus('Abra a versão desktop do launcher para importar sua ROM e iniciar o jogo.', true);
      return;
    }

    const value = await window.platina.getPlatform();
    platformLabel.textContent = value === 'win32'
      ? 'Windows x64'
      : value === 'linux'
        ? 'Linux desktop'
        : value;
    const [runtime, rom] = await Promise.all([
      window.platina.getRuntimeStatus(),
      window.platina.getImportedRom()
    ]);
    state.runtimeAvailable = Boolean(runtime && runtime.available);
    state.runtimeDataAvailable = Boolean(runtime && runtime.runtimeDataAvailable);
    if (rom) {
      state.romName = rom.name;
      state.romSize = rom.size || 0;
      state.romImported = true;
    }
    renderRom();
    renderPrimaryAction();
    if (!state.runtimeAvailable) {
      setStatus('O pacote desktop está incompleto: o executável nativo está ausente.', true);
    } else if (state.romImported) {
      setStatus(state.runtimeDataAvailable
        ? 'ROM importada. Os dados locais do jogo estão preparados.'
        : 'ROM importada. Os recursos serão extraídos localmente ao iniciar o jogo.');
    } else {
      setStatus(state.runtimeDataAvailable
        ? 'Importe sua ROM .nds. O executável nativo já vem incluído.'
        : 'Importe sua ROM .nds. O executável está incluído; os recursos do jogo serão extraídos localmente na primeira inicialização.');
    }
  }

  romButton.addEventListener('click', chooseRom);
  launchButton.addEventListener('click', launchGame);
  initialize().catch((error) => {
    setStatus('Falha ao inicializar launcher: ' + error.message, true);
    renderPrimaryAction();
  });
}());
