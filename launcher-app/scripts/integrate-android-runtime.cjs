'use strict';
const fs = require('node:fs');
const path = require('node:path');

function fail(message) { throw new Error(message); }
function copyDirectoryContents(source, destination) {
  if (!fs.existsSync(source) || !fs.statSync(source).isDirectory()) fail('Expected directory is missing: ' + source);
  fs.mkdirSync(destination, { recursive: true });
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    const from = path.join(source, entry.name);
    const to = path.join(destination, entry.name);
    if (entry.isDirectory()) copyDirectoryContents(from, to);
    else if (entry.isFile()) {
      fs.mkdirSync(path.dirname(to), { recursive: true });
      fs.copyFileSync(from, to);
    } else fail('Unsupported runtime artifact entry: ' + from);
  }
}
function listFiles(directory) {
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const file = path.join(directory, entry.name);
    return entry.isDirectory() ? listFiles(file) : entry.isFile() ? [file] : [];
  });
}
function matchingBrace(text, openIndex) {
  let depth = 0;
  for (let i = openIndex; i < text.length; i += 1) {
    if (text[i] === '{') depth += 1;
    if (text[i] === '}') {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return -1;
}
function findMainActivity(javaRoot) {
  const matches = listFiles(javaRoot).filter((file) => path.basename(file) === 'MainActivity.java');
  if (matches.length !== 1) fail('Expected exactly one MainActivity.java, found ' + matches.length);
  const source = fs.readFileSync(matches[0], 'utf8');
  const match = source.match(/^\s*package\s+([A-Za-z0-9_.]+)\s*;/m);
  if (!match) fail('MainActivity.java has no Java package declaration');
  return { file: matches[0], packageName: match[1] };
}
function addSdlActivity(manifestPath) {
  let manifest = fs.readFileSync(manifestPath, 'utf8');
  if (!/<application\b/.test(manifest) || !/<\/application>/.test(manifest)) fail('Android manifest has no application element');
  if (!/android:glEsVersion\s*=\s*"0x00030002"/.test(manifest)) {
    const feature = '    <uses-feature android:glEsVersion="0x00030002" android:required="true" />\n';
    manifest = manifest.replace(/(<manifest\b[^>]*>)/, '$1\n' + feature);
  }
  if (!/android:name\s*=\s*"org\.libsdl\.app\.SDLActivity"/.test(manifest)) {
    const activity = [
      '        <activity',
      '            android:name="org.libsdl.app.SDLActivity"',
      '            android:configChanges="layoutDirection|locale|orientation|uiMode|screenLayout|screenSize|smallestScreenSize|keyboard|keyboardHidden|navigation"',
      '            android:exported="false"',
      '            android:screenOrientation="portrait"',
      '            android:theme="@android:style/Theme.NoTitleBar.Fullscreen">',
      '            <meta-data android:name="SDL_ENV.SDL_ACCELEROMETER_AS_JOYSTICK" android:value="0" />',
      '        </activity>'
    ].join('\n') + '\n';
    manifest = manifest.replace(/<\/application>/, activity + '    </application>');
  }
  fs.writeFileSync(manifestPath, manifest, 'utf8');
}
function patchGradle(gradlePath) {
  let gradle = fs.readFileSync(gradlePath, 'utf8');
  const config = /\bdefaultConfig\s*\{/.exec(gradle);
  if (!config) fail('app/build.gradle has no defaultConfig block');
  const configOpen = gradle.indexOf('{', config.index);
  const configClose = matchingBrace(gradle, configOpen);
  if (configClose < 0) fail('Could not close app/build.gradle defaultConfig block');
  let body = gradle.slice(configOpen + 1, configClose);
  if (!/abiFilters\s+['"]arm64-v8a['"]/.test(body)) body += "\n        ndk { abiFilters 'arm64-v8a' }\n";
  if (/minSdkVersion\s+[^,\n]+/.test(body)) body = body.replace(/minSdkVersion\s+[^,\n]+/, 'minSdkVersion 24');
  else body += '\n        minSdkVersion 24\n';
  gradle = gradle.slice(0, configOpen + 1) + body + gradle.slice(configClose);

  if (!/useLegacyPackaging\s*=\s*true/.test(gradle)) {
    const androidBlock = /\bandroid\s*\{/.exec(gradle);
    if (!androidBlock) fail('app/build.gradle has no android block');
    const androidOpen = gradle.indexOf('{', androidBlock.index);
    const androidClose = matchingBrace(gradle, androidOpen);
    if (androidClose < 0) fail('Could not close app/build.gradle android block');
    gradle = gradle.slice(0, androidClose)
      + "\n    packagingOptions {\n        jniLibs { useLegacyPackaging = true }\n    }\n"
      + gradle.slice(androidClose);
  }
  fs.writeFileSync(gradlePath, gradle, 'utf8');
}
function integrateAndroidRuntime(options) {
  const projectDir = path.resolve(options.projectDir);
  const artifactDir = path.resolve(options.runtimeArtifactDir);
  const appDir = path.join(projectDir, 'app');
  const sourceRoot = path.join(appDir, 'src', 'main');
  const javaRoot = path.join(sourceRoot, 'java');
  const assetsRoot = path.join(sourceRoot, 'assets');
  const jniRoot = path.join(sourceRoot, 'jniLibs', 'arm64-v8a');
  const runtimeData = path.join(artifactDir, 'runtime-data');
  const sdlJava = path.join(artifactDir, 'sdl-java');
  const requiredFiles = ['libmain.so', 'libSDL2.so', 'libc++_shared.so'];
  for (const file of requiredFiles) {
    if (!fs.existsSync(path.join(artifactDir, file))) fail('Native runtime is missing ' + file);
  }
  const requiredRuntimeFiles = [
    'header.bin',
    'firmware.bin',
    'build-version.txt',
    'wazaeffect/we.arc',
    'battle/skill/waza_seq.narc'
  ];
  for (const file of requiredRuntimeFiles) {
    if (!fs.existsSync(path.join(runtimeData, file))) fail('Runtime data is missing ' + file);
  }
  if (!fs.existsSync(sdlJava) || listFiles(sdlJava).filter((file) => file.endsWith('.java')).length === 0) {
    fail('SDLActivity Java sources were not included in the Android native artifact');
  }
  fs.mkdirSync(jniRoot, { recursive: true });
  for (const file of requiredFiles) fs.copyFileSync(path.join(artifactDir, file), path.join(jniRoot, file));
  copyDirectoryContents(sdlJava, path.join(javaRoot, 'org', 'libsdl', 'app'));
  copyDirectoryContents(runtimeData, path.join(assetsRoot, 'pokeplatinum'));

  const mainActivity = findMainActivity(javaRoot);
  const pluginTemplate = options.pluginTemplatePath
    ? path.resolve(options.pluginTemplatePath)
    : path.resolve(__dirname, '..', 'android-native', 'PlatinaGamePlugin.java');
  let plugin = fs.readFileSync(pluginTemplate, 'utf8');
  plugin = plugin.replace(/^\s*package\s+[A-Za-z0-9_.]+\s*;/m, 'package ' + mainActivity.packageName + ';');
  fs.writeFileSync(path.join(path.dirname(mainActivity.file), 'PlatinaGamePlugin.java'), plugin, 'utf8');
  const activitySource = [
    'package ' + mainActivity.packageName + ';',
    '',
    'import android.os.Bundle;',
    'import com.getcapacitor.BridgeActivity;',
    '',
    'public class MainActivity extends BridgeActivity {',
    '    @Override',
    '    public void onCreate(Bundle savedInstanceState) {',
    '        registerPlugin(PlatinaGamePlugin.class);',
    '        super.onCreate(savedInstanceState);',
    '    }',
    '}',
    ''
  ].join('\n');
  fs.writeFileSync(mainActivity.file, activitySource, 'utf8');
  addSdlActivity(path.join(sourceRoot, 'AndroidManifest.xml'));
  patchGradle(path.join(appDir, 'build.gradle'));
  return {
    applicationPackage: mainActivity.packageName,
    nativeLibraries: requiredFiles,
    sdlJavaFiles: listFiles(path.join(javaRoot, 'org', 'libsdl', 'app')).filter((file) => file.endsWith('.java')).length,
    runtimeAssetFiles: listFiles(path.join(assetsRoot, 'pokeplatinum')).length
  };
}
function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--project') args.projectDir = argv[++i];
    else if (argv[i] === '--runtime-artifact') args.runtimeArtifactDir = argv[++i];
    else throw new Error('Unknown argument: ' + argv[i]);
  }
  if (!args.projectDir || !args.runtimeArtifactDir) {
    throw new Error('Usage: node scripts/integrate-android-runtime.cjs --project android --runtime-artifact dist/native-game');
  }
  return args;
}
if (require.main === module) {
  try {
    const result = integrateAndroidRuntime(parseArgs(process.argv.slice(2)));
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  } catch (error) {
    process.stderr.write('Android runtime integration failed: ' + error.message + '\n');
    process.exitCode = 1;
  }
}
module.exports = { integrateAndroidRuntime, addSdlActivity, patchGradle };
