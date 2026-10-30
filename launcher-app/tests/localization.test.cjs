'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {
  LOCALIZATION_MANIFEST_FILE,
  PTBR_BASE_ROM_SHA1,
  PTBR_SOURCE_ROM_SHA1,
  PTBR_RESOURCE_SHA256,
  verifyLocalizationPackage,
  installLocalizationPackage,
  readLanguagePreference,
  writeLanguagePreference
} = require('../electron/localization.cjs');

function fixturePolicy() {
  const relative = 'msgdata/pl_msg.narc';
  const data = Buffer.from('synthetic Portuguese resource');
  const sha256 = crypto.createHash('sha256').update(data).digest('hex');
  return {
    policy: {
      game: 'pokemon-platinum',
      locale: 'pt-BR',
      baseRomSha1: 'base-rom-sha1',
      sourceRomSha1: 'source-rom-sha1',
      resources: { [relative]: sha256 }
    },
    relative,
    data
  };
}

function writeFixturePackage(root, policy, relative, data) {
  fs.mkdirSync(root, { recursive: true });
  const destination = path.join(root, ...relative.split('/'));
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.writeFileSync(destination, data);
  const manifest = {
    schemaVersion: 1,
    game: policy.game,
    locale: policy.locale,
    baseRomSha1: policy.baseRomSha1,
    sourceRomSha1: policy.sourceRomSha1,
    resourceCount: 1,
    resources: [{
      path: relative,
      sizeBytes: data.length,
      fatSizeBytes: data.length,
      sizeRecoveredFromNarcHeader: false,
      sha256: policy.resources[relative]
    }]
  };
  fs.writeFileSync(path.join(root, LOCALIZATION_MANIFEST_FILE), JSON.stringify(manifest, null, 2) + '\n');
  return manifest;
}

test('launcher PT-BR hashes stay synchronized with the canonical Python manifest', () => {
  const pythonManifest = fs.readFileSync(
    path.resolve(__dirname, '..', '..', 'tools', 'localization_manifest.py'),
    'utf8'
  );
  const match = pythonManifest.match(/PTBR_RESOURCE_SHA256\s*=\s*\{([\s\S]*?)\n\}/);
  assert.ok(match, 'canonical Python resource hash map exists');
  const entries = [...match[1].matchAll(/"([^"]+)"\s*:\s*"([a-f0-9]{64})"/g)];
  assert.deepEqual(
    Object.fromEntries(entries.map((entry) => [entry[1], entry[2]])),
    PTBR_RESOURCE_SHA256
  );
  assert.match(pythonManifest, new RegExp(PTBR_BASE_ROM_SHA1));
  assert.match(pythonManifest, new RegExp(PTBR_SOURCE_ROM_SHA1));
});

