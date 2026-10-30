from __future__ import annotations

import hashlib
import os
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from localization_manifest import PTBR_RESOURCE_SHA256  # noqa: E402
from import_localization import (  # noqa: E402
    TARGET_FILES,
    RomFormatError,
    extract_localization,
    build_localization_package,
    verify_localization_package,
)


def _narc(label: bytes) -> bytes:
    payload = label[:4].ljust(4, b"_")
    btaf = b"BTAF" + struct.pack("<I", 12) + struct.pack("<HH", 1, 0)
    btnf = b"BTNF" + struct.pack("<I", 8)
    gmif = b"GMIF" + struct.pack("<I", 8 + len(payload)) + payload
    total_size = 16 + len(btaf) + len(btnf) + len(gmif)
    header = b"NARC\xfe\xff\x00\x01" + struct.pack("<IHH", total_size, 16, 3)
    return header + btaf + btnf + gmif


def _extract_synthetic(
    rom: Path,
    destination: Path,
    file_ids: dict[str, int],
    file_data: dict[int, bytes],
    **kwargs: object,
) -> list[dict[str, str | int | bool]]:
    synthetic_hashes = {
        target.as_posix(): hashlib.sha256(
            file_data[file_ids[target.as_posix()]]
        ).hexdigest()
        for target in TARGET_FILES
        if target.as_posix() in file_ids
    }
    with patch.dict(PTBR_RESOURCE_SHA256, synthetic_hashes, clear=True):
        return extract_localization(rom, destination, **kwargs)




def _build_synthetic_package(
    rom: Path,
    package: Path,
    file_ids: dict[str, int],
    file_data: dict[int, bytes],
    **kwargs: object,
) -> dict[str, object]:
    synthetic_hashes = {
        target.as_posix(): hashlib.sha256(
            file_data[file_ids[target.as_posix()]]
        ).hexdigest()
        for target in TARGET_FILES
        if target.as_posix() in file_ids
    }
    source_sha1 = hashlib.sha1(rom.read_bytes()).hexdigest()
    with patch.dict(PTBR_RESOURCE_SHA256, synthetic_hashes, clear=True):
        with patch("import_localization.PTBR_SOURCE_ROM_SHA1", source_sha1):
            return build_localization_package(rom, package, **kwargs)


def _align4(value: int) -> int:
    return (value + 3) & ~3


