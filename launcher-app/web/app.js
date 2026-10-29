'use strict';

(function () {
  const $ = (id) => document.getElementById(id);
  const platformLabel = $('platform-label');
  const platinumCard = $('platinum-library-card');
  const blackCard = $('black-library-card');
  const platinumDetail = $('platinum-detail');
  const blackDetail = $('black-detail');
  const launchButton = $('launch-button');
  const launchLabel = $('launch-label');
  const romButton = $('rom-button');
  const launchStatus = $('launch-status');
  const startupLogButton = $('startup-log-button');
  const romSummary = $('rom-summary');
  const blackRomButton = $('black-rom-button');
  const blackLaunchButton = $('black-launch-button');
  const blackRomSummary = $('black-rom-summary');
  const blackStatusSymbol = $('black-status-symbol');
  const blackStatusTitle = $('black-status-title');
  const blackStatusCopy = $('black-status-copy');
  const blackLaunchStatus = $('black-launch-status');

  const state = {
    selectedGame: 'platinum',
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
    runtimeError: '',
    busy: false
  };

  function formatSize(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0) return '';
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function setStatus(message, bad) {
    launchStatus.textContent = message;
    launchStatus.classList.toggle('status-error', Boolean(bad));
  }

  function selectGame(game) {
    state.selectedGame = game === 'black' ? 'black' : 'platinum';
    const blackSelected = state.selectedGame === 'black';
    platinumCard.classList.toggle('selected', !blackSelected);
    blackCard.classList.toggle('selected', blackSelected);
    platinumCard.setAttribute('aria-pressed', String(!blackSelected));
    blackCard.setAttribute('aria-pressed', String(blackSelected));
    platinumDetail.hidden = blackSelected;
    blackDetail.hidden = !blackSelected;
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
    romButton.disabled = state.importing;
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
      renderRom();
      setStatus(state.runtimeDataAvailable
        ? 'ROM verificada e importada. Os dados locais do jogo estão preparados.'
        : 'ROM verificada e importada. Os recursos necessários serão preparados localmente na primeira inicialização.');
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
      setStatus('O runtime nativo de Platinum não está disponível neste pacote.', true);
      return;
    }

    launchButton.disabled = true;
    setStatus('Iniciando Pokémon Platinum pelo launcher…');
    try {
      const result = await window.platina.launchGame();
      setStatus(result.message || 'O processo nativo foi iniciado.', !result.ok);
    } catch (error) {
      setStatus('Falha ao iniciar o jogo: ' + error.message, true);
    } finally {
      renderPrimaryAction();
    }
  }

  async function openStartupLog() {
    if (!window.platina || typeof window.platina.openStartupLog !== 'function') {
      setStatus('O log só pode ser aberto pela versão desktop do launcher.', true);
      return;
    }
    startupLogButton.disabled = true;
    try {
      const result = await window.platina.openStartupLog();
      if (!result || !result.ok) {
        throw new Error(result && result.message ? result.message : 'Não foi possível abrir o log de inicialização.');
      }
      setStatus(result.message || 'Log de inicialização aberto.');
    } catch (error) {
      setStatus('Falha ao abrir o log de inicialização: ' + error.message, true);
    } finally {
      startupLogButton.disabled = false;
    }
  }

  function renderBlackActions() {
    const desktopAvailable = Boolean(window.platina)
      && typeof window.platina.getBlackStatus === 'function';
    const canUseDesktop = desktopAvailable && !blackState.busy;
    blackRomButton.disabled = !canUseDesktop;
    blackRomButton.textContent = 'Importar / trocar ROM';
    blackLaunchButton.disabled = !canUseDesktop
      || !blackState.runtimeAvailable || !blackState.romImported;
    blackRomSummary.textContent = blackState.romImported
      ? blackState.romName + (blackState.romSize ? ' · ' + formatSize(blackState.romSize) : '')
      : 'Nenhuma ROM importada.';
  }

  function setBlackStatus(title, message, failed) {
    blackStatusTitle.textContent = title;
    blackStatusCopy.textContent = message;
    blackStatusSymbol.textContent = failed ? '!' : (blackState.runtimeAvailable && blackState.romImported ? '✓' : '…');
    blackStatusSymbol.classList.toggle('good', !failed && blackState.runtimeAvailable && blackState.romImported);
    blackStatusSymbol.classList.toggle('pending', failed || !blackState.runtimeAvailable || !blackState.romImported);
  }

  async function refreshBlackStatus() {
    if (!window.platina || typeof window.platina.getBlackStatus !== 'function') {
      blackState.runtimeAvailable = false;
      blackState.romImported = false;
      blackState.runtimeError = 'Abra a versão desktop para consultar e importar os dados locais.';
      setBlackStatus('Disponível na versão desktop', blackState.runtimeError, false);
      renderBlackActions();
      return;
    }

    try {
      const value = await window.platina.getBlackStatus();
      blackState.runtimeAvailable = Boolean(value && value.runtimeAvailable);
      blackState.romImported = Boolean(value && value.romImported);
      blackState.romName = value && value.romName ? value.romName : '';
      blackState.romSize = value && value.romSize ? value.romSize : 0;
      blackState.runtimeError = value && value.error ? value.error : '';

      if (!blackState.runtimeAvailable) {
        setBlackStatus('Runtime nativo não integrado', blackState.runtimeError
          || 'A execução será habilitada quando o runtime puder ser incluído legalmente no pacote único.', false);
        if (!blackState.romImported) {
          blackLaunchStatus.textContent = 'Você pode preparar a importação local, mas o jogo ainda não pode ser iniciado neste build.';
        } else {
          blackLaunchStatus.textContent = 'ROM importada e armazenada localmente. A inicialização aguarda o runtime integrado ao launcher.';
        }
      } else if (blackState.romImported) {
        setBlackStatus('Runtime e ROM disponíveis', 'A ROM compatível e o runtime nativo foram validados para uma tentativa de inicialização. A tela de título e a jogabilidade ainda não foram confirmadas.', false);
        blackLaunchStatus.textContent = 'O jogo será iniciado pelo mesmo launcher, sem selecionar outro executável.';
      } else {
        setBlackStatus('Runtime integrado', 'Importe uma cópia compatível de Pokémon Black para continuar.', false);
        blackLaunchStatus.textContent = 'A ROM fica em armazenamento privado, separado de Platinum.';
      }
    } catch (error) {
      blackState.runtimeAvailable = false;
      blackState.runtimeError = error.message;
      setBlackStatus('Falha ao consultar Pokémon Black', error.message, true);
    }
    renderBlackActions();
  }

  async function importBlackRom() {
    if (!window.platina || typeof window.platina.importBlackRom !== 'function') {
      setBlackStatus('Abra o launcher desktop', 'A importação da ROM de Pokémon Black está disponível na versão desktop.', true);
      return;
    }
    blackState.busy = true;
    renderBlackActions();
    try {
      const result = await window.platina.importBlackRom();
      if (!result || result.canceled) return;
      if (!result.ok) throw new Error(result.message || 'Não foi possível importar a ROM de Pokémon Black.');
      await refreshBlackStatus();
      if (blackLaunchStatus) {
        blackLaunchStatus.textContent = blackState.runtimeAvailable
          ? 'ROM verificada e guardada no armazenamento privado de Black.'
          : 'ROM verificada e guardada localmente. A inicialização será ativada quando o runtime interno for integrado.';
      }
    } catch (error) {
      setBlackStatus('Falha ao importar ROM Black', error.message, true);
      blackLaunchStatus.textContent = 'Falha ao importar Pokémon Black: ' + error.message;
    } finally {
      blackState.busy = false;
      renderBlackActions();
    }
  }

  async function launchBlackGame() {
    if (!window.platina || typeof window.platina.launchBlackGame !== 'function') {
      setBlackStatus('Abra o launcher desktop', 'A inicialização está disponível na versão desktop quando o runtime interno estiver integrado.', true);
      return;
    }
    if (!blackState.runtimeAvailable || !blackState.romImported) {
      await refreshBlackStatus();
      return;
    }

    blackState.busy = true;
    renderBlackActions();
    blackLaunchStatus.textContent = 'Iniciando Pokémon Black pelo launcher…';
    try {
      const result = await window.platina.launchBlackGame();
      if (!result || !result.ok) throw new Error(result && result.message
        ? result.message : 'Não foi possível iniciar Pokémon Black.');
      blackLaunchStatus.textContent = result.message;
    } catch (error) {
      blackLaunchStatus.textContent = 'Falha ao iniciar Pokémon Black: ' + error.message;
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
      setBlackStatus('Disponível na versão desktop', 'Abra o launcher desktop para consultar os motores nativos e importar ROMs.', false);
      setStatus('Abra a versão desktop do launcher para importar uma ROM e iniciar o jogo.', true);
      return;
    }

    const value = await window.platina.getPlatform();
    platformLabel.textContent = value === 'win32'
      ? 'Windows x64'
      : value === 'linux'
        ? 'Linux x86-64'
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
      setStatus('O runtime nativo de Platinum está ausente deste pacote.', true);
    } else if (state.romImported) {
      setStatus(state.runtimeDataAvailable
        ? 'ROM importada. Os dados locais do jogo estão preparados.'
        : 'ROM importada. Os recursos necessários serão extraídos localmente ao iniciar.');
    } else {
      setStatus(state.runtimeDataAvailable
        ? 'Importe uma ROM compatível. O motor nativo já vem incluído.'
        : 'Importe uma ROM compatível; os recursos necessários serão preparados localmente na primeira inicialização.');
    }
    await refreshBlackStatus();
  }

  document.querySelectorAll('[data-game-select]').forEach((card) => {
    card.addEventListener('click', () => selectGame(card.dataset.gameSelect));
  });
  launchButton.addEventListener('click', launchGame);
  romButton.addEventListener('click', chooseRom);
  startupLogButton.addEventListener('click', openStartupLog);
  blackRomButton.addEventListener('click', importBlackRom);
  blackLaunchButton.addEventListener('click', launchBlackGame);
  renderBlackActions();
  initialize().catch((error) => {
    setStatus('Falha ao inicializar o launcher: ' + error.message, true);
    setBlackStatus('Falha ao inicializar o launcher', error.message, true);
    renderPrimaryAction();
    renderBlackActions();
  });
}());