test('validates package identity, exact resource hash and exact directory contents', async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-localization-valid-'));
  const { policy, relative, data } = fixturePolicy();
  try {
    writeFixturePackage(temp, policy, relative, data);
    const verified = await verifyLocalizationPackage(temp, policy);
    assert.equal(verified.root, temp);
    assert.equal(verified.manifest.locale, 'pt-BR');
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test('rejects a changed resource, extra file, or extra directory', async () => {
  const { policy, relative, data } = fixturePolicy();
  for (const mutate of [
    (root) => fs.writeFileSync(path.join(root, ...relative.split('/')), 'changed'),
    (root) => fs.writeFileSync(path.join(root, 'extra.bin'), 'unlisted'),
    (root) => fs.mkdirSync(path.join(root, 'extra-directory'))
  ]) {
    const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-localization-reject-'));
    try {
      writeFixturePackage(temp, policy, relative, data);
      mutate(temp);
      await assert.rejects(verifyLocalizationPackage(temp, policy));
    } finally {
      fs.rmSync(temp, { recursive: true, force: true });
    }
  }
});

test('rejects incorrect source identity and malformed manifest metadata', async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-localization-identity-'));
  const { policy, relative, data } = fixturePolicy();
  try {
    const manifest = writeFixturePackage(temp, policy, relative, data);
    manifest.sourceRomSha1 = 'another-source';
    fs.writeFileSync(path.join(temp, LOCALIZATION_MANIFEST_FILE), JSON.stringify(manifest));
    await assert.rejects(verifyLocalizationPackage(temp, policy), /Identidade ou compatibilidade/);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test('rejects symbolic links at package root and inside package', async (t) => {
  const { policy, relative, data } = fixturePolicy();
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-localization-symlink-'));
  const source = path.join(temp, 'source');
  const external = path.join(temp, 'external');
  try {
    writeFixturePackage(source, policy, relative, data);
    fs.mkdirSync(external);
    fs.writeFileSync(path.join(external, 'resource.bin'), 'outside');
    try {
      fs.symlinkSync(external, path.join(temp, 'root-link'), 'dir');
      fs.symlinkSync(path.join(external, 'resource.bin'), path.join(source, 'linked.bin'), 'file');
    } catch (error) {
      if (error && ['EPERM', 'EACCES', 'ENOTSUP', 'ENOSYS'].includes(error.code)) {
        t.skip('This platform does not permit creating symlinks for tests.');
        return;
      }
      throw error;
    }
    await assert.rejects(verifyLocalizationPackage(path.join(temp, 'root-link')));
    await assert.rejects(verifyLocalizationPackage(source, policy));
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test('installs a verified package into a private target and preserves the source', async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-localization-install-'));
  const { policy, relative, data } = fixturePolicy();
  const source = path.join(temp, 'source-package');
  const destination = path.join(temp, 'user-data', 'localizations', 'pt-BR');
  try {
    writeFixturePackage(source, policy, relative, data);
    const result = await installLocalizationPackage(source, destination, policy);
    assert.equal(result.root, destination);
    assert.equal(fs.readFileSync(path.join(destination, ...relative.split('/'))).toString(), data.toString());
    assert.equal(fs.existsSync(path.join(source, relative)), true);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test('replaces only a previously verified managed package', async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-localization-replace-'));
  const { policy, relative, data } = fixturePolicy();
  const source = path.join(temp, 'source-package');
  const destination = path.join(temp, 'user-data', 'localizations', 'pt-BR');
  try {
    writeFixturePackage(source, policy, relative, data);
    writeFixturePackage(destination, policy, relative, data);
    const result = await installLocalizationPackage(source, destination, policy);
    assert.equal(result.root, destination);

    const unmanaged = path.join(temp, 'user-data', 'localizations', 'unmanaged');
    fs.mkdirSync(unmanaged, { recursive: true });
    fs.writeFileSync(path.join(unmanaged, 'keep.txt'), 'keep');
    await assert.rejects(installLocalizationPackage(source, unmanaged, policy));
    assert.equal(fs.readFileSync(path.join(unmanaged, 'keep.txt'), 'utf8'), 'keep');
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test('rejects invalid language preferences and persists supported choices', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-language-setting-'));
  const filePath = path.join(temp, 'settings', 'platinum-language.txt');
  try {
    assert.equal(readLanguagePreference(filePath), 'en');
    assert.equal(writeLanguagePreference(filePath, 'pt-BR'), 'pt-BR');
    assert.equal(readLanguagePreference(filePath), 'pt-BR');
    assert.equal(writeLanguagePreference(filePath, 'en'), 'en');
    assert.equal(readLanguagePreference(filePath), 'en');
    assert.throws(() => writeLanguagePreference(filePath, 'fr'), /não suportado/);
    fs.writeFileSync(filePath, 'fr\n');
    assert.throws(() => readLanguagePreference(filePath), /preferência de idioma/);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test('refuses to follow a symbolic link for the language preference', (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-language-setting-link-'));
  const external = path.join(temp, 'external.txt');
  const preference = path.join(temp, 'platinum-language.txt');
  try {
    fs.writeFileSync(external, 'pt-BR\n');
    try {
      fs.symlinkSync(external, preference, 'file');
    } catch (error) {
      if (error && ['EPERM', 'EACCES', 'ENOTSUP', 'ENOSYS'].includes(error.code)) {
        t.skip('This platform does not permit creating symlinks for tests.');
        return;
      }
      throw error;
    }
    assert.throws(() => readLanguagePreference(preference), /Link simbólico/);
    assert.throws(() => writeLanguagePreference(preference, 'en'), /Link simbólico/);
    assert.equal(fs.readFileSync(external, 'utf8'), 'pt-BR\n');
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});
