'use strict';

const { spawnSync } = require('node:child_process');

const BUILD_INPUT_PATHS = [
  '.gitmodules',
  'scripts/build-native.sh',
  'scripts/build-native.ps1',
  'scripts/pin_native_dependencies.py',
  'scripts/prepare_native_runtime.py',
  'scripts/verify_native_package.py',
  'tools/check_runtime_data.py',
  'launcher-app/scripts/create-data-path-manifest.cjs'
];

function nativeBuildRecipe(workflowText) {
  if (typeof workflowText !== 'string') throw new TypeError('Workflow text is required.');
  const match = /^on:\s*$/m.exec(workflowText);
  if (!match) throw new Error('Could not locate the native workflow trigger section.');
  // Concurrency and queue policy can change without changing the native build.
  // From "on:" onward, keep the workflow exact so the pinned source, toolchain,
  // compile, smoke-test, staging and upload steps must remain identical.
  return workflowText.slice(match.index);
}

function sameNativeBuildRecipe(candidateWorkflow, currentWorkflow) {
  try {
    return nativeBuildRecipe(candidateWorkflow) === nativeBuildRecipe(currentWorkflow);
  } catch {
    return false;
  }
}

function hasUsableArtifact(artifacts, expectedName) {
  return Array.isArray(artifacts) && artifacts.some((artifact) =>
    artifact
    && artifact.name === expectedName
    && artifact.expired === false
    && Number.isSafeInteger(artifact.size_in_bytes)
    && artifact.size_in_bytes > 0
  );
}

function runGit(args) {
  const result = spawnSync('git', args, {
    encoding: 'utf8',
    maxBuffer: 16 * 1024 * 1024,
    windowsHide: true
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || 'git command failed').trim());
  }
  return result.stdout;
}

async function getGitHubJson(repo, endpoint, token) {
  const response = await fetch('https://api.github.com/repos/' + repo + endpoint, {
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: 'Bearer ' + token,
      'X-GitHub-Api-Version': '2022-11-28'
    }
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 500);
    throw new Error('GitHub API returned HTTP ' + response.status + ' for ' + endpoint + ': ' + detail);
  }
  return response.json();
}

function writeOutput(values) {
  const output = process.env.GITHUB_OUTPUT;
  if (!output) {
    process.stdout.write(Object.entries(values).map(([key, value]) => key + '=' + value).join('\n') + '\n');
    return;
  }
  const fs = require('node:fs');
  fs.appendFileSync(output, Object.entries(values).map(([key, value]) => key + '=' + value).join('\n') + '\n', 'utf8');
}

async function candidateIsCompatible(candidateSha, currentSha) {
  if (!/^[a-f0-9]{40}$/i.test(candidateSha) || !/^[a-f0-9]{40}$/i.test(currentSha)) return false;
  try {
    runGit(['fetch', '--no-tags', '--depth=1', 'origin', candidateSha]);
    const differences = spawnSync('git', [
      'diff', '--quiet', candidateSha, currentSha, '--', ...BUILD_INPUT_PATHS
    ], { encoding: 'utf8', windowsHide: true });
    if (differences.error) throw differences.error;
    if (differences.status !== 0) {
      process.stdout.write('Skipping native run from ' + candidateSha.slice(0, 8)
        + ': one or more native build inputs changed.\n');
      return false;
    }

    const candidateWorkflow = runGit(['show', candidateSha + ':.github/workflows/native-desktop.yml']);
    const currentWorkflow = runGit(['show', currentSha + ':.github/workflows/native-desktop.yml']);
    if (!sameNativeBuildRecipe(candidateWorkflow, currentWorkflow)) {
      process.stdout.write('Skipping native run from ' + candidateSha.slice(0, 8)
        + ': native workflow build recipe changed.\n');
      return false;
    }
    return true;
  } catch (error) {
    process.stdout.write('Skipping native run from ' + candidateSha.slice(0, 8)
      + ': compatibility check failed (' + error.message + ').\n');
    return false;
  }
}

async function main() {
  const platform = process.argv[2];
  const artifactName = platform === 'linux'
    ? 'Platina-Reluzente-Linux-x86_64-AppImage'
    : platform === 'windows'
      ? 'Platina-Reluzente-Windows-x64-native'
      : '';
  if (!artifactName) throw new Error('Usage: node select-compatible-native-build.cjs linux|windows');

  const repo = process.env.GITHUB_REPOSITORY;
  const token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN;
  const currentSha = process.env.GITHUB_SHA;
  const eventName = process.env.GITHUB_EVENT_NAME;
  if (!repo || !/^[^/]+\/[^/]+$/.test(repo) || !token
      || !/^[a-f0-9]{40}$/i.test(currentSha || '')) {
    throw new Error('GITHUB_REPOSITORY, GITHUB_TOKEN and a full GITHUB_SHA are required.');
  }

  let runs;
  if (eventName === 'workflow_run') {
    const runId = process.env.NATIVE_WORKFLOW_RUN_ID;
    if (!/^\d+$/.test(runId || '')) throw new Error('The triggering native workflow run ID is missing.');
    runs = [await getGitHubJson(repo, '/actions/runs/' + runId, token)];
  } else {
    const response = await getGitHubJson(
      repo,
      '/actions/workflows/native-desktop.yml/runs?branch=main&per_page=100',
      token
    );
    runs = Array.isArray(response.workflow_runs) ? response.workflow_runs : [];
  }

  for (const run of runs) {
    if (!run || run.conclusion !== 'success' || run.head_branch !== 'main'
        || !/^[a-f0-9]{40}$/i.test(run.head_sha || '')
        || !Number.isSafeInteger(run.id)) continue;

    const artifactsResponse = await getGitHubJson(
      repo,
      '/actions/runs/' + run.id + '/artifacts?per_page=100',
      token
    );
    if (!hasUsableArtifact(artifactsResponse.artifacts, artifactName)) continue;

    // A successful workflow_run is packaging the exact source revision that
    // produced the artifact. A push/manual package may reuse an older native
    // build only after all build inputs and the complete build recipe match.
    if (eventName !== 'workflow_run'
        && !await candidateIsCompatible(run.head_sha, currentSha)) continue;

    writeOutput({ run_id: String(run.id), native_sha: run.head_sha });
    process.stdout.write('Selected verified native build run ' + run.id
      + ' (' + run.head_sha.slice(0, 8) + ') for ' + platform
      + ' from artifact ' + artifactName + '.\n');
    return;
  }

  throw new Error('No successful, unexpired and compatible native build artifact was found. A fresh native build is required.');
}

module.exports = { BUILD_INPUT_PATHS, nativeBuildRecipe, sameNativeBuildRecipe, hasUsableArtifact };

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write('Native build selection failed: ' + error.message + '\n');
    process.exitCode = 1;
  });
}
