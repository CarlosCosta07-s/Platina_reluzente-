'use strict';
const fs = require('node:fs');
const path = require('node:path');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '..');
const source = path.join(root, 'web');
const output = path.join(root, 'web-dist');
fs.rmSync(output, { recursive: true, force: true });
fs.mkdirSync(output, { recursive: true });
fs.copyFileSync(path.join(source, 'index.html'), path.join(output, 'index.html'));
fs.copyFileSync(path.join(source, 'styles.css'), path.join(output, 'styles.css'));
esbuild.buildSync({
  entryPoints: [path.join(source, 'app.js')],
  outfile: path.join(output, 'app.js'),
  bundle: true,
  platform: 'browser',
  format: 'iife',
  target: ['es2020']
});
if (!fs.statSync(path.join(output, 'app.js')).size) throw new Error('Launcher web bundle is empty.');
console.log('Built launcher web bundle with Capacitor Filesystem support.');
