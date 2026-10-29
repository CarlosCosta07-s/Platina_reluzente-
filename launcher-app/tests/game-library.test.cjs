'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const appRoot = path.join(__dirname, '..');
const webRoot = path.join(appRoot, 'web');
const html = fs.readFileSync(path.join(webRoot, 'index.html'), 'utf8');
const appJs = fs.readFileSync(path.join(webRoot, 'app.js'), 'utf8');
const css = fs.readFileSync(path.join(webRoot, 'styles.css'), 'utf8');
const electronMain = fs.readFileSync(path.join(appRoot, 'electron', 'main.cjs'), 'utf8');
const preload = fs.readFileSync(path.join(appRoot, 'electron', 'preload.cjs'), 'utf8');
const packageConfig = JSON.parse(fs.readFileSync(path.join(appRoot, 'package.json'), 'utf8'));
const blackRuntimeNotice = fs.readFileSync(path.join(appRoot, 'black-runtime', 'README.md'), 'utf8');

test('Platinum and Black are presented in one selectable launcher library', () => {
  assert.match(html, /id="platinum-library-card"/);
  assert.match(html, /id="black-library-card"/);
  assert.match(html, /Pokémon Platinum/);
  assert.match(html, /Pokémon Black Version/);
  assert.match(html, /data-game-select="platinum"/);
  assert.match(html, /data-game-select="black"/);
  assert.match(appJs, /function selectGame\(game\)/);
  assert.match(appJs, /platinumDetail\.hidden = blackSelected/);
  assert.match(appJs, /blackDetail\.hidden = !blackSelected/);
  assert.match(html, /aria-label="Escolher jogo"/);
  assert.match(css, /\.game-card\.selected/);
  assert.match(css, /grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(css, /@media \(max-width: 560px\)/);
  assert.match(css, /prefers-reduced-motion/);
});

test('Black import and launch use an internal runtime slot; no external runtime picker exists', () => {
  assert.match(html, /black-rom-button/);
  assert.match(html, /black-launch-button/);
  assert.doesNotMatch(html, /Selecionar runtime Eidos local|black-runtime-button/i);
  assert.match(electronMain, /function blackRuntimeDirectory\(\)/);
  assert.match(electronMain, /path\.join\(process\.resourcesPath, 'black-runtime', 'runtime'\)/);
  assert.match(electronMain, /ipcMain\.handle\('platina:black-status'/);
  assert.match(electronMain, /ipcMain\.handle\('platina:import-black-rom'/);
  assert.match(electronMain, /ipcMain\.handle\('platina:launch-black-game'/);
  assert.doesNotMatch(electronMain, /platina:select-black-runtime|showOpenDialog\(\{[\s\S]*openDirectory/);
  assert.doesNotMatch(preload, /selectBlackRuntime|platina:select-black-runtime/);
  assert.match(blackRuntimeNotice, /not included in public builds at this stage/i);
  assert.match(blackRuntimeNotice, /must never browse for or launch its executable manually/i);
});

test('launcher reserves the internal Black resource path without bundling an unlicensed runtime', () => {
  const resources = packageConfig.build.extraResources.map((resource) => resource.to);
  assert.deepEqual(resources, ['runtime', 'black-runtime/README.md']);
  assert.doesNotMatch(
    JSON.stringify(packageConfig.build),
    /"from":\s*"black-runtime"\s*,\s*"to":\s*"black-runtime"/
  );
  assert.doesNotMatch(JSON.stringify(packageConfig.build), /eidos\.exe|SDL3\.dll|PokemonBlack/i);
  assert.match(electronMain, /O runtime nativo de Pokémon Black ainda não está integrado/);
  assert.match(electronMain, /readBundledBlackRuntime\(\)/);
});

test('Platinum ROM validation and launch IPC remain part of the same app', () => {
  assert.match(electronMain, /const ORIGINAL_ROM_SHA1 = '0862ec35b24de5c7e2dcb88c9eea0873110d755c'/);
  assert.match(electronMain, /ipcMain\.handle\('platina:import-rom'/);
  assert.match(electronMain, /ipcMain\.handle\('platina:launch-game'/);
  assert.match(electronMain, /path\.join\(app\.getPath\('userData'\), 'roms', 'current\.nds'\)/);
});
