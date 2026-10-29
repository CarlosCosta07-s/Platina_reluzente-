'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { integrateAndroidRuntime } = require('../scripts/integrate-android-runtime.cjs');

test('one Android package combines ROM importer, SDLActivity, native libraries and game assets', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-android-package-'));
  try {
    const project = path.join(temp, 'android');
    const app = path.join(project, 'app');
    const javaRoot = path.join(app, 'src', 'main', 'java', 'org', 'carloscostaxavier', 'platinareluzentelauncher');
    const runtime = path.join(temp, 'native-artifact');
    const sdl = path.join(runtime, 'sdl-java');
    const runtimeData = path.join(runtime, 'runtime-data');
    fs.mkdirSync(javaRoot, { recursive: true });
    fs.mkdirSync(sdl, { recursive: true });
    fs.mkdirSync(runtimeData, { recursive: true });
    fs.writeFileSync(path.join(javaRoot, 'MainActivity.java'), 'package org.carloscostaxavier.platinareluzentelauncher;\nimport com.getcapacitor.BridgeActivity;\npublic class MainActivity extends BridgeActivity {}\n');
    fs.writeFileSync(path.join(app, 'src', 'main', 'AndroidManifest.xml'), '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><activity android:name=".MainActivity" android:exported="true"/></application></manifest>');
    fs.writeFileSync(path.join(app, 'build.gradle'), "apply plugin: 'com.android.application'\nandroid {\n    defaultConfig {\n        applicationId 'org.carloscostaxavier.platinareluzentelauncher'\n        minSdkVersion rootProject.ext.minSdkVersion\n    }\n}\n");
    for (const name of ['libmain.so', 'libSDL2.so', 'libc++_shared.so']) fs.writeFileSync(path.join(runtime, name), Buffer.from('binary ' + name));
    fs.writeFileSync(path.join(runtimeData, 'header.bin'), 'header');
    fs.writeFileSync(path.join(runtimeData, 'firmware.bin'), 'firmware');
    fs.writeFileSync(path.join(runtimeData, 'build-version.txt'), 'test-build\n');
    fs.mkdirSync(path.join(runtimeData, 'wazaeffect'), { recursive: true });
    fs.mkdirSync(path.join(runtimeData, 'battle', 'skill'), { recursive: true });
    fs.writeFileSync(path.join(runtimeData, 'wazaeffect', 'we.arc'), 'waza-effect archive');
    fs.writeFileSync(path.join(runtimeData, 'battle', 'skill', 'waza_seq.narc'), 'move-animation archive');
    fs.writeFileSync(path.join(sdl, 'SDLActivity.java'), 'package org.libsdl.app; public class SDLActivity {}\n');

    const result = integrateAndroidRuntime({ projectDir: project, runtimeArtifactDir: runtime });
    const manifest = fs.readFileSync(path.join(app, 'src', 'main', 'AndroidManifest.xml'), 'utf8');
    const gradle = fs.readFileSync(path.join(app, 'build.gradle'), 'utf8');
    const mainActivity = fs.readFileSync(path.join(javaRoot, 'MainActivity.java'), 'utf8');
    const plugin = fs.readFileSync(path.join(javaRoot, 'PlatinaGamePlugin.java'), 'utf8');

    assert.equal(result.applicationPackage, 'org.carloscostaxavier.platinareluzentelauncher');
    assert.equal(result.sdlJavaFiles, 1);
    for (const name of ['libmain.so', 'libSDL2.so', 'libc++_shared.so']) {
      assert.ok(fs.existsSync(path.join(app, 'src', 'main', 'jniLibs', 'arm64-v8a', name)));
    }
    assert.ok(fs.existsSync(path.join(app, 'src', 'main', 'assets', 'pokeplatinum', 'header.bin')));
    assert.ok(fs.existsSync(path.join(app, 'src', 'main', 'assets', 'pokeplatinum', 'firmware.bin')));
    assert.ok(fs.existsSync(path.join(app, 'src', 'main', 'assets', 'pokeplatinum', 'build-version.txt')));
    assert.ok(fs.existsSync(path.join(app, 'src', 'main', 'assets', 'pokeplatinum', 'wazaeffect', 'we.arc')));
    assert.ok(fs.existsSync(path.join(app, 'src', 'main', 'assets', 'pokeplatinum', 'battle', 'skill', 'waza_seq.narc')));
    assert.ok(fs.existsSync(path.join(app, 'src', 'main', 'java', 'org', 'libsdl', 'app', 'SDLActivity.java')));
    assert.match(mainActivity, /registerPlugin\(PlatinaGamePlugin\.class\)/);
    assert.match(plugin, /startActivity\(intent\)/);
    assert.match(plugin, /A atividade SDL foi aberta/);
    assert.match(plugin, /abrir a atividade ainda não confirma que o jogo carregou/);
    assert.match(plugin, /roms\/current\.nds/);
    assert.match(plugin, /!\"CPUE\"\.equals\(code\)/);
    assert.equal(plugin.split('if (!"CPUE".equals(code))').length - 1, 1);
    assert.match(plugin, /Pokémon Platinum USA Rev\. 1/);
    assert.match(plugin, /input\.read\(\) != -1/);
    assert.match(plugin, /!required\.isFile\(\) \|\| required\.length\(\) <= 0/);
    assert.match(plugin, /Unable to recover|Não foi possível recuperar a pasta de recursos anterior/);
    const launcherSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'app.js'), 'utf8');
    assert.match(plugin, /romVersion != 1/);
    assert.match(plugin, /ROM version 0x1E igual a 1/);
    assert.match(launcherSource, /code !== 'CPUE'/);
    assert.match(launcherSource, /romVersion !== 1/);
    assert.match(launcherSource, /ROM version 0x1E igual a 1/);
    assert.match(launcherSource, /header\[0x1e\] !== 1/);
    assert.match(launcherSource, /ROM version no cabeçalho \(0x1E\) deve ser 1/);
    assert.match(plugin, /!destination\.exists\(\) && previous\.exists\(\) && !previous\.renameTo\(destination\)/);
    const existingBackupBranch = plugin.indexOf('if (destination.exists() && previous.exists())');
    const destinationVersionCheck = plugin.indexOf('if (isCompleteRuntime(destination, expectedVersion))', existingBackupBranch);
    const staleBackupCleanup = plugin.indexOf('deleteRecursively(previous);', destinationVersionCheck);
    const invalidDestinationCleanup = plugin.indexOf('if (!deleteRecursively(destination))', existingBackupBranch);
    const previousRestore = plugin.indexOf('if (!previous.renameTo(destination))', invalidDestinationCleanup);
    assert.ok(
      existingBackupBranch >= 0
        && destinationVersionCheck > existingBackupBranch
        && staleBackupCleanup > destinationVersionCheck,
      'the current runtime must be validated before its backup is deleted',
    );
    assert.ok(
      invalidDestinationCleanup > existingBackupBranch && previousRestore > invalidDestinationCleanup,
      'an invalid destination must be removed and the backup restored before a new copy begins',
    );
    assert.match(manifest, /android:name="org\.libsdl\.app\.SDLActivity"/);
    assert.match(manifest, /android:exported="false"/);
    assert.match(manifest, /0x00030002/);
    assert.match(gradle, /abiFilters 'arm64-v8a'/);
    assert.match(gradle, /minSdkVersion 24/);
    assert.match(gradle, /useLegacyPackaging = true/);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test('Android runtime integration rejects an artifact missing a required game archive', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platina-android-missing-archive-'));
  try {
    const runtime = path.join(temp, 'native-artifact');
    const runtimeData = path.join(runtime, 'runtime-data');
    fs.mkdirSync(runtimeData, { recursive: true });
    for (const name of ['libmain.so', 'libSDL2.so', 'libc++_shared.so']) {
      fs.writeFileSync(path.join(runtime, name), Buffer.from('binary ' + name));
    }
    for (const name of ['header.bin', 'firmware.bin', 'build-version.txt']) {
      fs.writeFileSync(path.join(runtimeData, name), name === 'build-version.txt' ? 'test-build\n' : 'fixture');
    }

    assert.throws(
      () => integrateAndroidRuntime({ projectDir: path.join(temp, 'android'), runtimeArtifactDir: runtime }),
      /Runtime data is missing wazaeffect\/we\.arc/,
    );
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