def _synthetic_rom(
    *,
    missing_path: str | None = None,
    short_pl_msg_fat: bool = False,
) -> tuple[bytes, int, dict[str, int], dict[int, tuple[int, int, int]], dict[int, bytes]]:
    paths = ["root.bin"] + [
        target.as_posix()
        for target in TARGET_FILES
        if target.as_posix() != missing_path
    ]
    root: dict[str, object] = {"name": "", "dirs": {}, "files": [], "parent": None}
    for relative_path in paths:
        parts = PurePosixPath(relative_path).parts
        node = root
        for directory_name in parts[:-1]:
            dirs = node["dirs"]
            if directory_name not in dirs:
                dirs[directory_name] = {
                    "name": directory_name,
                    "dirs": {},
                    "files": [],
                    "parent": node,
                }
            node = dirs[directory_name]
        node["files"].append((parts[-1], relative_path))

    nodes: list[dict[str, object]] = []

    def collect(node: dict[str, object], parent: dict[str, object] | None) -> None:
        node["index"] = len(nodes)
        node["dir_id"] = 0xF000 + len(nodes)
        node["parent"] = parent
        nodes.append(node)
        for _name, child in sorted(node["dirs"].items()):
            collect(child, node)

    collect(root, None)

    file_ids: dict[str, int] = {}
    next_file_id = 0

    def assign_file_ids(node: dict[str, object]) -> None:
        nonlocal next_file_id
        node["first_file_id"] = next_file_id
        for _name, relative_path in sorted(node["files"], key=lambda item: item[0]):
            file_ids[relative_path] = next_file_id
            next_file_id += 1
        for _name, child in sorted(node["dirs"].items()):
            assign_file_ids(child)

    assign_file_ids(root)

    name_cursor = len(nodes) * 8
    for node in nodes:
        stream = bytearray()
        for name, child in sorted(node["dirs"].items()):
            encoded = name.encode("ascii")
            stream.append(0x80 | len(encoded))
            stream += encoded
            stream += struct.pack("<H", int(child["dir_id"]))
        for filename, _relative_path in sorted(node["files"], key=lambda item: item[0]):
            encoded = filename.encode("ascii")
            stream.append(len(encoded))
            stream += encoded
        stream.append(0)
        node["name_offset"] = name_cursor
        node["name_stream"] = bytes(stream)
        name_cursor += len(stream)

    fnt = bytearray(len(nodes) * 8)
    for node in nodes:
        if node is root:
            parent_id = len(nodes)
        else:
            parent_id = int(node["parent"]["dir_id"])
        struct.pack_into(
            "<IHH",
            fnt,
            int(node["index"]) * 8,
            int(node["name_offset"]),
            int(node["first_file_id"]),
            parent_id,
        )
    fnt += b"".join(node["name_stream"] for node in nodes)

    path_by_id = {file_id: relative_path for relative_path, file_id in file_ids.items()}
    file_data: dict[int, bytes] = {}
    for file_id in range(len(file_ids)):
        relative_path = path_by_id[file_id]
        if relative_path == "root.bin":
            file_data[file_id] = b"ROOT"
        else:
            file_data[file_id] = _narc(PurePosixPath(relative_path).name.encode("ascii"))

    fnt_offset = 0x200
    fat_offset = _align4(fnt_offset + len(fnt))
    fat_size = len(file_data) * 8
    data_offset = _align4(fat_offset + fat_size)

    ranges: dict[int, tuple[int, int, int]] = {}
    cursor = data_offset
    for file_id, item in sorted(file_data.items()):
        start = cursor
        actual_end = start + len(item)
        fat_end = actual_end
        if short_pl_msg_fat and path_by_id[file_id] == "msgdata/pl_msg.narc":
            fat_end -= 2
        ranges[file_id] = (start, fat_end, actual_end)
        cursor = actual_end + 64

    rom = bytearray(cursor)
    rom[:12] = b"POKEMON PL\0\0"
    rom[12:16] = b"CPUE"
    struct.pack_into("<II", rom, 0x40, fnt_offset, len(fnt))
    struct.pack_into("<II", rom, 0x48, fat_offset, fat_size)
    rom[fnt_offset:fnt_offset + len(fnt)] = fnt

    fat = bytearray()
    for file_id, item in sorted(file_data.items()):
        start, fat_end, actual_end = ranges[file_id]
        fat += struct.pack("<II", start, fat_end)
        rom[start:actual_end] = item
    rom[fat_offset:fat_offset + len(fat)] = fat
    return bytes(rom), fat_offset, file_ids, ranges, file_data


