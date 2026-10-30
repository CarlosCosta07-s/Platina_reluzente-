#!/usr/bin/env python3
"""Import an allowlisted set of localized Pokémon Platinum NARC files from a local CPUE ROM dump.

This tool never modifies the ROM and writes only to an explicit destination.
It does not distribute or upload ROM data.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import json
import stat
import struct
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

try:
    from localization_manifest import PTBR_SOURCE_ROM_SHA1, PLATINUM_USA_REV1_SHA1, PTBR_RESOURCE_SHA256
except ImportError:
    from tools.localization_manifest import PTBR_SOURCE_ROM_SHA1, PLATINUM_USA_REV1_SHA1, PTBR_RESOURCE_SHA256

HEADER_SIZE = 0x200
MAX_ROM_SIZE = 512 * 1024 * 1024
MAX_DIRECTORIES = 2048
TARGET_FILES = (
    PurePosixPath("battle/graphic/pl_b_plist_gra.narc"),
    PurePosixPath("data/slot.narc"),
    PurePosixPath("demo/title/op_demo.narc"),
    PurePosixPath("graphic/pl_bag_gra.narc"),
    PurePosixPath("graphic/pl_plist_gra.narc"),
    PurePosixPath("graphic/pl_pst_gra.narc"),
    PurePosixPath("msgdata/pl_msg.narc"),
)
CHUNK_SIZE = 1024 * 1024


class RomFormatError(ValueError):
    """Raised when the supplied file is not a supported Platinum ROM image."""


@dataclass(frozen=True)
class RomFile:
    file_id: int
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start


def _checked_region(offset: int, size: int, rom_size: int, label: str) -> None:
    if offset < HEADER_SIZE or size <= 0 or offset + size > rom_size:
        raise RomFormatError(f"Região {label} fora dos limites da ROM.")


def _read_exact(stream: BinaryIO, size: int, label: str) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise RomFormatError(f"Arquivo truncado ao ler {label}.")
    return data


def _parse_fnt(fnt: bytes, fat: bytes, rom_size: int) -> tuple[dict[str, RomFile], list[RomFile]]:
    if len(fnt) < 8 or len(fat) == 0 or len(fat) % 8 != 0:
        raise RomFormatError("Tabelas FNT/FAT inválidas.")

    fat_entries: list[RomFile] = []
    for file_id in range(len(fat) // 8):
        start, end = struct.unpack_from("<II", fat, file_id * 8)
        if start > end or end > rom_size:
            raise RomFormatError(f"Limites FAT inválidos para o arquivo {file_id}.")
        fat_entries.append(RomFile(file_id, start, end))

    directory_count = struct.unpack_from("<H", fnt, 6)[0]
    if directory_count == 0 or directory_count > MAX_DIRECTORIES:
        raise RomFormatError(f"Quantidade de diretórios inválida: {directory_count}.")
    if directory_count * 8 > len(fnt):
        raise RomFormatError("Tabela de diretórios ultrapassa o tamanho do FNT.")

    directories: dict[int, tuple[int, int, int]] = {}
    for index in range(directory_count):
        name_offset, first_file_id, parent_id = struct.unpack_from("<IHH", fnt, index * 8)
        if name_offset >= len(fnt):
            raise RomFormatError(f"Offset de nomes inválido no diretório {index}.")
        directories[0xF000 + index] = (name_offset, first_file_id, parent_id)

    file_count = len(fat_entries)
    result: dict[str, RomFile] = {}
    seen_directories: set[int] = set()

    def walk(directory_id: int, prefix: str, depth: int = 0) -> None:
        if depth > 64:
            raise RomFormatError("A hierarquia do FNT excede a profundidade permitida.")
        if directory_id in seen_directories:
            raise RomFormatError(f"Diretório duplicado ou ciclo no FNT: 0x{directory_id:04X}.")
        record = directories.get(directory_id)
        if record is None:
            raise RomFormatError(f"Referência a diretório ausente: 0x{directory_id:04X}.")
        seen_directories.add(directory_id)
        cursor, current_file_id, _parent_id = record

        while True:
            if cursor >= len(fnt):
                raise RomFormatError("Lista de nomes FNT sem terminador.")
            entry = fnt[cursor]
            cursor += 1
            if entry == 0:
                break

            is_directory = bool(entry & 0x80)
            name_length = entry & 0x7F
            if name_length == 0 or cursor + name_length > len(fnt):
                raise RomFormatError("Entrada de nome FNT inválida.")
            raw_name = fnt[cursor:cursor + name_length]
            cursor += name_length
            name = raw_name.decode("cp932", errors="replace")
            if name in (".", "..") or "/" in name or "\\" in name:
                raise RomFormatError("Nome de arquivo/diretório inseguro no FNT.")

            if is_directory:
                if cursor + 2 > len(fnt):
                    raise RomFormatError("Entrada de subdiretório FNT truncada.")
                child_id = struct.unpack_from("<H", fnt, cursor)[0]
                cursor += 2
                walk(child_id, f"{prefix}{name}/", depth + 1)
                continue

            if current_file_id >= file_count:
                raise RomFormatError(f"ID FAT fora dos limites: {current_file_id}.")
            relative_path = f"{prefix}{name}".casefold()
            if relative_path in result:
                raise RomFormatError(f"Caminho duplicado no FNT: {relative_path}.")
            result[relative_path] = fat_entries[current_file_id]
            current_file_id += 1

    walk(0xF000, "")
    return result, fat_entries


def _index_rom(rom_path: Path) -> tuple[dict[str, RomFile], list[RomFile], int]:
    if not rom_path.is_file():
        raise FileNotFoundError(f"ROM não encontrada: {rom_path}")

    rom_size = rom_path.stat().st_size
    if rom_size < HEADER_SIZE or rom_size > MAX_ROM_SIZE:
        raise RomFormatError(f"Tamanho de ROM fora do intervalo aceito: {rom_size} bytes.")

    with rom_path.open("rb") as stream:
        header = _read_exact(stream, HEADER_SIZE, "cabeçalho NDS")
        title = header[:12].decode("ascii", errors="replace").rstrip("\0")
        game_code = header[12:16].decode("ascii", errors="replace")
        if not title.upper().startswith("POKEMON PL") or game_code != "CPUE":
            raise RomFormatError(
                f"ROM não reconhecida como Pokémon Platinum USA (título={title!r}, código={game_code!r})."
            )

        fnt_offset, fnt_size = struct.unpack_from("<II", header, 0x40)
        fat_offset, fat_size = struct.unpack_from("<II", header, 0x48)
        _checked_region(fnt_offset, fnt_size, rom_size, "FNT")
        _checked_region(fat_offset, fat_size, rom_size, "FAT")
        if fnt_size > 16 * 1024 * 1024 or fat_size > 16 * 1024 * 1024:
            raise RomFormatError("Tabela FNT/FAT excede o limite de tamanho permitido.")

        stream.seek(fnt_offset)
        fnt = _read_exact(stream, fnt_size, "FNT")
        stream.seek(fat_offset)
        fat = _read_exact(stream, fat_size, "FAT")

    files, fat_entries = _parse_fnt(fnt, fat, rom_size)
    return files, fat_entries, rom_size


def _sha256_region(stream: BinaryIO, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    stream.seek(offset)
    remaining = size
    while remaining:
        chunk = stream.read(min(CHUNK_SIZE, remaining))
        if not chunk:
            raise RomFormatError("ROM truncada ao calcular o SHA-256 de um recurso.")
        digest.update(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def _validated_narc_size(
    stream: BinaryIO,
    entry: RomFile,
    fat_entries: list[RomFile],
    rom_size: int,
    relative_path: PurePosixPath,
) -> int:
    if entry.size < 16:
        raise RomFormatError(f"Arquivo NARC pequeno demais: {relative_path}.")
    stream.seek(entry.start)
    header = _read_exact(stream, 16, str(relative_path))
    if header[:4] != b"NARC" or header[4:6] != b"\xfe\xff":
        raise RomFormatError(f"Cabeçalho NARC inválido: {relative_path}.")

    declared_size = struct.unpack_from("<I", header, 8)[0]
    chunk_count = struct.unpack_from("<H", header, 14)[0]
    declared_end = entry.start + declared_size
    if declared_size < 16 or declared_end > rom_size:
        raise RomFormatError(f"Tamanho declarado no NARC ultrapassa a ROM: {relative_path}.")
    if chunk_count < 1 or chunk_count > 32:
        raise RomFormatError(f"Quantidade de blocos NARC inválida: {relative_path}.")

    # Some patched dumps have a FAT end offset shorter than the NARC's own
    # size. Permit recovery only if the header's full region stays inside the
    # ROM and does not overlap any other FAT-allocated file.
    for other in fat_entries:
        if other.file_id == entry.file_id or other.size == 0:
            continue
        if other.start < declared_end and other.end > entry.start:
            raise RomFormatError(
                f"O tamanho declarado de {relative_path} sobrepõe outro arquivo FAT ({other.file_id})."
            )

    cursor = 16
    chunk_ids: set[bytes] = set()
    for _ in range(chunk_count):
        if cursor + 8 > declared_size:
            raise RomFormatError(f"Lista de blocos NARC truncada: {relative_path}.")
        stream.seek(entry.start + cursor)
        chunk_header = _read_exact(stream, 8, f"bloco NARC de {relative_path}")
        chunk_id = chunk_header[:4]
        chunk_size = struct.unpack_from("<I", chunk_header, 4)[0]
        if chunk_id not in (b"BTAF", b"BTNF", b"GMIF") or chunk_id in chunk_ids:
            raise RomFormatError(f"Identificador de bloco NARC inválido/duplicado: {relative_path}.")
        if chunk_size < 8 or cursor + chunk_size > declared_size:
            raise RomFormatError(f"Tamanho de bloco NARC inválido: {relative_path}.")
        chunk_ids.add(chunk_id)
        cursor += chunk_size

    if not {b"BTAF", b"BTNF", b"GMIF"}.issubset(chunk_ids):
        raise RomFormatError(f"Blocos essenciais ausentes no NARC: {relative_path}.")
    return declared_size


def extract_localization(
    rom_path: str | Path,
    destination: str | Path,
    *,
    force: bool = False,
) -> list[dict[str, str | int | bool]]:
    """Extract the allowlisted localized archives to destination; return metadata only."""
    rom_path = Path(rom_path).expanduser().resolve()
    destination = Path(destination).expanduser().absolute()  # Preserve the root path so symlinks can be rejected.
    files, fat_entries, rom_size = _index_rom(rom_path)
    selected: list[tuple[PurePosixPath, RomFile, int]] = []

    with rom_path.open("rb") as stream:
        for relative_path in TARGET_FILES:
            entry = files.get(relative_path.as_posix().casefold())
            if entry is None:
                raise RomFormatError(f"Arquivo necessário não encontrado na ROM: {relative_path}.")
            effective_size = _validated_narc_size(stream, entry, fat_entries, rom_size, relative_path)
            relative_name = relative_path.as_posix()
            expected_sha256 = PTBR_RESOURCE_SHA256.get(relative_name)
            if expected_sha256 is None:
                raise RomFormatError(
                    f"Não existe SHA-256 aprovado para o recurso localizado {relative_name}."
                )
            actual_sha256 = _sha256_region(stream, entry.start, effective_size)
            if actual_sha256 != expected_sha256:
                raise RomFormatError(
                    f"O SHA-256 de {relative_name} não corresponde à variante PT-BR aprovada "
                    f"(esperado {expected_sha256}, recebido {actual_sha256}). "
                    "Nenhum arquivo foi escrito; confira se a ROM de origem é a tradução suportada."
                )
            selected.append((relative_path, entry, effective_size))

    if destination.is_symlink():
        raise RomFormatError(f"Diretório de destino não pode ser link simbólico: {destination}.")
    if destination.exists() and not destination.is_dir():
        raise RomFormatError(f"Destino existe e não é diretório: {destination}.")

    output_paths = [
        (destination.joinpath(*path.parts), path, entry, effective_size)
        for path, entry, effective_size in selected
    ]

    # Validate existing targets without creating any directories. A rejected
    # ROM must not leave a new runtime directory or mutate paths through links.
    if destination.exists():
        for target, relative_path, _entry, _effective_size in output_paths:
            current = destination
            for component in relative_path.parts[:-1]:
                current = current / component
                if current.is_symlink():
                    raise RomFormatError(
                        f"Diretório de destino não pode ser link simbólico: {current}."
                    )
                if current.exists() and not current.is_dir():
                    raise RomFormatError(
                        f"Componente do destino não é diretório: {current}."
                    )
            if target.is_symlink():
                raise RomFormatError(
                    f"Arquivo de destino não pode ser link simbólico: {target}."
                )
            if target.exists() and not target.is_file():
                raise RomFormatError(
                    f"Destino já existe e não é arquivo regular: {target}."
                )

    existing = [
        str(target)
        for target, _relative, _entry, _size in output_paths
        if target.exists()
    ]
    if existing and not force:
        raise FileExistsError(
            "Arquivos de destino já existem; nada foi substituído. Use --force para sobrescrevê-los:\n  "
            + "\n  ".join(existing)
        )

    # Stage beside the destination so every final rename remains on the same
    # filesystem, but keep all staged bytes outside the live runtime tree.
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise RomFormatError(f"Destino deixou de ser um diretório seguro: {destination}.")
    transaction_root = Path(
        tempfile.mkdtemp(prefix=".ptbr-localization-", dir=destination.parent)
    )
    staged_root = transaction_root / "staged"
    backup_root = transaction_root / "backup"
    written: list[dict[str, str | int | bool]] = []
    moved_backups: list[tuple[Path, Path]] = []
    installed_targets: list[Path] = []
    created_directories: list[Path] = []
    destination_created = False

    try:
        with rom_path.open("rb") as source:
            for target, relative_path, entry, effective_size in output_paths:
                staged_target = staged_root.joinpath(*relative_path.parts)
                staged_target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with staged_target.open("xb") as temporary:
                    source.seek(entry.start)
                    remaining = effective_size
                    while remaining:
                        chunk = source.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            raise RomFormatError(
                                f"ROM truncada durante a extração de {relative_path}."
                            )
                        temporary.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)
                    temporary.flush()
                    os.fsync(temporary.fileno())

                digest_text = digest.hexdigest()
                expected_sha256 = PTBR_RESOURCE_SHA256[relative_path.as_posix()]
                if digest_text != expected_sha256:
                    raise RomFormatError(
                        f"O SHA-256 de {relative_path} mudou durante a extração "
                        "da ROM. Nenhum arquivo de destino foi substituído."
                    )

                written.append({
                    "path": relative_path.as_posix(),
                    "size_bytes": effective_size,
                    "fat_size_bytes": entry.size,
                    "size_recovered_from_narc_header": effective_size != entry.size,
                    "sha256": digest_text,
                })

        # Validate and make the destination only after all bytes and hashes pass.
        if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
            raise RomFormatError(f"Destino deixou de ser um diretório seguro: {destination}.")
        if not destination.exists():
            destination.mkdir()
            destination_created = True
            created_directories.append(destination)

        for target, relative_path, _entry, _size in output_paths:
            current = destination
            for component in relative_path.parts[:-1]:
                current = current / component
                if current.is_symlink():
                    raise RomFormatError(
                        f"Diretório de destino não pode ser link simbólico: {current}."
                    )
                if current.exists():
                    if not current.is_dir():
                        raise RomFormatError(
                            f"Componente do destino não é diretório: {current}."
                        )
                else:
                    current.mkdir()
                    created_directories.append(current)
            if target.is_symlink():
                raise RomFormatError(
                    f"Arquivo de destino não pode ser link simbólico: {target}."
                )
            if target.exists() and not target.is_file():
                raise RomFormatError(
                    f"Destino já existe e não é arquivo regular: {target}."
                )

        # Recheck destinations at the last responsible moment; another process
        # must not cause --force-free imports to overwrite newly created files.
        existing = [
            str(target)
            for target, _relative, _entry, _size in output_paths
            if target.exists()
        ]
        if existing and not force:
            raise FileExistsError(
                "Arquivos de destino apareceram durante a importação; nada foi substituído:\n  "
                + "\n  ".join(existing)
            )

        # Back up all prior files first, then install the fully validated set.
        for target, relative_path, _entry, _size in output_paths:
            if target.exists():
                backup_target = backup_root.joinpath(*relative_path.parts)
                backup_target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, backup_target)
                moved_backups.append((target, backup_target))

        for target, relative_path, _entry, _size in output_paths:
            staged_target = staged_root.joinpath(*relative_path.parts)
            os.replace(staged_target, target)
            installed_targets.append(target)

    except Exception as install_error:
        rollback_errors: list[str] = []
        for target in reversed(installed_targets):
            try:
                target.unlink(missing_ok=True)
            except OSError as rollback_error:
                rollback_errors.append(f"remoção de {target}: {rollback_error}")

        for target, backup_target in reversed(moved_backups):
            try:
                if target.exists() or target.is_symlink():
                    if target.is_dir() and not target.is_symlink():
                        raise OSError(f"Destino inesperadamente virou diretório: {target}")
                    target.unlink()
                if backup_target.exists():
                    os.replace(backup_target, target)
            except OSError as rollback_error:
                rollback_errors.append(f"restauração de {target}: {rollback_error}")

        if rollback_errors:
            raise OSError(
                "A importação de localização falhou e a restauração não terminou. "
                f"Backups preservados em {transaction_root}. "
                + "; ".join(rollback_errors)
            ) from install_error

        shutil.rmtree(transaction_root, ignore_errors=True)
        # A failed first install should restore the filesystem to its prior
        # shape too, including empty folders created solely for this import.
        for directory in reversed(created_directories):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise

    shutil.rmtree(transaction_root, ignore_errors=True)
    return written




LOCALIZATION_PACKAGE_MANIFEST = "localization-manifest.json"


def _sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _safe_package_file(root: Path, relative_path: PurePosixPath) -> Path:
    current = root
    for index, component in enumerate(relative_path.parts):
        if component in ("", ".", "..") or "/" in component or "\\" in component:
            raise RomFormatError("Caminho inseguro no pacote de localização.")
        current = current / component
        try:
            current_stat = current.lstat()
        except OSError as error:
            raise RomFormatError(
                f"Arquivo ausente no pacote de localização: {relative_path}."
            ) from error
        if stat.S_ISLNK(current_stat.st_mode):
            raise RomFormatError(f"Link simbólico não permitido no pacote: {relative_path}.")
        if index < len(relative_path.parts) - 1:
            if not stat.S_ISDIR(current_stat.st_mode):
                raise RomFormatError(f"Componente não é diretório no pacote: {relative_path}.")
        elif not stat.S_ISREG(current_stat.st_mode):
            raise RomFormatError(f"Recurso do pacote não é arquivo regular: {relative_path}.")
    return current


def verify_localization_package(package_path: str | Path) -> dict[str, object]:
    """Validate the complete isolated PT-BR package and all seven resource hashes."""
    root = Path(package_path).expanduser().absolute()
    try:
        root_stat = root.lstat()
    except OSError as error:
        raise RomFormatError(f"Pacote de localização ausente: {root}.") from error
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise RomFormatError("A raiz do pacote deve ser um diretório real, sem link simbólico.")

    manifest_path = _safe_package_file(root, PurePosixPath(LOCALIZATION_PACKAGE_MANIFEST))
    try:
        package_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RomFormatError("Manifesto do pacote PT-BR ausente ou inválido.") from error

    if not isinstance(package_manifest, dict):
        raise RomFormatError("O manifesto PT-BR deve ser um objeto JSON.")
    if (package_manifest.get("schemaVersion") != 1
            or package_manifest.get("game") != "pokemon-platinum"
            or package_manifest.get("locale") != "pt-BR"
            or package_manifest.get("baseRomSha1") != PLATINUM_USA_REV1_SHA1
            or package_manifest.get("sourceRomSha1") != PTBR_SOURCE_ROM_SHA1
            or package_manifest.get("resourceCount") != len(TARGET_FILES)):
        raise RomFormatError("Identidade ou compatibilidade do pacote PT-BR é inválida.")

    resources = package_manifest.get("resources")
    expected_paths = [item.as_posix() for item in TARGET_FILES]
    if not isinstance(resources, list) or len(resources) != len(expected_paths):
        raise RomFormatError("A quantidade de recursos do pacote PT-BR é inválida.")

    expected_files = {LOCALIZATION_PACKAGE_MANIFEST}
    expected_directories: set[str] = set()
    for index, expected_name in enumerate(expected_paths):
        entry = resources[index]
        if not isinstance(entry, dict) or entry.get("path") != expected_name:
            raise RomFormatError("A lista de recursos PT-BR não corresponde à allowlist.")
        expected_sha256 = PTBR_RESOURCE_SHA256.get(expected_name)
        if expected_sha256 is None or entry.get("sha256") != expected_sha256:
            raise RomFormatError(f"SHA-256 de referência incorreto no manifesto: {expected_name}.")
        size = entry.get("sizeBytes")
        fat_size = entry.get("fatSizeBytes")
        recovered = entry.get("sizeRecoveredFromNarcHeader")
        if (not isinstance(size, int) or isinstance(size, bool) or size <= 0
                or not isinstance(fat_size, int) or isinstance(fat_size, bool) or fat_size < 0
                or not isinstance(recovered, bool)
                or recovered != (size != fat_size)):
            raise RomFormatError(f"Metadados de tamanho inválidos no manifesto: {expected_name}.")

        relative = PurePosixPath(expected_name)
        resource_path = _safe_package_file(root, relative)
        if resource_path.stat().st_size != size:
            raise RomFormatError(f"Tamanho divergente no pacote PT-BR: {expected_name}.")
        if _sha256_file(resource_path) != expected_sha256:
            raise RomFormatError(f"Conteúdo divergente no pacote PT-BR: {expected_name}.")
        expected_files.add(expected_name)
        parent = relative.parent
        while parent != PurePosixPath("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent

    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for item in root.rglob("*"):
        if item.is_symlink():
            raise RomFormatError(f"Link simbólico não permitido no pacote: {item.relative_to(root)}.")
        relative_name = item.relative_to(root).as_posix()
        if item.is_file():
            actual_files.add(relative_name)
        elif item.is_dir():
            actual_directories.add(relative_name)
        else:
            raise RomFormatError(f"Entrada especial não permitida no pacote: {relative_name}.")
    if actual_files != expected_files or actual_directories != expected_directories:
        raise RomFormatError("O pacote contém arquivos ou diretórios fora da allowlist.")

    return package_manifest


def build_localization_package(
    rom_path: str | Path,
    package_path: str | Path,
    *,
    force: bool = False,
) -> dict[str, object]:
    """Build and atomically install an isolated PT-BR resource package."""
    source_rom = Path(rom_path).expanduser().resolve()
    _index_rom(source_rom)
    source_sha1 = _sha1_file(source_rom)
    if source_sha1 != PTBR_SOURCE_ROM_SHA1:
        raise RomFormatError(
            "A ROM PT-BR de origem não corresponde à variante aprovada "
            f"(esperado SHA-1 {PTBR_SOURCE_ROM_SHA1}, recebido {source_sha1})."
        )

    destination = Path(package_path).expanduser().absolute()
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise RomFormatError("O diretório-pai do pacote deve ser um diretório real.")
    if destination.is_symlink():
        raise RomFormatError("A raiz do pacote não pode ser um link simbólico.")
    if destination.exists() and not destination.is_dir():
        raise RomFormatError("O destino do pacote existe e não é diretório.")

    if destination.exists():
        if not force:
            raise FileExistsError(
                f"O pacote PT-BR já existe: {destination}. Use --force somente para substituí-lo."
            )
        marker = destination / LOCALIZATION_PACKAGE_MANIFEST
        if marker.is_symlink() or not marker.is_file():
            raise RomFormatError(
                "O diretório existente não foi criado como pacote PT-BR por esta ferramenta; "
                "ele não será substituído."
            )
        try:
            existing_manifest = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RomFormatError("O pacote existente não possui um manifesto reconhecível.") from error
        if (not isinstance(existing_manifest, dict)
                or existing_manifest.get("schemaVersion") != 1
                or existing_manifest.get("game") != "pokemon-platinum"
                or existing_manifest.get("locale") != "pt-BR"):
            raise RomFormatError(
                "O diretório existente não pertence ao pacote PT-BR gerenciado; "
                "ele não será substituído."
            )

    transaction_root = Path(tempfile.mkdtemp(prefix=".ptbr-package-", dir=parent))
    staged_package = transaction_root / "package"
    previous_package = transaction_root / "previous-package"
    failed_package = transaction_root / "failed-package"
    moved_previous = False
    installed_new = False
    preserve_transaction = False

    try:
        entries = extract_localization(source_rom, staged_package, force=False)
        package_manifest: dict[str, object] = {
            "schemaVersion": 1,
            "game": "pokemon-platinum",
            "locale": "pt-BR",
            "baseRomSha1": PLATINUM_USA_REV1_SHA1,
            "sourceRomSha1": source_sha1,
            "resourceCount": len(entries),
            "resources": [
                {
                    "path": str(entry["path"]),
                    "sizeBytes": int(entry["size_bytes"]),
                    "fatSizeBytes": int(entry["fat_size_bytes"]),
                    "sizeRecoveredFromNarcHeader": bool(
                        entry["size_recovered_from_narc_header"]
                    ),
                    "sha256": str(entry["sha256"]),
                }
                for entry in entries
            ],
        }
        manifest_file = staged_package / LOCALIZATION_PACKAGE_MANIFEST
        with manifest_file.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(package_manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        verify_localization_package(staged_package)

        if destination.exists():
            os.replace(destination, previous_package)
            moved_previous = True

        try:
            os.replace(staged_package, destination)
            installed_new = True
            installed_manifest = verify_localization_package(destination)
        except Exception as install_error:
            rollback_errors: list[str] = []
            if installed_new and destination.exists():
                try:
                    os.replace(destination, failed_package)
                    installed_new = False
                except OSError as rollback_error:
                    rollback_errors.append(str(rollback_error))
            if moved_previous:
                try:
                    os.replace(previous_package, destination)
                    moved_previous = False
                except OSError as rollback_error:
                    rollback_errors.append(str(rollback_error))
            if rollback_errors:
                preserve_transaction = True
                raise OSError(
                    "A instalação do pacote PT-BR falhou e o rollback não terminou. "
                    f"Backup preservado em {previous_package}: " + "; ".join(rollback_errors)
                ) from install_error
            raise

        shutil.rmtree(transaction_root, ignore_errors=True)
        return installed_manifest

    except Exception:
        if moved_previous and previous_package.exists() and not destination.exists():
            try:
                os.replace(previous_package, destination)
                moved_previous = False
            except OSError as rollback_error:
                preserve_transaction = True
                raise OSError(
                    "A instalação do pacote PT-BR falhou e o pacote anterior não pôde ser "
                    f"restaurado. Backup preservado em {previous_package}: {rollback_error}"
                )
        if not preserve_transaction:
            shutil.rmtree(transaction_root, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera um pacote PT-BR isolado e validado para o porte nativo de Pokémon Platinum."
    )
    parser.add_argument("--rom", required=True, help="Caminho local para a ROM PT-BR aprovada do próprio usuário.")
    parser.add_argument(
        "--package", required=True,
        help="Diretório privado de saída do pacote PT-BR; não use a pasta raiz do runtime."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Substitui somente um pacote PT-BR gerenciado previamente por esta ferramenta."
    )
    args = parser.parse_args(argv)

    try:
        package = build_localization_package(args.rom, args.package, force=args.force)
    except (OSError, RomFormatError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    print("Pacote PT-BR isolado criado e verificado.")
    print(f"Destino: {Path(args.package).expanduser().absolute()}")
    print(f"ROM de origem SHA-1: {package['sourceRomSha1']}")
    print(f"ROM-base compatível SHA-1: {package['baseRomSha1']}")
    for entry in package["resources"]:
        recovered = (
            " (tamanho recuperado do cabeçalho NARC; FAT divergente)"
            if entry["sizeRecoveredFromNarcHeader"]
            else ""
        )
        print(f"  {entry['path']}: {entry['sizeBytes']} bytes (SHA-256 {entry['sha256']}){recovered}")
    print("O pacote contém somente recursos allowlisted e metadados; a ROM e o runtime original não foram modificados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
