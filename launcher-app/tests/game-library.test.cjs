'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const appRoot = path.join(__dirname, '..');
const webRoot = path.join(appRoot, 'web');
const html = fs.readFileSync(path.join(webRoot, 'index.html'), 'utf8');
const electronMain = fs.readFileSync(path.join(appRoot, 'electron', 'main.cjs'), 'utf8');
const blackRuntime = fs.readFileSync(path.join(appRoot, 'electron', 'black-runtime.cjs'), 'utf8');
const packageConfig = JSON.parse(fs.readFileSync(path.join(appRoot, 'package.json'), 'utf8'));

test('Black card provides import and start controls for a user-supplied local runtime', () => {
  const start = html.indexOf('<article class="black-project-card"');
  assert.notEqual(start, -1, 'Black project card should be present in the launcher');
  const end = html.indexOf('</article>', start);
  assert.notEqual(end, -1, 'Black project card should be closed');
  const card = html.slice(start, end);

  assert.match(card, /Pokémon Black Version/);
  assert.match(card, /black-runtime-button/);
  assert.match(card, /black-rom-button/);
  assert.match(card, /black-launch-button/);
  assert.match(card, /launcher não inclui o executável Black/i);
  assert.match(card, /contrato do runtime local/i);
  assert.match(electronMain, /ipcMain\.handle\('platina:black-status'/);
  assert.match(electronMain, /ipcMain\.handle\('platina:select-black-runtime'/);
  assert.match(electronMain, /ipcMain\.handle\('platina:import-black-rom'/);
  assert.match(electronMain, /ipcMain\.handle\('platina:launch-black-game'/);
});

test('Black runtime is selected locally and is not bundled in public launcher resources', () => {
  assert.match(blackRuntime, /function inspectBlackRuntime/);
  assert.match(blackRuntime, /function createBlackLaunchSpec/);
  assert.match(blackRuntime, /const BLACK_ROM_SHA1/);
  const resources = packageConfig.build.extraResources.map((resource) => resource.to);
  assert.deepEqual(resources, ['runtime'], 'only the existing Platinum runtime directory is bundled');
  assert.doesNotMatch(JSON.stringify(packageConfig.build), /eidos\.exe|SDL3\.dll|PokemonBlack/i);
});

test('Platinum ROM validation remains pinned to its own revision and IPC handlers', () => {
  assert.match(electronMain, /const ORIGINAL_ROM_SHA1 = '0862ec35b24de5c7e2dcb88c9eea0873110d755c'/);
  assert.match(electronMain, /ipcMain\.handle\('platina:import-rom'/);
  assert.match(electronMain, /ipcMain\.handle\('platina:launch-game'/);
  assert.match(electronMain, /path\.join\(app\.getPath\('userData'\), 'roms', 'current\.nds'\)/);
});
