'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  BUILD_INPUT_PATHS,
  nativeBuildRecipe,
  sameNativeBuildRecipe,
  hasUsableArtifact
} = require('../scripts/select-compatible-native-build.cjs');

test('native build recipe comparison ignores only concurrency policy above the trigger section', () => {
  const successfulBuild = [
    'name: Native desktop build and localization checks',
    '',
    'concurrency:',
    '  cancel-in-progress: true',
    '',
    'on:',
    '  push:',
    '    branches: [main]',
    '',
    'env:',
    '  NATIVE_SOURCE_COMMIT: abc123',
    'jobs:',
    '  linux:',
    '    steps:',
    '      - run: ./drun.sh make linux',
    ''
  ].join('\n');
  const currentBuild = successfulBuild.replace('cancel-in-progress: true', 'cancel-in-progress: false')
    .replace('  cancel-in-progress: false', '  cancel-in-progress: false\n  # Keep the build running');
  assert.equal(sameNativeBuildRecipe(successfulBuild, currentBuild), true);
  assert.equal(
    nativeBuildRecipe(successfulBuild),
    nativeBuildRecipe(currentBuild)
  );
});

test('native build recipe comparison rejects a changed pinned source or compile command', () => {
  const base = [
    'name: Native desktop build',
    '',
    'concurrency:',
    '  cancel-in-progress: true',
    '',
    'on:',
    '  push:',
    '    branches: [main]',
    '',
    'env:',
    '  NATIVE_SOURCE_COMMIT: abc123',
    'jobs:',
    '  linux:',
    '    steps:',
    '      - run: ./drun.sh make linux',
    ''
  ].join('\n');

  assert.equal(
    sameNativeBuildRecipe(base, base.replace('NATIVE_SOURCE_COMMIT: abc123', 'NATIVE_SOURCE_COMMIT: def456')),
    false
  );
  assert.equal(
    sameNativeBuildRecipe(base, base.replace('./drun.sh make linux', './drun.sh make debug')),
    false
  );
});

test('only non-expired, non-empty artifacts with the required native artifact name qualify', () => {
  const artifacts = [
    { name: 'Platina-Reluzente-Windows-x64-native', expired: false, size_in_bytes: 12345 },
    { name: 'Platina-Reluzente-Linux-x86_64-AppImage', expired: true, size_in_bytes: 99999 },
    { name: 'Platina-Reluzente-Linux-x86_64-AppImage', expired: false, size_in_bytes: 0 }
  ];

  assert.equal(hasUsableArtifact(artifacts, 'Platina-Reluzente-Windows-x64-native'), true);
  assert.equal(hasUsableArtifact(artifacts, 'Platina-Reluzente-Linux-x86_64-AppImage'), false);
  assert.equal(hasUsableArtifact(null, 'Platina-Reluzente-Windows-x64-native'), false);
});

test('compatibility gate covers the source preparation, pinned dependencies, data manifest and verification paths', () => {
  assert.ok(BUILD_INPUT_PATHS.includes('scripts/prepare_native_runtime.py'));
  assert.ok(BUILD_INPUT_PATHS.includes('scripts/pin_native_dependencies.py'));
  assert.ok(BUILD_INPUT_PATHS.includes('scripts/verify_native_package.py'));
  assert.ok(BUILD_INPUT_PATHS.includes('launcher-app/scripts/create-data-path-manifest.cjs'));
});
