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
    # Use Python from the installed MSYS2 environment, then build in the same shell.
    & $launcher "python3 ../../scripts/pin_native_dependencies.py . && make $Target"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
