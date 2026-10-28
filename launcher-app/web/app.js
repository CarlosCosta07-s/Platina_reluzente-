import { Filesystem, Directory } from '@capacitor/filesystem';

'use strict';
(function () {
  const $ = (id) => document.getElementById(id);
  const romButton = $('rom-button');
  const romPicker = $('rom-picker');
  const launchButton = $('launch-button');
  const launchLabel = $('launch-label');
  const launchStatus = $('launch-status');
  const platformLabel = $('platform-label');
  const romSummary = $('rom-summary');
  const state = { isAndroid: false, romImported: false, romName: '', romSize: 0, runtimeAvailable: false, importing: false };

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
    if (state.importing) { launchLabel.textContent = 'Importando ROM…'; launchButton.disabled = true; }
    else if (!state.romImported) { launchLabel.textContent = 'Importar ROM'; launchButton.disabled = false; }
    else if (state.isAndroid) { launchLabel.textContent = 'Motor Android em integração'; launchButton.disabled = true; }
    else if (!state.runtimeAvailable) { launchLabel.textContent = 'Executável ausente do pacote'; launchButton.disabled = true; }
    else { launchLabel.textContent = 'Iniciar jogo'; launchButton.disabled = false; }
  }
  function detectAndroid() {
    const cap = window.Capacitor;
    return Boolean((cap && typeof cap.getPlatform === 'function' && cap.getPlatform() === 'android')
      || /Android/i.test(navigator.userAgent));
  }
  async function validateRom(file) {
    if (!file || !/\.nds$/i.test(file.name || '')) throw new Error('Selecione uma ROM Nintendo DS com extensão .nds.');
    if (file.size < 0x200 || file.size > 512 * 1024 * 1024) throw new Error('Tamanho inválido para uma ROM Nintendo DS. Limite: 512 MiB.');
    const code = new Uint8Array(await file.slice(0x0c, 0x10).arrayBuffer());
    if (!/^[A-Z0-9]{4}$/.test(String.fromCharCode(...code))) throw new Error('O cabeçalho não parece ser de uma ROM Nintendo DS válida.');
  }
  function toBase64(buffer) {
    const bytes = new Uint8Array(buffer), chunks = [], chunkSize = 0x8000;
    for (let i = 0; i < bytes.length; i += chunkSize) chunks.push(String.fromCharCode(...bytes.subarray(i, Math.min(i + chunkSize, bytes.length))));
    return btoa(chunks.join(''));
  }
  async function importAndroidRom(file) {
    await validateRom(file);
    await Filesystem.writeFile({
      path: 'roms/current.nds', data: toBase64(await file.arrayBuffer()),
      directory: Directory.Data, recursive: true
    });
    state.romName = file.name; state.romSize = file.size; state.romImported = true;
    localStorage.setItem('platinaRom', JSON.stringify({ name: file.name, size: file.size, storedPath: 'roms/current.nds' }));
    renderRom();
    setStatus('ROM validada e salva no armazenamento privado. A execução do motor Android ainda está em integração.');
  }
  async function chooseRom() {
    if (state.isAndroid || !window.platina) { romPicker.click(); return; }
    state.importing = true; renderPrimaryAction();
    try {
      const result = await window.platina.importRom();
      if (!result || result.canceled) return;
      if (!result.ok) throw new Error(result.message || 'Não foi possível importar a ROM.');
      state.romName = result.name; state.romSize = result.size; state.romImported = true;
      localStorage.setItem('platinaRom', JSON.stringify({ name: result.name, size: result.size, sha256: result.sha256 }));
      renderRom();
      setStatus('ROM validada e copiada para os dados privados do aplicativo.');
    } catch (error) { setStatus('Falha ao importar ROM: ' + error.message, true); }
    finally { state.importing = false; renderPrimaryAction(); }
  }
  async function launchGame() {
    if (!state.romImported) { await chooseRom(); return; }
    if (state.isAndroid) {
      setStatus('A ROM está importada. A ponte de execução do motor nativo ainda não está integrada a este launcher.', true);
      return;
    }
    launchButton.disabled = true;
    setStatus('Iniciando o executável nativo incluído no pacote…');
    try {
      const result = await window.platina.launchGame();
      setStatus(result.message, !result.ok);
    } catch (error) { setStatus('Falha ao iniciar o jogo: ' + error.message, true); }
    finally { renderPrimaryAction(); }
  }
  async function initialize() {
    if (window.platina && typeof window.platina.getPlatform === 'function') {
      const value = await window.platina.getPlatform();
      platformLabel.textContent = value === 'win32' ? 'Windows x64' : value === 'linux' ? 'Linux desktop' : value;
      const [runtime, rom] = await Promise.all([window.platina.getRuntimeStatus(), window.platina.getImportedRom()]);
      state.runtimeAvailable = Boolean(runtime && runtime.available);
      if (rom) { state.romName = rom.name; state.romSize = rom.size || 0; state.romImported = true; }
      renderRom(); renderPrimaryAction();
      if (!state.runtimeAvailable) setStatus('O executável nativo não está incluído neste pacote. Use o pacote desktop completo.', true);
      else setStatus(state.romImported ? 'ROM importada. O executável nativo já está incluído.' : 'Importe sua ROM .nds. O executável nativo já vem incluído.');
      return;
    }
    state.isAndroid = detectAndroid();
    if (state.isAndroid) {
      platformLabel.textContent = 'Android · ARM64';
      try {
        const saved = JSON.parse(localStorage.getItem('platinaRom') || 'null');
        if (saved) {
          const file = await Filesystem.stat({ path: saved.storedPath || 'roms/current.nds', directory: Directory.Data });
          if (file) { state.romName = saved.name; state.romSize = saved.size || file.size || 0; state.romImported = true; }
        }
      } catch { localStorage.removeItem('platinaRom'); }
      renderRom(); renderPrimaryAction();
      setStatus(state.romImported ? 'ROM salva localmente. O motor Android ainda está em integração.' : 'Importe sua ROM .nds; ela será salva no armazenamento privado.');
      return;
    }
    platformLabel.textContent = 'Web de teste';
    renderRom(); renderPrimaryAction();
    setStatus('Use o pacote nativo de Windows/Linux ou o APK Android.');
  }

  romButton.addEventListener('click', chooseRom);
  launchButton.addEventListener('click', launchGame);
  romPicker.addEventListener('change', async () => {
    const file = romPicker.files && romPicker.files[0]; romPicker.value = '';
    if (!file) return;
    state.importing = true; renderPrimaryAction();
    try {
      if (!state.isAndroid) throw new Error('Use o seletor nativo para importar a ROM no PC.');
      await importAndroidRom(file);
    } catch (error) { setStatus('Falha ao importar ROM: ' + error.message, true); }
    finally { state.importing = false; renderPrimaryAction(); }
  });
  initialize().catch((error) => { setStatus('Falha ao inicializar launcher: ' + error.message, true); renderPrimaryAction(); });
}());
