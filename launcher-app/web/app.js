import { Filesystem, Directory } from '@capacitor/filesystem';
import { registerPlugin } from '@capacitor/core';
import { persistRomAtomically } from './rom-storage.js';

const NativeGame = registerPlugin('PlatinaGame');

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
    else if (!state.runtimeAvailable) { launchLabel.textContent = 'Motor nativo indisponível'; launchButton.disabled = true; }
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
    const header = new Uint8Array(await file.slice(0, 0x10).arrayBuffer());
    const title = String.fromCharCode(...header.slice(0, 12)).replace(/\0/g, '').trim();
    const code = String.fromCharCode(...header.slice(0x0c, 0x10));
    if (!title || !/^[A-Z0-9]{4}$/.test(code)) throw new Error('O cabeçalho não parece ser de uma ROM Nintendo DS válida.');
    if (code !== 'CPUE') throw new Error('Esta compilação nativa espera Pokémon Platinum USA Rev. 1 (código CPUE). A ROM selecionada não corresponde à versão de jogo configurada.');
  }
  function toBase64(buffer) {
    const bytes = new Uint8Array(buffer), chunks = [], chunkSize = 0x8000;
    for (let i = 0; i < bytes.length; i += chunkSize) chunks.push(String.fromCharCode(...bytes.subarray(i, Math.min(i + chunkSize, bytes.length))));
    return btoa(chunks.join(''));
  }
  async function importAndroidRom(file) {
    await validateRom(file);
    const { path: destination } = await persistRomAtomically({
      filesystem: Filesystem,
      directory: Directory.Data,
      file,
      toBase64
    });
    state.romName = file.name; state.romSize = file.size; state.romImported = true;
    localStorage.setItem('platinaRom', JSON.stringify({ name: file.name, size: file.size, storedPath: destination }));
    renderRom();
    setStatus('ROM validada e guardada no armazenamento privado. Toque em Iniciar jogo para abrir o motor nativo.');
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
    if (!state.runtimeAvailable) {
      setStatus('O pacote não contém todos os componentes do motor nativo.', true);
      return;
    }
    launchButton.disabled = true;
    setStatus(state.isAndroid ? 'Preparando os recursos e iniciando o jogo…' : 'Iniciando o executável nativo incluído no pacote…');
    try {
      const result = state.isAndroid
        ? await NativeGame.launchGame()
        : await window.platina.launchGame();
      setStatus(result.message || 'O motor nativo foi iniciado.', !result.ok);
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
      if (!state.runtimeAvailable) setStatus('O pacote desktop está incompleto: o executável nativo ou os recursos obrigatórios do jogo estão ausentes. Instale o pacote completo.', true);
      else setStatus(state.romImported ? 'ROM importada. O executável nativo já está incluído.' : 'Importe sua ROM .nds. O executável nativo já vem incluído.');
      return;
    }
    state.isAndroid = detectAndroid();
    if (state.isAndroid) {
      platformLabel.textContent = 'Android · ARM64 nativo';
      const runtime = await NativeGame.getRuntimeStatus().catch(() => ({ available: false }));
      state.runtimeAvailable = Boolean(runtime && runtime.available);
      try {
        const saved = JSON.parse(localStorage.getItem('platinaRom') || 'null');
        if (saved) {
          const file = await Filesystem.stat({ path: saved.storedPath || 'roms/current.nds', directory: Directory.Data });
          if (file) { state.romName = saved.name; state.romSize = saved.size || file.size || 0; state.romImported = true; }
        }
      } catch { localStorage.removeItem('platinaRom'); }
      renderRom(); renderPrimaryAction();
      if (!state.runtimeAvailable) {
        setStatus('Este APK não contém o runtime Android ARM64 completo. Instale o pacote integrado mais recente.', true);
      } else {
        setStatus(state.romImported ? 'ROM importada. O motor nativo está incluído neste APK.' : 'Importe sua ROM .nds; o motor nativo já vem incluído.');
      }
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