class LocalizationImportTests(unittest.TestCase):
    def test_extracts_only_the_allowlisted_localized_archives(self) -> None:
        rom_data, _fat_offset, _file_ids, _ranges, file_data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Dados São João" / "Platiná Reluzente"
            root.mkdir(parents=True)
            rom = root / "test.nds"
            destination = root / "runtime com acentos"
            rom.write_bytes(rom_data)
            result = _extract_synthetic(rom, destination, _file_ids, file_data)
            self.assertEqual(
                [entry["path"] for entry in result],
                [item.as_posix() for item in TARGET_FILES],
            )
            for target in TARGET_FILES:
                self.assertEqual(
                    (destination / Path(*target.parts)).read_bytes(),
                    file_data[next(i for path, i in _file_ids.items() if path == target.as_posix())],
                )
            outputs = [path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()]
            self.assertEqual(sorted(outputs), sorted(item.as_posix() for item in TARGET_FILES))
            self.assertFalse((destination / "data/utility.bin").exists())
            self.assertFalse((destination / "dwc/utility.bin").exists())

    def test_recovers_pl_msg_size_when_fat_end_is_short_and_unallocated(self) -> None:
        rom_data, _fat_offset, _file_ids, _ranges, _data = _synthetic_rom(short_pl_msg_fat=True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "patched.nds"
            destination = root / "out"
            rom.write_bytes(rom_data)
            result = _extract_synthetic(rom, destination, _file_ids, _data)
            index = [item.as_posix() for item in TARGET_FILES].index("msgdata/pl_msg.narc")
            recovered = result[index]
            self.assertEqual(recovered["path"], "msgdata/pl_msg.narc")
            self.assertTrue(recovered["size_recovered_from_narc_header"])
            self.assertEqual(
                (destination / "msgdata/pl_msg.narc").read_bytes(),
                _data[next(i for path, i in _file_ids.items() if path == "msgdata/pl_msg.narc")],
            )

    def test_rejects_narc_recovery_that_overlaps_another_fat_file(self) -> None:
        rom_data, fat_offset, file_ids, ranges, file_data = _synthetic_rom(short_pl_msg_fat=True)
        altered = bytearray(rom_data)
        pl_msg_id = file_ids["msgdata/pl_msg.narc"]
        pl_start, _pl_fat_end, pl_actual_end = ranges[pl_msg_id]
        overlap_start = pl_start + len(file_data[pl_msg_id]) - 1
        # Reassign root.bin to a range that overlaps the declared NARC interval.
        root_id = file_ids["root.bin"]
        struct.pack_into("<II", altered, fat_offset + root_id * 8, overlap_start, overlap_start + 20)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "overlap.nds"
            destination = root / "out"
            rom.write_bytes(altered)
            with self.assertRaisesRegex(RomFormatError, "sobrepõe outro arquivo FAT"):
                _extract_synthetic(rom, destination, file_ids, file_data)
            self.assertFalse(destination.exists())

    def test_destination_root_symlink_is_rejected_without_touching_external_directory(self) -> None:
        rom_data, _fat_offset, file_ids, _ranges, file_data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "translated.nds"
            outside = root / "outside-runtime"
            destination = root / "runtime-link"
            rom.write_bytes(rom_data)
            outside.mkdir()
            sentinel = outside / "keep.txt"
            sentinel.write_bytes(b"do not touch")
            try:
                destination.symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"Symlinks are unavailable in this environment: {error}")

            with self.assertRaisesRegex(RomFormatError, "link simbólico"):
                _extract_synthetic(rom, destination, file_ids, file_data)

            self.assertEqual(sentinel.read_bytes(), b"do not touch")
            self.assertTrue(destination.is_symlink())

    def test_wrong_localization_hash_fails_before_writing(self) -> None:
        rom_data, _fat_offset, _file_ids, _ranges, _data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "wrong-localization.nds"
            destination = root / "out"
            rom.write_bytes(rom_data)
            with self.assertRaisesRegex(RomFormatError, "SHA-256.*não corresponde"):
                extract_localization(rom, destination)
            self.assertFalse(destination.exists())

    def test_rejects_a_different_game_code(self) -> None:
        rom_data, _fat_offset, _file_ids, _ranges, _data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "wrong.nds"
            altered = bytearray(rom_data)
            altered[12:16] = b"XXXX"
            rom.write_bytes(altered)
            with self.assertRaises(RomFormatError):
                extract_localization(rom, root / "out")

    def test_missing_allowlisted_file_fails_without_creating_output(self) -> None:
        missing = TARGET_FILES[-1].as_posix()
        rom_data, _fat_offset, _file_ids, _ranges, _data = _synthetic_rom(missing_path=missing)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "missing.nds"
            destination = root / "out"
            rom.write_bytes(rom_data)
            with self.assertRaises(RomFormatError):
                _extract_synthetic(rom, destination, _file_ids, _data)
            self.assertFalse(destination.exists())

    def test_rejects_fnt_table_offset_outside_rom_before_writing(self) -> None:
        rom_data, _fat_offset, _file_ids, _ranges, _data = _synthetic_rom()
        altered = bytearray(rom_data)
        struct.pack_into("<II", altered, 0x40, len(altered) + 16, 8)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "fnt-outside-rom.nds"
            destination = root / "out"
            rom.write_bytes(altered)

            with self.assertRaisesRegex(RomFormatError, "Região FNT fora dos limites"):
                extract_localization(rom, destination)

            self.assertFalse(destination.exists())

    def test_rejects_truncated_narc_chunk_before_writing(self) -> None:
        rom_data, _fat_offset, file_ids, ranges, file_data = _synthetic_rom()
        target_path = TARGET_FILES[0].as_posix()
        file_id = file_ids[target_path]
        narc_start = ranges[file_id][0]
        narc_size = len(file_data[file_id])
        altered = bytearray(rom_data)

        # The GMIF chunk begins after the 16-byte NARC header, 12-byte BTAF
        # and 8-byte BTNF. Make its declared size run beyond the NARC boundary.
        struct.pack_into("<I", altered, narc_start + 40, narc_size)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "truncated-narc.nds"
            destination = root / "out"
            rom.write_bytes(altered)

            with self.assertRaisesRegex(RomFormatError, "Tamanho de bloco NARC inválido"):
                _extract_synthetic(rom, destination, file_ids, file_data)

            self.assertFalse(destination.exists())

    def test_invalid_fat_range_is_rejected(self) -> None:
        rom_data, fat_offset, file_ids, _ranges, _data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "bad-fat.nds"
            altered = bytearray(rom_data)
            first_id = file_ids["root.bin"]
            struct.pack_into("<II", altered, fat_offset + first_id * 8, len(altered) + 100, len(altered) + 120)
            rom.write_bytes(altered)
            with self.assertRaises(RomFormatError):
                extract_localization(rom, root / "out")

    def test_existing_output_is_not_overwritten_without_force(self) -> None:
        rom_data, _fat_offset, _file_ids, _ranges, _data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "test.nds"
            destination = root / "out"
            target = destination / Path(*TARGET_FILES[0].parts)
            target.parent.mkdir(parents=True)
            target.write_bytes(b"preserve me")
            rom.write_bytes(rom_data)
            with self.assertRaises(FileExistsError):
                _extract_synthetic(rom, destination, _file_ids, _data)
            self.assertEqual(target.read_bytes(), b"preserve me")


    def test_failed_multi_file_commit_rolls_back_every_localized_archive(self) -> None:
        rom_data, _fat_offset, file_ids, _ranges, file_data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "translated.nds"
            destination = root / "runtime"
            rom.write_bytes(rom_data)

            original_bytes: dict[str, bytes] = {}
            for target in TARGET_FILES:
                output = destination.joinpath(*target.parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                original_bytes[target.as_posix()] = b"old:" + target.as_posix().encode("ascii")
                output.write_bytes(original_bytes[target.as_posix()])

            real_replace = __import__("os").replace
            failing_target = destination.joinpath(*TARGET_FILES[1].parts)

            def fail_during_install(source: str | Path, target: str | Path) -> None:
                source_path = Path(source)
                target_path = Path(target)
                if "staged" in source_path.parts and target_path == failing_target:
                    raise OSError("simulated disk failure during localization install")
                real_replace(source, target)

            with patch("import_localization.os.replace", side_effect=fail_during_install):
                with self.assertRaisesRegex(OSError, "simulated disk failure"):
                    _extract_synthetic(rom, destination, file_ids, file_data, force=True)

            for target in TARGET_FILES:
                output = destination.joinpath(*target.parts)
                self.assertEqual(output.read_bytes(), original_bytes[target.as_posix()])
            self.assertEqual(list(destination.glob(".ptbr-localization-*")), [])



    def test_builds_an_isolated_package_with_manifest_and_leaves_runtime_data_untouched(self) -> None:
        rom_data, _fat_offset, file_ids, _ranges, file_data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "translated.nds"
            rom.write_bytes(rom_data)

            runtime = root / "runtime"
            base_file = runtime / "msgdata" / "pl_msg.narc"
            base_file.parent.mkdir(parents=True)
            base_file.write_bytes(b"original-English-resource")
            package = root / "user-data" / "localizations" / "pt-BR"

            package_manifest = _build_synthetic_package(rom, package, file_ids, file_data)

            self.assertEqual(package_manifest["locale"], "pt-BR")
            self.assertEqual(package_manifest["game"], "pokemon-platinum")
            self.assertEqual(package_manifest["resourceCount"], len(TARGET_FILES))
            self.assertEqual(package_manifest["sourceRomSha1"], hashlib.sha1(rom_data).hexdigest())
            self.assertEqual(base_file.read_bytes(), b"original-English-resource")
            self.assertTrue((package / "localization-manifest.json").is_file())
            for target in TARGET_FILES:
                self.assertTrue(package.joinpath(*target.parts).is_file())
                self.assertFalse(runtime.joinpath(*target.parts).exists())
            self.assertEqual(verify_localization_package(package), package_manifest)

    def test_package_verification_rejects_modified_resource_and_unlisted_file(self) -> None:
        rom_data, _fat_offset, file_ids, _ranges, file_data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "translated.nds"
            rom.write_bytes(rom_data)
            package = root / "localizations" / "pt-BR"
            _build_synthetic_package(rom, package, file_ids, file_data)

            resource = package.joinpath(*TARGET_FILES[0].parts)
            resource.write_bytes(b"tampered")
            with self.assertRaisesRegex(RomFormatError, "Tamanho divergente|Conteúdo divergente"):
                verify_localization_package(package)
            resource.write_bytes(file_data[file_ids[TARGET_FILES[0].as_posix()]])
            (package / "extra.bin").write_bytes(b"not allowlisted")
            with self.assertRaisesRegex(RomFormatError, "fora da allowlist"):
                verify_localization_package(package)

    def test_package_builder_refuses_wrong_source_rom_hash_before_creating_output(self) -> None:
        rom_data, _fat_offset, file_ids, _ranges, file_data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "translated.nds"
            rom.write_bytes(rom_data)
            package = root / "localizations" / "pt-BR"
            with patch.dict(PTBR_RESOURCE_SHA256, {
                target.as_posix(): hashlib.sha256(file_data[file_ids[target.as_posix()]]).hexdigest()
                for target in TARGET_FILES
            }, clear=True):
                with patch("import_localization.PTBR_SOURCE_ROM_SHA1", "0" * 40):
                    with self.assertRaisesRegex(RomFormatError, "ROM PT-BR de origem"):
                        build_localization_package(rom, package)
            self.assertFalse(package.exists())

    def test_package_builder_refuses_to_replace_an_unmanaged_directory(self) -> None:
        rom_data, _fat_offset, file_ids, _ranges, file_data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "translated.nds"
            rom.write_bytes(rom_data)
            package = root / "localizations" / "pt-BR"
            package.mkdir(parents=True)
            sentinel = package / "keep.txt"
            sentinel.write_text("do not replace", encoding="utf-8")
            with self.assertRaisesRegex(RomFormatError, "não foi criado como pacote PT-BR"):
                _build_synthetic_package(rom, package, file_ids, file_data, force=True)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not replace")

    def test_package_builder_replaces_only_a_recognized_package_when_forced(self) -> None:
        rom_data, _fat_offset, file_ids, _ranges, file_data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "translated.nds"
            rom.write_bytes(rom_data)
            package = root / "localizations" / "pt-BR"
            _build_synthetic_package(rom, package, file_ids, file_data)
            previous_manifest = verify_localization_package(package)

            replacement = _build_synthetic_package(rom, package, file_ids, file_data, force=True)

            self.assertEqual(replacement, previous_manifest)
            self.assertEqual(verify_localization_package(package), replacement)
            self.assertEqual(list(package.parent.glob(".ptbr-package-*")), [])

    def test_package_root_symlink_is_rejected_without_touching_target(self) -> None:
        rom_data, _fat_offset, file_ids, _ranges, file_data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "translated.nds"
            rom.write_bytes(rom_data)
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "keep.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            package = root / "pt-BR-link"
            try:
                package.symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"Symlinks are unavailable in this environment: {error}")
            with self.assertRaisesRegex(RomFormatError, "link simbólico"):
                _build_synthetic_package(rom, package, file_ids, file_data)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")

    def test_package_replacement_failure_restores_the_previous_package(self) -> None:
        rom_data, _fat_offset, file_ids, _ranges, file_data = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "translated.nds"
            rom.write_bytes(rom_data)
            package = root / "localizations" / "pt-BR"
            _build_synthetic_package(rom, package, file_ids, file_data)
            old_manifest = verify_localization_package(package)

            real_replace = os.replace
            def fail_stage_install(source: str | Path, target: str | Path) -> None:
                source_path = Path(source)
                target_path = Path(target)
                if source_path.name == "package" and target_path == package:
                    raise OSError("simulated package install failure")
                real_replace(source, target)

            with patch("import_localization.os.replace", side_effect=fail_stage_install):
                with self.assertRaisesRegex(OSError, "simulated package install failure"):
                    _build_synthetic_package(rom, package, file_ids, file_data, force=True)

            self.assertEqual(verify_localization_package(package), old_manifest)
            self.assertEqual(list(package.parent.glob(".ptbr-package-*")), [])



if __name__ == "__main__":
    unittest.main()
