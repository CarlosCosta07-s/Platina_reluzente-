'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const webRoot = path.join(__dirname, '..', 'web');
const html = fs.readFileSync(path.join(webRoot, 'index.html'), 'utf8');
const electronMain = fs.readFileSync(
  path.join(__dirname, '..', 'electron', 'main.cjs'),
  'utf8'
);

test('library announces Pokémon Black without exposing import or launch actions', () => {
  const start = html.indexOf('<article class="black-project-card"');
  assert.notEqual(start, -1, 'Black project card should be present in the launcher');
  const end = html.indexOf('</article>', start);
  assert.notEqual(end, -1, 'Black project card should be closed');
  const card = html.slice(start, end);

  assert.match(card, /Pokémon Black Version/);
  assert.match(card, /Em desenvolvimento/i);
  assert.match(card, /Runtime Black ainda não integrado/i);
  assert.match(card, /Importação de ROM e inicialização estão indisponíveis/i);
  assert.doesNotMatch(card, /<button\b/i, 'Black must not have an active action before its runtime exists');
});

test('Platinum ROM validation remains isolated and unchanged by the Black announcement', () => {
  assert.match(electronMain, /const ORIGINAL_ROM_SHA1 = '0862ec35b24de5c7e2dcb88c9eea0873110d755c'/);
  assert.match(electronMain, /ipcMain\.handle\('platina:import-rom'/);
  assert.match(electronMain, /ipcMain\.handle\('platina:launch-game'/);
  assert.doesNotMatch(electronMain, /BLACK_ROM_SHA1|importBlackRom|launchBlackGame/);
});
