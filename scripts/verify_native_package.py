#!/usr/bin/env python3
"""Verify that a native runtime package contains every mapped filesystem file.

The upstream copy script intentionally doesn't stop on every failed cp command.
This verifier turns those silent omissions into an explicit build failure.
It reads only build outputs and the text filesys.csv manifest; it never reads
or ships a ROM and does not modify the package.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

EXECUTABLE_CANDIDATES = ("main", "main.exe")
REQUIRED_PACKAGE_FILES = ("header.bin", "firmware.bin")
REQUIRED_ANIMATION_ARCHIVES = (
    "wazaeffect/we.arc",
    "battle/skill/waza_seq.narc",
)


class PackageVerificationError(ValueError):
    """Raised for invalid manifests or missing package directories."""


def _safe_relative(value: str, *, target: bool = False) -> PurePosixPath:
    value = value.strip()
    if target and value.startswith("/") and not value.startswith("//"):
        value = value[1:]
    if not value:
        raise PackageVerificationError("filesys.csv contém caminho vazio.")
    if "\\" in value or "\x00" in value or ":" in value:
        raise PackageVerificationError(f"Caminho inseguro no filesys.csv: {value!r}")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PackageVerificationError(f"Caminho inseguro no filesys.csv: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise PackageVerificationError(f"Caminho absoluto não permitido: {value!r}")
    return path


def _regular_file_without_symlinks(root: Path, relative: PurePosixPath) -> Path | None:
    current = root
    for index, component in enumerate(relative.parts):
        current = current / component
        if current.is_symlink():
            return None
        if index < len(relative.parts) - 1:
            if not current.is_dir():
                return None
        elif not current.is_file():
            return None
    return current


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _narc_error(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return f"não foi possível ler: {exc}"
    if len(data) < 16 or data[:8] != b"NARC\xfe\xff\x00\x01":
        return "assinatura NARC inválida"
    declared_size = int.from_bytes(data[8:12], "little")
    header_size = int.from_bytes(data[12:14], "little")
    chunk_count = int.from_bytes(data[14:16], "little")
    if declared_size != len(data):
        return f"tamanho NARC declarado {declared_size} difere do arquivo {len(data)}"
    if header_size != 16 or chunk_count != 3:
        return f"cabeçalho NARC inválido (header={header_size}, chunks={chunk_count})"

    pos = 16
    seen: set[bytes] = set()
    for _ in range(chunk_count):
        if pos + 8 > declared_size:
            return "tabela de blocos NARC truncada"
        block_id = data[pos:pos + 4]
        block_size = int.from_bytes(data[pos + 4:pos + 8], "little")
        if block_id not in {b"BTAF", b"BTNF", b"GMIF"} or block_id in seen:
            return f"identificador de bloco NARC inválido/duplicado: {block_id!r}"
        if block_size < 8 or pos + block_size > declared_size:
            return f"tamanho inválido no bloco NARC: {block_id!r}"
        seen.add(block_id)
        pos += block_size
    if seen != {b"BTAF", b"BTNF", b"GMIF"}:
        return "blocos NARC essenciais ausentes"
    return None


def verify_native_package(
    build_dir: str | Path,
    package_dir: str | Path,
    filesys_csv: str | Path,
) -> dict[str, Any]:
    build_root = Path(build_dir).expanduser().absolute()
    package_root = Path(package_dir).expanduser().absolute()
    manifest = Path(filesys_csv).expanduser().absolute()
    for label, path in (("build", build_root), ("package", package_root)):
        if path.is_symlink():
            raise PackageVerificationError(f"Diretório {label} não pode ser link simbólico: {path}")
        if not path.is_dir():
            raise PackageVerificationError(f"Diretório {label} não encontrado: {path}")
    if manifest.is_symlink() or not manifest.is_file():
        raise PackageVerificationError(f"Manifesto filesys.csv não encontrado ou não regular: {manifest}")

    missing_sources: list[str] = []
    missing_package_files: list[str] = []
    size_mismatches: list[dict[str, Any]] = []
    hash_mismatches: list[dict[str, Any]] = []
    manifest_entries = 0
    seen_targets: set[str] = set()

    with manifest.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
        if header != ["Source File", "Target File"]:
            raise PackageVerificationError(
                f"Cabeçalho filesys.csv inesperado: {header!r}; "
                "esperado ['Source File', 'Target File']."
            )
        for line_number, row in enumerate(reader, start=2):
            if not row or all(not item.strip() for item in row):
                continue
            if len(row) != 2:
                raise PackageVerificationError(
                    f"Linha {line_number} de filesys.csv deveria ter duas colunas."
                )
            source_rel = _safe_relative(row[0])
            target_rel = _safe_relative(row[1], target=True)
            target_key = target_rel.as_posix().casefold()
            if target_key in seen_targets:
                raise PackageVerificationError(
                    f"Destino duplicado no filesys.csv: {target_rel.as_posix()}"
                )
            seen_targets.add(target_key)
            manifest_entries += 1
            source_path = _regular_file_without_symlinks(build_root, source_rel)
            target_path = _regular_file_without_symlinks(package_root, target_rel)

            if source_path is None:
                missing_sources.append(f"linha {line_number}: {source_rel.as_posix()}")
                continue
            if target_path is None:
                missing_package_files.append(f"linha {line_number}: {target_rel.as_posix()}")
                continue
            source_size = source_path.stat().st_size
            target_size = target_path.stat().st_size
            if source_size != target_size:
                size_mismatches.append({
                    "source": source_rel.as_posix(),
                    "target": target_rel.as_posix(),
                    "source_bytes": source_size,
                    "target_bytes": target_size,
                })
                continue
            source_hash = _sha256(source_path)
            target_hash = _sha256(target_path)
            if source_hash != target_hash:
                hash_mismatches.append({
                    "source": source_rel.as_posix(),
                    "target": target_rel.as_posix(),
                    "source_sha256": source_hash,
                    "target_sha256": target_hash,
                })

    missing_root_files: list[str] = []
    if not any(
        _regular_file_without_symlinks(package_root, PurePosixPath(name)) is not None
        for name in EXECUTABLE_CANDIDATES
    ):
        missing_root_files.append("main ou main.exe")
    for relative in REQUIRED_PACKAGE_FILES:
        if _regular_file_without_symlinks(package_root, PurePosixPath(relative)) is None:
            missing_root_files.append(relative)

    invalid_animation_archives: list[dict[str, str]] = []
    for relative in REQUIRED_ANIMATION_ARCHIVES:
        path = _regular_file_without_symlinks(package_root, PurePosixPath(relative))
        if path is None:
            missing_root_files.append(relative)
            continue
        problem = _narc_error(path)
        if problem:
            invalid_animation_archives.append({"path": relative, "problem": problem})

    ready = not any((
        missing_sources,
        missing_package_files,
        size_mismatches,
        hash_mismatches,
        missing_root_files,
        invalid_animation_archives,
    ))
    return {
        "ready": ready,
        "build_dir": str(build_root),
        "package_dir": str(package_root),
        "manifest": str(manifest),
        "manifest_entries": manifest_entries,
        "missing_sources": missing_sources,
        "missing_package_files": missing_package_files,
        "size_mismatches": size_mismatches,
        "hash_mismatches": hash_mismatches,
        "missing_root_files": missing_root_files,
        "invalid_animation_archives": invalid_animation_archives,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verifica pacote runtime nativo contra o manifesto filesys.csv do porte."
    )
    parser.add_argument("--build-dir", required=True, help="Raiz do build Meson (build_linux ou build_win64).")
    parser.add_argument("--package-dir", required=True, help="Pasta gerada para executar o jogo (build_*/pokeplatinum).")
    parser.add_argument("--filesys-csv", required=True, help="Caminho para platinum.us/filesys.csv.")
    parser.add_argument("--json", action="store_true", help="Imprime relatório JSON completo.")
    args = parser.parse_args(argv)

    try:
        report = verify_native_package(args.build_dir, args.package_dir, args.filesys_csv)
    except (OSError, PackageVerificationError) as exc:
        print(f"Falha ao validar pacote nativo: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        state = "PACOTE COMPLETO" if report["ready"] else "PACOTE INCOMPLETO"
        print(f"{state}: {report['package_dir']}")
        print(f"Entradas verificadas: {report['manifest_entries']}")
        print(f"Arquivos de origem ausentes: {len(report['missing_sources'])}")
        print(f"Arquivos de destino ausentes: {len(report['missing_package_files'])}")
        print(f"Divergências de tamanho/hash: {len(report['size_mismatches']) + len(report['hash_mismatches'])}")
        print(f"Arquivos raiz/animação ausentes: {len(report['missing_root_files'])}")
        print(f"Arquivos NARC de animação inválidos: {len(report['invalid_animation_archives'])}")
        if not report["ready"]:
            for key in (
                "missing_sources",
                "missing_package_files",
                "size_mismatches",
                "hash_mismatches",
                "missing_root_files",
                "invalid_animation_archives",
            ):
                values = report[key]
                if values:
                    print(f"{key}:")
                    for value in values[:25]:
                        print(f"  - {value}")
                    if len(values) > 25:
                        print(f"  - ... e mais {len(values)-25}")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
