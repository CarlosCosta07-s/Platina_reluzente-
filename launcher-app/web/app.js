'use strict';

(function () {
  const $ = (id) => document.getElementById(id);
  const romButton = $('rom-button');
  const launchButton = $('launch-button');
  const launchLabel = $('launch-label');
  const launchStatus = $('launch-status');
  const platformLabel = $('platform-label');
  const romSummary = $('rom-summary');
  const blackRuntimeButton = $('black-runtime-button');
  const blackRomButton = $('black-rom-button');
  const blackLaunchButton = $('black-launch-button');
  const blackStatusSymbol = $('black-status-symbol');
  const blackStatusTitle = $('black-status-title');
  const blackStatusCopy = $('black-status-copy');
  const blackLaunchStatus = $('black-launch-status');
  const state = {
    romImported: false,
    romName: '',
    romSize: 0,
    runtimeAvailable: false,
    runtimeDataAvailable: false,
    importing: false
  };
  const blackState = {
    runtimeAvailable: false,
    romImported: false,
    romName: '',
    romSize: 0,
    executableName: '',
    busy: false
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

  function setBlackStatus(title, message, failed) {
    if (blackStatusTitle) blackStatusTitle.textContent = title;
    if (blackStatusCopy) blackStatusCopy.textContent = message;
    if (blackStatusSymbol) {
      blackStatusSymbol.textContent = failed ? '!' : (blackState.runtimeAvailable && blackState.romImported ? '✓' : '…');
      blackStatusSymbol.classList.toggle('good', !failed && blackState.runtimeAvailable && blackState.romImported);
      blackStatusSymbol.classList.toggle('pending', failed || !blackState.runtimeAvailable || !blackState.romImported);
    }
  }

  function renderBlackActions() {
    const desktopAvailable = Boolean(window.platina)
      && typeof window.platina.getBlackStatus === 'function';
    if (blackRuntimeButton) {
      blackRuntimeButton.disabled = !desktopAvailable || blackState.busy;
      blackRuntimeButton.textContent = blackState.runtimeAvailable
        ? 'Trocar runtime Eidos local'
        : 'Selecionar runtime Eidos local';
    }
    if (blackRomButton) {
      blackRomButton.disabled = !desktopAvailable || blackState.busy;
      blackRomButton.textContent = blackState.romImported ? 'Trocar ROM Black' : 'Importar ROM Black';
    }
    if (blackLaunchButton) {
      blackLaunchButton.disabled = !desktopAvailable || blackState.busy
        || !blackState.runtimeAvailable || !blackState.romImported;
    }
  }

  async function refreshBlackStatus() {
    if (!window.platina || typeof window.platina.getBlackStatus !== 'function') {
      blackState.runtimeAvailable = false;
      blackState.romImported = false;
      renderBlackActions();
      setBlackStatus('Disponível no launcher desktop', 'Vincule um build Eidos local e importe sua ROM compatível na versão desktop.', false);
      return;
    }
    try {
      const value = await window.platina.getBlackStatus();
      blackState.runtimeAvailable = Boolean(value && value.runtimeAvailable);
      blackState.romImported = Boolean(value && value.romImported);
      blackState.romName = value && value.romName ? value.romName : '';
      blackState.romSize = value && value.romSize ? value.romSize : 0;
      blackState.executableName = value && value.executableName ? value.executableName : '';

      if (value && value.error && !blackState.runtimeAvailable) {
        setBlackStatus('Runtime local indisponível', value.error, true);
      } else if (blackState.runtimeAvailable && blackState.romImported) {
        setBlackStatus('Runtime e ROM prontos', blackState.executableName + ' vinculado e ROM verificada. Iniciar confirma apenas o processo, não a tela de título.', false);
      } else if (blackState.runtimeAvailable) {
        setBlackStatus('Runtime Eidos vinculado', 'Importe a ROM compatível de Pokémon Black para continuar.', false);
      } else {
        setBlackStatus('Runtime local necessário', 'Selecione a pasta build64/host do seu build Eidos local. O launcher não inclui esse executável.', false);
      }
    } catch (error) {
      setBlackStatus('Falha ao consultar o estado do Black', error.message, true);
    }
    renderBlackActions();
  }

  async function selectBlackRuntime() {
    if (!window.platina || typeof window.platina.selectBlackRuntime !== 'function') {
      setBlackStatus('Abra o launcher desktop', 'A seleção de runtime local está disponível na versão desktop.', true);
      return;
    }
    blackState.busy = true;
    renderBlackActions();
    try {
      const result = await window.platina.selectBlackRuntime();
      if (!result || result.canceled) return;
      if (!result.ok) throw new Error(result.message || 'Não foi possível validar o runtime Eidos.');
      await refreshBlackStatus();
      if (blackLaunchStatus) blackLaunchStatus.textContent = 'Runtime local vinculado; nenhum executável Black foi copiado para o pacote do launcher.';
    } catch (error) {
      setBlackStatus('Falha ao selecionar runtime', error.message, true);
    } finally {
      blackState.busy = false;
      renderBlackActions();
    }
  }

  async function importBlackRom() {
    if (!window.platina || typeof window.platina.importBlackRom !== 'function') {
      setBlackStatus('Abra o launcher desktop', 'A importação de Pokémon Black está disponível na versão desktop.', true);
      return;
    }
    blackState.busy = true;
    renderBlackActions();
    try {
      const result = await window.platina.importBlackRom();
      if (!result || result.canceled) return;
      if (!result.ok) throw new Error(result.message || 'Não foi possível importar a ROM de Pokémon Black.');
      await refreshBlackStatus();
      if (blackLaunchStatus) blackLaunchStatus.textContent = 'ROM verificada pelo hash completo e copiada para o armazenamento privado do Black.';
    } catch (error) {
      setBlackStatus('Falha ao importar ROM Black', error.message, true);
    } finally {
      blackState.busy = false;
      renderBlackActions();
    }
  }

  async function launchBlackGame() {
    if (!window.platina || typeof window.platina.launchBlackGame !== 'function') {
      setBlackStatus('Abra o launcher desktop', 'A inicialização do Black está disponível na versão desktop.', true);
      return;
    }
    if (!blackState.runtimeAvailable || !blackState.romImported) {
      await refreshBlackStatus();
      return;
    }
    blackState.busy = true;
    renderBlackActions();
    if (blackLaunchStatus) blackLaunchStatus.textContent = 'Iniciando o processo nativo local de Pokémon Black…';
    try {
      const result = await window.platina.launchBlackGame();
      if (!result || !result.ok) throw new Error(result && result.message ? result.message : 'Não foi possível iniciar o runtime Black.');
      if (blackLaunchStatus) blackLaunchStatus.textContent = result.message;
    } catch (error) {
      if (blackLaunchStatus) blackLaunchStatus.textContent = 'Falha ao iniciar Pokémon Black: ' + error.message;
      setBlackStatus('Falha ao iniciar Pokémon Black', error.message, true);
    } finally {
      blackState.busy = false;
      renderBlackActions();
    }
  }

  async function initialize() {
    if (!window.platina || typeof window.platina.getPlatform !== 'function') {
      platformLabel.textContent = 'Windows / Linux desktop';
      renderRom();
      renderPrimaryAction();
      renderBlackActions();
      setBlackStatus('Disponível no launcher desktop', 'Vincule um build Eidos local e importe sua ROM compatível na versão desktop.', false);
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
    await refreshBlackStatus();
  }

  romButton.addEventListener('click', chooseRom);
  launchButton.addEventListener('click', launchGame);
  if (blackRuntimeButton) blackRuntimeButton.addEventListener('click', selectBlackRuntime);
  if (blackRomButton) blackRomButton.addEventListener('click', importBlackRom);
  if (blackLaunchButton) blackLaunchButton.addEventListener('click', launchBlackGame);
  renderBlackActions();
  initialize().catch((error) => {
    setStatus('Falha ao inicializar launcher: ' + error.message, true);
    setBlackStatus('Falha ao inicializar launcher', error.message, true);
    renderPrimaryAction();
    renderBlackActions();
  });
}());
