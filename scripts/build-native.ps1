param(
    [ValidateSet("win64")]
    [string]$Target = "win64"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$nativeDir = Join-Path $repoRoot "vendor/pokeplatinum-native"

if (-not (Test-Path (Join-Path $nativeDir "Makefile"))) {
    Write-Error "Submódulo nativo ausente. Execute: git submodule update --init --recursive"
    exit 2
}

$launcher = Join-Path $nativeDir "Launch_MSys2.ps1"
if (-not (Test-Path $launcher)) {
    Write-Error "Launch_MSys2.ps1 não existe no submódulo nativo."
    exit 2
}

Push-Location $nativeDir
try {
    # Pin, compile, and restore the upstream wrap files in the same MSYS shell.
    $command = "python3 ../../scripts/pin_native_dependencies.py . && (trap 'python3 ../../scripts/pin_native_dependencies.py --restore .' EXIT; make $Target)"
    & $launcher $command
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
