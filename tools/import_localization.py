#!/usr/bin/env python3
"""Import an allowlisted set of localized Pokémon Platinum NARC files from a local CPUE ROM dump.

This tool never modifies the ROM and writes only to an explicit destination.
It does not distribute or upload ROM data.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

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
    destination = Path(destination).expanduser().resolve()
    files, fat_entries, rom_size = _index_rom(rom_path)
    selected: list[tuple[PurePosixPath, RomFile, int]] = []

    with rom_path.open("rb") as stream:
        for relative_path in TARGET_FILES:
            entry = files.get(relative_path.as_posix().casefold())
            if entry is None:
                raise RomFormatError(f"Arquivo necessário não encontrado na ROM: {relative_path}.")
            effective_size = _validated_narc_size(stream, entry, fat_entries, rom_size, relative_path)
            selected.append((relative_path, entry, effective_size))

    output_paths = [
        (destination.joinpath(*path.parts), path, entry, effective_size)
        for path, entry, effective_size in selected
    ]
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

    written: list[dict[str, str | int | bool]] = []
    with rom_path.open("rb") as source:
        for target, relative_path, entry, effective_size in output_paths:
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            temp_name: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
                ) as temporary:
                    temp_name = temporary.name
                    source.seek(entry.start)
                    remaining = effective_size
                    while remaining:
                        chunk = source.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            raise RomFormatError(f"ROM truncada durante a extração de {relative_path}.")
                        temporary.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temp_name, target)
            except Exception:
                if temp_name is not None:
                    try:
                        os.unlink(temp_name)
                    except FileNotFoundError:
                        pass
                raise
            written.append({
                "path": relative_path.as_posix(),
                "size_bytes": effective_size,
                "fat_size_bytes": entry.size,
                "size_recovered_from_narc_header": effective_size != entry.size,
                "sha256": digest.hexdigest(),
            })

    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Importa recursos NARC localizados explicitamente autorizados de Pokémon Platinum CPUE para um diretório local."
    )
    parser.add_argument("--rom", required=True, help="Caminho local para o arquivo .nds do próprio usuário.")
    parser.add_argument(
        "--destination", required=True,
        help="Diretório de trabalho do executável nativo; os caminhos originais da ROM serão criados abaixo dele."
    )
    parser.add_argument("--force", action="store_true", help="Permite substituir arquivos de destino existentes.")
    args = parser.parse_args(argv)

    try:
        entries = extract_localization(args.rom, args.destination, force=args.force)
    except (OSError, RomFormatError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    print(f"Importação local concluída. Nenhuma ROM foi modificada; ROM de origem: {Path(args.rom).name}")
    for entry in entries:
        recovered = (
            " (tamanho recuperado do cabeçalho NARC; FAT divergente)"
            if entry["size_recovered_from_narc_header"]
            else ""
        )
        print(f"  {entry['path']}: {entry['size_bytes']} bytes (SHA-256 {entry['sha256']}){recovered}")
    print("Mantenha os arquivos extraídos fora do Git e use-os apenas com seu próprio porte local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
