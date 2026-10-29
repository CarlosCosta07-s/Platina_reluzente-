#!/usr/bin/env python3
"""Check local runtime data and optionally verify the supported PT-BR resource set.

This tool checks only local runtime files. It never reads or copies a ROM,
never downloads game data, and never uploads any files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    from import_localization import TARGET_FILES
    from localization_manifest import PTBR_RESOURCE_SHA256
except ImportError:
    from tools.import_localization import TARGET_FILES
    from tools.localization_manifest import PTBR_RESOURCE_SHA256


CORE_FILES = {
    "header.bin": 0x4000,
    "arm9.bin": 1,
    "arm7.bin": 1,
    "arm9ovt.bin": 1,
    "arm7ovt.bin": 1,
    "banner.bin": 1,
    "fnt.bin": 8,
    "fat.bin": 8,
    "rsasig.bin": 1,
}
REQUIRED_RUNTIME_ARCHIVES = (
    "wazaeffect/we.arc",
    "battle/skill/waza_seq.narc",
)
EXECUTABLE_CANDIDATES = ("main", "main.exe", "pokeplatinum", "pokeplatinum.exe")
OVERLAY_PATTERNS = {
    "overlay9": re.compile(r"^overlay9_\d+\.bin$"),
    "overlay7": re.compile(r"^overlay7_\d+\.bin$"),
}

class RuntimeDataError(ValueError):
    """Raised if the selected directory does not look like an extracted runtime."""


def _validate_narc(path: Path) -> tuple[bool, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return False, f"não foi possível ler: {exc}"
    if len(raw) < 16:
        return False, "arquivo menor que o cabeçalho NARC"
    if raw[:8] != b"NARC\xfe\xff\x00\x01":
        return False, "assinatura/versão/endian NARC inválidos"

    declared_size = int.from_bytes(raw[8:12], "little")
    header_size = int.from_bytes(raw[12:14], "little")
    chunk_count = int.from_bytes(raw[14:16], "little")
    if declared_size != len(raw):
        return False, f"tamanho real {len(raw)} difere do tamanho NARC declarado {declared_size}"
    if header_size != 16:
        return False, f"tamanho do cabeçalho NARC inválido: {header_size}"
    if chunk_count < 1 or chunk_count > 32:
        return False, f"contagem de blocos inválida: {chunk_count}"

    cursor = 16
    identifiers: set[bytes] = set()
    for _ in range(chunk_count):
        if cursor + 8 > declared_size:
            return False, "lista de blocos truncada"
        block_id = raw[cursor:cursor + 4]
        block_size = int.from_bytes(raw[cursor + 4:cursor + 8], "little")
        if block_id not in (b"BTAF", b"BTNF", b"GMIF") or block_id in identifiers:
            return False, f"bloco inválido/duplicado: {block_id!r}"
        if block_size < 8 or cursor + block_size > declared_size:
            return False, f"tamanho inválido no bloco {block_id!r}"
        identifiers.add(block_id)
        cursor += block_size

    if not {b"BTAF", b"BTNF", b"GMIF"}.issubset(identifiers):
        return False, "faltam blocos essenciais BTAF/BTNF/GMIF"
    return True, "NARC válido"


def _regular_file_without_symlinks(root: Path, relative: str) -> Path | None:
    """Return a regular file only when none of its runtime path components is a symlink."""
    current = root
    parts = Path(relative).parts
    for index, component in enumerate(parts):
        current = current / component
        if current.is_symlink():
            return None
        if index < len(parts) - 1:
            if not current.is_dir():
                return None
        elif not current.is_file():
            return None
    return current


def inspect_runtime_directory(
    runtime_dir: str | Path,
    *,
    require_localized_resources: bool = False,
) -> dict[str, object]:
    root = Path(runtime_dir).expanduser().absolute()
    if root.is_symlink():
        raise RuntimeDataError(f"diretório de runtime não pode ser link simbólico: {root}")
    if not root.exists() or not root.is_dir():
        raise RuntimeDataError(f"diretório de runtime não encontrado: {root}")

    missing: list[str] = []
    invalid: list[dict[str, str]] = []
    checked: list[dict[str, object]] = []

    executable = next(
        (
            name for name in EXECUTABLE_CANDIDATES
            if _regular_file_without_symlinks(root, name) is not None
        ),
        None,
    )
    if executable is None:
        missing.append("executável nativo (esperado main/main.exe no diretório indicado)")
    else:
        checked.append({"path": executable, "status": "present"})

    for name, minimum_size in CORE_FILES.items():
        path = _regular_file_without_symlinks(root, name)
        if path is None:
            missing.append(name)
            continue
        size = path.stat().st_size
        if size < minimum_size:
            invalid.append({
                "path": name,
                "problem": f"tamanho {size} menor que o mínimo {minimum_size}",
            })
        else:
            checked.append({"path": name, "status": "present", "size_bytes": size})

    for directory, pattern in OVERLAY_PATTERNS.items():
        overlay_dir = root / directory
        if overlay_dir.is_symlink() or not overlay_dir.is_dir():
            missing.append(f"{directory}/")
            continue
        overlays = []
        for candidate in sorted(overlay_dir.iterdir()):
            if not pattern.fullmatch(candidate.name):
                continue
            safe_candidate = _regular_file_without_symlinks(
                root, f"{directory}/{candidate.name}"
            )
            if safe_candidate is None:
                invalid.append({
                    "path": f"{directory}/{candidate.name}",
                    "problem": "overlay usa um link simbólico ou não é arquivo regular",
                })
                continue
            overlays.append(safe_candidate)
        if not overlays:
            missing.append(f"{directory}/overlay*_*.bin")
            continue
        checked.append({
            "path": f"{directory}/",
            "status": "present",
            "overlay_count": len(overlays),
        })
        for overlay in overlays:
            if overlay.stat().st_size == 0:
                invalid.append({"path": overlay.relative_to(root).as_posix(), "problem": "overlay vazio"})

    # These archives are essential to battle/move-animation behavior. The upstream
    # Windows CI once skipped their generation, which let a broken package pass.
    for relative_name in REQUIRED_RUNTIME_ARCHIVES:
        path = _regular_file_without_symlinks(root, relative_name)
        if path is None:
            missing.append(relative_name)
            continue
        valid, message = _validate_narc(path)
        if not valid:
            invalid.append({"path": relative_name, "problem": message})
        else:
            checked.append({
                "path": relative_name,
                "status": "present_and_valid_narc",
                "size_bytes": path.stat().st_size,
            })

    localization_report: list[dict[str, str | int]] = []
    if require_localized_resources:
        for relative in TARGET_FILES:
            relative_name = relative.as_posix()
            path = _regular_file_without_symlinks(root, relative_name)
            expected_hash = PTBR_RESOURCE_SHA256.get(relative_name)
            if path is None:
                missing.append(relative_name)
                continue

            valid, message = _validate_narc(path)
            if not valid:
                invalid.append({"path": relative_name, "problem": message})
                continue

            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if expected_hash is None:
                invalid.append({
                    "path": relative_name,
                    "problem": "não existe SHA-256 de referência para esta versão PT-BR",
                })
                continue
            if actual_hash != expected_hash:
                invalid.append({
                    "path": relative_name,
                    "problem": (
                        "NARC válido, mas o SHA-256 não corresponde à versão PT-BR aprovada "
                        f"(esperado {expected_hash}, recebido {actual_hash})"
                    ),
                })
                continue
            localization_report.append({
                "path": relative_name,
                "size_bytes": path.stat().st_size,
                "sha256": actual_hash,
                "status": "ptbr_sha256_match",
            })

    ready = not missing and not invalid
    return {
        "runtime_directory": str(root),
        "ready_for_launch_attempt": ready,
        "executable": executable,
        "missing": missing,
        "invalid": invalid,
        "checked": checked,
        "localized_resources_required": require_localized_resources,
        "localized_resources_valid": localization_report,
        "notes": (
            "A aprovação confirma arquivos locais, estruturas NARC básicas e, quando solicitado, "
            "correspondência SHA-256 com a variante PT-BR de referência. Não prova que o jogo "
            "inicia, renderiza corretamente ou é jogável."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verifica recursos locais do runtime do porte sem ler ou enviar uma ROM."
    )
    parser.add_argument(
        "--runtime-dir",
        required=True,
        help="Diretório de runtime do executável nativo, por exemplo build_linux/pokeplatinum ou build_win64/pokeplatinum.",
    )
    parser.add_argument(
        "--require-localized-resources",
        action="store_true",
        help="Também exige NARC válidos e SHA-256 correspondente à variante PT-BR de referência.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Imprime um relatório JSON para diagnósticos.",
    )
    args = parser.parse_args(argv)

    try:
        report = inspect_runtime_directory(
            args.runtime_dir,
            require_localized_resources=args.require_localized_resources,
        )
    except (OSError, RuntimeDataError) as exc:
        print(f"Erro de validação do runtime: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "PRONTO PARA TENTAR INICIAR" if report["ready_for_launch_attempt"] else "DADOS INCOMPLETOS"
        print(f"{status}: {report['runtime_directory']}")
        print(f"Executável: {report['executable'] or 'ausente'}")
        if report["missing"]:
            print("Ausentes:")
            for item in report["missing"]:
                print(f"  - {item}")
        if report["invalid"]:
            print("Inválidos:")
            for item in report["invalid"]:
                print(f"  - {item['path']}: {item['problem']}")
        if report["localized_resources_required"]:
            print(
                f"NARC da variante PT-BR confirmados por hash: "
                f"{len(report['localized_resources_valid'])}/{len(TARGET_FILES)}"
            )
        print(report["notes"])
    return 0 if report["ready_for_launch_attempt"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
