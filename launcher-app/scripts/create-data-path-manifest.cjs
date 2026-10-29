'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { createExtractedPathManifest } = require('./stage-native-runtime.cjs');

function writeDataPathManifest({ inputCsvPath, outputPath }) {
  if (typeof inputCsvPath !== 'string' || !path.isAbsolute(inputCsvPath)
      || typeof outputPath !== 'string' || !path.isAbsolute(outputPath)) {
    throw new TypeError('Informe caminhos absolutos para filesys.csv e para o manifesto de saída.');
  }
  const outputStat = (() => {
    try { return fs.lstatSync(outputPath); }
    catch (error) {
      if (error && error.code === 'ENOENT') return null;
      throw error;
    }
  })();
  if (outputStat && (outputStat.isSymbolicLink() || !outputStat.isFile())) {
    throw new Error('O destino do manifesto precisa ser um arquivo regular, sem link simbólico.');
  }
  if (outputStat) {
    throw new Error('O manifesto de saída já existe; não será sobrescrito: ' + outputPath);
  }

  const contents = createExtractedPathManifest(inputCsvPath);
  fs.writeFileSync(outputPath, contents, { encoding: 'utf8', flag: 'wx', mode: 0o644 });
  return { outputPath, entries: Number(contents.split('\n')[1]) };
}

if (require.main === module) {
  const args = process.argv.slice(2);
  const inputIndex = args.indexOf('--input');
  const outputIndex = args.indexOf('--output');
  if (inputIndex < 0 || outputIndex < 0 || !args[inputIndex + 1] || !args[outputIndex + 1]
      || args.length !== 4) {
    process.stderr.write('Uso: node create-data-path-manifest.cjs --input <filesys.csv> --output <manifesto.txt>\n');
    process.exitCode = 2;
  } else {
    try {
      const result = writeDataPathManifest({
        inputCsvPath: path.resolve(args[inputIndex + 1]),
        outputPath: path.resolve(args[outputIndex + 1])
      });
      process.stdout.write('Manifesto de caminhos criado com ' + result.entries + ' entradas: ' + result.outputPath + '\n');
    } catch (error) {
      process.stderr.write('Falha ao criar manifesto de caminhos: ' + error.message + '\n');
      process.exitCode = 1;
    }
  }
}

module.exports = { writeDataPathManifest };
