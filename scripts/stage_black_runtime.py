#!/usr/bin/env python3
"""Stage a locally built Eidos runtime for the launcher's private test directory.

This helper copies only the native executable and its native shared-library
dependencies. It never copies ROMs, extracted assets, saves, patches, or build
intermediates. The destination is for local development, not public releases.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

class RuntimeStageError(RuntimeError):
    """Raised when a safe, complete local runtime cannot be staged."""


_SAFE_BASENAME = re.compile(r"^[A-Za-z0-9_.+-]+$")
_LINUX_SYSTEM_ROOTS = tuple(
    Path(value) for value in ("/lib", "/lib64", "/usr/lib", "/usr/lib64")
)
_WINDOWS_SYSTEM_DLLS = {
    # Windows OS components and API-set forwarders. Do not infer that an
    # arbitrary DLL is an OS dependency merely because the CI runner happens
    # to have a copy in System32; redistributable runtimes must be staged.
    "advapi32.dll", "bcrypt.dll", "bcryptprimitives.dll", "cfgmgr32.dll",
    "combase.dll", "comctl32.dll", "comdlg32.dll", "crypt32.dll",
    "cryptbase.dll", "cryptsp.dll", "d2d1.dll", "d3d11.dll", "dcomp.dll",
    "ddraw.dll", "dbghelp.dll", "dnsapi.dll", "dwmapi.dll", "dxgi.dll", "gdi32.dll",
    "gdi32full.dll", "hid.dll", "imm32.dll", "iphlpapi.dll",
    "kernel32.dll", "kernelbase.dll", "mpr.dll", "msimg32.dll",
    "msvcrt.dll", "nsi.dll", "ntdll.dll", "ole32.dll", "oleacc.dll",
    "oleaut32.dll", "opengl32.dll", "powrprof.dll", "psapi.dll",
    "rpcrt4.dll", "sechost.dll", "setupapi.dll", "shell32.dll",
    "shcore.dll", "shlwapi.dll", "ucrtbase.dll", "user32.dll",
    "userenv.dll", "uuid.dll", "uxtheme.dll", "version.dll", "win32u.dll",
    "windowscodecs.dll", "winmm.dll", "winspool.drv", "wintrust.dll",
    "ws2_32.dll", "wtsapi32.dll", "xinput1_4.dll",
}


def _require_regular_file(path: Path, label: str) -> Path:
    try:
        stat = path.lstat()
    except OSError as exc:
        raise RuntimeStageError(f"{label} não encontrado: {path}") from exc
    if path.is_symlink() or not path.is_file() or stat.st_size <= 0:
        raise RuntimeStageError(f"{label} precisa ser um arquivo regular, não vazio e sem link: {path}")
    return path


def _safe_runtime_name(name: str) -> str:
    if not name or not _SAFE_BASENAME.fullmatch(name) or name in {".", ".."}:
        raise RuntimeStageError(f"Nome de biblioteca inseguro no runtime: {name!r}")
    return name


def parse_ldd_dependencies(output: str) -> list[tuple[str, Path]]:
    """Parse ldd output and fail rather than silently omit unresolved libraries."""
    dependencies: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for line in output.splitlines():
        if "=> not found" in line or re.search(r"\bnot found\b", line):
            raise RuntimeStageError(f"Dependência Linux não resolvida por ldd: {line.strip()}")
        match = re.match(r"^\s*(\S+)\s+=>\s+(\S+)\s+\(0x[0-9a-fA-F]+\)\s*$", line)
        if match:
            name, resolved = match.groups()
            if resolved == "not":
                raise RuntimeStageError(f"Dependência Linux não resolvida por ldd: {line.strip()}")
        else:
            # The ELF loader itself is printed as an absolute path without "=>".
            match = re.match(r"^\s*(/\S+)\s+\(0x[0-9a-fA-F]+\)\s*$", line)
            if not match:
                continue
            resolved = match.group(1)
            name = Path(resolved).name
        if name.startswith("linux-vdso"):
            continue
        name = _safe_runtime_name(name)
        resolved_path = Path(resolved)
        if name not in seen:
            dependencies.append((name, resolved_path))
            seen.add(name)
    return dependencies


def is_linux_system_library(path: Path, name: str) -> bool:
    """Leave normal OS libraries to the host, but bundle SDL3 even if system-installed."""
    if name.lower().startswith("libsdl3"):
        return False
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in _LINUX_SYSTEM_ROOTS)


def _linux_dependencies(executable: Path, dependency_dirs: list[Path]) -> dict[str, Path]:
    if shutil.which("ldd") is None:
        raise RuntimeStageError("A ferramenta ldd é necessária para inspecionar dependências Linux.")
    env = os.environ.copy()
    search_dirs = [str(path) for path in dependency_dirs]
    inherited = env.get("LD_LIBRARY_PATH", "")
    if inherited:
        # An empty loader-path component means the current working directory.
        # Drop empty entries before invoking ldd so a developer's environment
        # cannot silently introduce the build directory into native resolution.
        search_dirs.extend(entry for entry in inherited.split(os.pathsep) if entry)
    if search_dirs:
        env["LD_LIBRARY_PATH"] = os.pathsep.join(search_dirs)

    collected: dict[str, Path] = {}
    inspected: set[Path] = set()
    pending: list[Path] = [executable.resolve()]

    # Inspect each staged candidate as well as the primary executable. A shared
    # library may itself depend on a non-system library that would otherwise be
    # missed by running ldd only once against the executable.
    while pending:
        image = pending.pop()
        image_key = image.resolve()
        if image_key in inspected:
            continue
        inspected.add(image_key)
        result = subprocess.run(
            ["ldd", str(image)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeStageError(
                f"Não foi possível inspecionar dependências de {image}: "
                + (result.stderr.strip() or result.stdout.strip() or f"ldd saiu com {result.returncode}")
            )

        for name, resolved_path in parse_ldd_dependencies(result.stdout):
            if is_linux_system_library(resolved_path, name):
                continue
            actual = resolved_path.resolve()
            _require_regular_file(actual, f"Biblioteca nativa {name}")
            previous = collected.get(name)
            if previous is not None:
                if previous.resolve() != actual:
                    raise RuntimeStageError(f"Dependência duplicada com origens diferentes: {name}")
                continue
            collected[name] = actual
            pending.append(actual)
    return collected


def parse_objdump_imports(output: str) -> list[str]:
    names = []
    seen = set()
    for line in output.splitlines():
        match = re.match(r"^\s*DLL Name:\s*(\S+)\s*$", line, re.IGNORECASE)
        if not match:
            continue
        name = _safe_runtime_name(match.group(1))
        key = name.casefold()
        if key not in seen:
            names.append(name)
            seen.add(key)
    return names


def _find_windows_dll(name: str, search_dirs: list[Path]) -> Path | None:
    key = name.casefold()
    for directory in search_dirs:
        if not directory.is_dir() or directory.is_symlink():
            continue
        direct = directory / name
        if direct.exists():
            candidate = direct
        else:
            candidate = next(
                (item for item in directory.iterdir()
                 if item.name.casefold() == key and item.is_file()),
                None,
            )
        if candidate is not None:
            if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size == 0:
                raise RuntimeStageError(f"Dependência Windows insegura ou vazia: {candidate}")
            return candidate.resolve()
    return None


def _is_windows_system_dll(name: str) -> bool:
    key = name.casefold()
    return key.startswith(("api-ms-win-", "ext-ms-win-")) or key in _WINDOWS_SYSTEM_DLLS


def _windows_dependencies(
    executable: Path,
    source_dir: Path,
    dependency_dirs: list[Path],
    objdump_path: str | Path | None = None,
) -> dict[str, Path]:
    if objdump_path is None:
        objdump = shutil.which("objdump")
    else:
        candidate = Path(objdump_path).expanduser().absolute()
        try:
            candidate_stat = candidate.lstat()
        except OSError as exc:
            raise RuntimeStageError(f"objdump configurado não foi encontrado: {candidate}") from exc
        if candidate.is_symlink() or not candidate.is_file() or candidate_stat.st_size == 0:
            raise RuntimeStageError(f"objdump precisa ser um arquivo regular e não vazio: {candidate}")
        objdump = str(candidate)
    if objdump is None:
        raise RuntimeStageError(
            "objdump não foi encontrado. Execute esta ferramenta em um ambiente MSYS2/MinGW "
            "ou informe --objdump com o caminho para o executável de análise."
        )
    search_dirs = [source_dir, *dependency_dirs]
    pending = [executable]
    inspected: set[Path] = set()
    collected: dict[str, Path] = {}
    collected_names: set[str] = set()

    while pending:
        image = pending.pop()
        image_key = image.resolve()
        if image_key in inspected:
            continue
        inspected.add(image_key)
        result = subprocess.run(
            [objdump, "-p", str(image)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeStageError(
                f"objdump não conseguiu examinar {image}: "
                + (result.stderr.strip() or result.stdout.strip())
            )
        for name in parse_objdump_imports(result.stdout):
            key = name.casefold()
            # Windows resolves DLL names case-insensitively. Use a separate
            # normalized set so imports with different casing never stage two
            # entries targeting the same destination name.
            if key in collected_names:
                continue
            candidate = _find_windows_dll(name, search_dirs)
            if candidate is None:
                if _is_windows_system_dll(name):
                    continue
                raise RuntimeStageError(
                    f"DLL necessária não encontrada: {name}. "
                    "Inclua a pasta que contém essa dependência com --dependency-dir."
                )
            collected[name] = candidate
            collected_names.add(key)
            pending.append(candidate)
    return collected


def _copy_native_file(source: Path, destination: Path) -> None:
    _require_regular_file(source, "Arquivo nativo")
    destination_name = _safe_runtime_name(destination.name)
    target = destination.parent / destination_name
    if target.exists():
        if target.is_symlink() or not target.is_file():
            raise RuntimeStageError(f"Destino de biblioteca inseguro: {target}")
        if target.read_bytes() != source.read_bytes():
            raise RuntimeStageError(f"Conflito de nomes de bibliotecas no pacote: {destination_name}")
        return
    shutil.copy2(source, target)


def stage_black_runtime(
    source_dir: str | Path,
    destination_dir: str | Path,
    platform: str,
    dependency_dirs: list[str | Path] | None = None,
    objdump_path: str | Path | None = None,
) -> dict[str, object]:
    """Stage a local, dependency-complete runtime without touching game data."""
    if platform not in {"linux", "windows"}:
        raise ValueError("platform deve ser 'linux' ou 'windows'.")

    source = Path(source_dir).expanduser().absolute()
    destination = Path(destination_dir).expanduser().absolute()
    dependencies = [Path(item).expanduser().absolute() for item in (dependency_dirs or [])]

    if destination == source or source in destination.parents or destination in source.parents:
        raise RuntimeStageError(
            "O diretório de build e o destino do runtime não podem conter um ao outro."
        )

    # Recover a previous interrupted commit before inspecting the new build.
    # If the destination exists, a leftover backup is stale and can be removed;
    # if only the backup exists, restore it before any new-build validation so
    # a missing executable or dependency cannot leave the launcher without its
    # last usable local runtime.
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = destination.with_name(destination.name + ".previous")
    if destination.is_symlink():
        raise RuntimeStageError(f"O destino não pode ser link simbólico: {destination}")
    if destination.exists() and not destination.is_dir():
        raise RuntimeStageError(f"O destino existe e não é uma pasta: {destination}")
    if backup.is_symlink() or (backup.exists() and not backup.is_dir()):
        raise RuntimeStageError(f"Backup anterior inseguro: {backup}")
    if backup.exists():
        if destination.exists():
            shutil.rmtree(backup)
        else:
            os.replace(backup, destination)

    if source.is_symlink() or not source.is_dir():
        raise RuntimeStageError(f"Diretório de build inválido: {source}")
    if any(item.is_symlink() or not item.is_dir() for item in dependencies):
        raise RuntimeStageError("Cada --dependency-dir precisa ser um diretório real, sem link simbólico.")

    executable_name = "eidos.exe" if platform == "windows" else "eidos"
    executable = _require_regular_file(source / executable_name, "Executável nativo Eidos")
    if platform == "linux" and not os.access(executable, os.X_OK):
        raise RuntimeStageError(f"O executável Linux não possui permissão de execução: {executable}")

    if platform == "linux":
        libraries = _linux_dependencies(executable, dependencies)
    else:
        libraries = _windows_dependencies(executable, source, dependencies, objdump_path)
        if not any(name.casefold() == "sdl3.dll" for name in libraries):
            raise RuntimeStageError(
                "O runtime Windows não resolveu SDL3.dll; não será preparado um pacote incompleto."
            )

    temporary_root = Path(tempfile.mkdtemp(prefix=destination.name + ".staging-", dir=destination.parent))
    try:
        staged_executable = temporary_root / executable_name
        _copy_native_file(executable, staged_executable)
        for name, library in libraries.items():
            _copy_native_file(library, temporary_root / name)
        if platform == "linux":
            staged_executable.chmod(staged_executable.stat().st_mode | 0o111)
        if not (temporary_root / executable_name).is_file():
            raise RuntimeStageError("O executável desapareceu durante a preparação do runtime.")
        if platform == "windows" and not (temporary_root / "SDL3.dll").is_file():
            raise RuntimeStageError("SDL3.dll está ausente do runtime preparado.")

        # A backup can only be present here if a previous destination is
        # being moved aside during this commit. It was already recovered or
        # validated above, so never delete it before the replacement is ready.
        had_previous = destination.exists()
        if had_previous:
            os.replace(destination, backup)
        try:
            os.replace(temporary_root, destination)
        except Exception:
            if had_previous and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            # The new runtime is already installed. A stale-backup cleanup
            # failure must not report the completed install as failed.
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        if temporary_root.exists():
            shutil.rmtree(temporary_root, ignore_errors=True)
        raise

    copied = [executable_name, *sorted(libraries)]
    return {
        "destination": str(destination),
        "platform": platform,
        "files": copied,
        "file_count": len(copied),
    }


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Prepara um runtime local do Pokémon Black dentro do launcher, sem ROMs ou dados do jogo."
    )
    parser.add_argument("--platform", required=True, choices=("linux", "windows"))
    parser.add_argument("--source-dir", required=True, help="Diretório build64/host do Eidos compilado.")
    parser.add_argument(
        "--dependency-dir", action="append", default=[],
        help="Pasta adicional com bibliotecas nativas; pode ser informada várias vezes.",
    )
    parser.add_argument(
        "--objdump",
        help="Caminho explícito para objdump; útil quando o toolchain MinGW fornece um binário específico.",
    )
    parser.add_argument(
        "--destination", default=str(repo_root / "launcher-app" / "black-runtime" / "runtime"),
        help="Pasta local de runtime (por padrão, launcher-app/black-runtime, ignorada pelo Git).",
    )
    args = parser.parse_args(argv)

    try:
        report = stage_black_runtime(
            args.source_dir, args.destination, args.platform,
            args.dependency_dir, args.objdump
        )
    except (OSError, RuntimeStageError, ValueError) as exc:
        print(f"Falha ao preparar runtime local de Pokémon Black: {exc}", file=sys.stderr)
        return 1

    print("Runtime local preparado para teste:")
    print(f"  Plataforma: {report['platform']}")
    print(f"  Destino: {report['destination']}")
    print(f"  Arquivos nativos: {report['file_count']}")
    for name in report["files"]:
        print(f"    - {name}")
    print("Nenhuma ROM, save, patch ou recurso extraído foi copiado.")
    print("Este runtime é local de desenvolvimento; não o publique nem o comite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
