'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const webRoot = path.join(__dirname, '..', 'web');
const html = fs.readFileSync(path.join(webRoot, 'index.html'), 'utf8');
const life = fs.readFileSync(path.join(webRoot, 'life.js'), 'utf8');
const css = fs.readFileSync(path.join(webRoot, 'styles.css'), 'utf8');
const appJs = fs.readFileSync(path.join(webRoot, 'app.js'), 'utf8');

test('intro animation never leaves the UI hidden if scripting fails', () => {
  assert.match(html, /id="splash"/);
  assert.match(html, /classList\.add\('js-life'\)/);
  assert.match(html, /setTimeout\(function \(\) \{ document\.documentElement\.classList\.add\('is-ready'\); \}, 5000\)/);
  assert.match(css, /html\.js-life:not\(\.is-ready\) \.splash \{ display: flex; \}/);
  assert.match(css, /html\.js-life:not\(\.is-ready\) \[data-reveal\] \{ opacity: 0; \}/);
});

test('life layer respects reduced motion and treats storage as optional', () => {
  assert.match(life, /prefers-reduced-motion: reduce/);
  assert.match(life, /if \(!splash \|\| reduceMotion \|\| seenThisSession\)/);
  assert.match(life, /if \(!reduceMotion\) \{[\s\S]*sparkles/);
  assert.match(life, /try \{[\s\S]*localStorage[\s\S]*\} catch/);
  assert.match(life, /sessionStorage[\s\S]*catch/);
});

test('sparkles pause when the window is hidden and sounds are off by default', () => {
  assert.match(life, /visibilitychange/);
  assert.match(life, /cancelAnimationFrame/);
  assert.match(life, /let soundOn = store\('platina:sound'\) === '1'/);
});

test('session counter only counts launches that the launcher reports as ok', () => {
  assert.match(appJs, /new CustomEvent\('platina:launched', \{ detail: \{ ok: Boolean\(result && result\.ok\) \} \}\)/);
  assert.match(life, /if \(!event\.detail \|\| !event\.detail\.ok\) return;/);
  assert.match(html, /id="session-stats"/);
});
