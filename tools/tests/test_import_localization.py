from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from import_localization import RomFormatError, extract_localization  # noqa: E402


def _narc(label: bytes) -> bytes:
    payload = label[:4].ljust(4, b"_")
    btaf = b"BTAF" + struct.pack("<I", 12) + struct.pack("<HH", 1, 0)
    btnf = b"BTNF" + struct.pack("<I", 8)
    gmif = b"GMIF" + struct.pack("<I", 8 + len(payload)) + payload
    total_size = 16 + len(btaf) + len(btnf) + len(gmif)
    header = b"NARC\xfe\xff\x00\x01" + struct.pack("<IHH", total_size, 16, 3)
    return header + btaf + btnf + gmif


def _file_entry(name: str) -> bytes:
    encoded = name.encode("ascii")
    return bytes([len(encoded)]) + encoded


def _dir_entry(name: str, directory_id: int) -> bytes:
    encoded = name.encode("ascii")
    return bytes([0x80 | len(encoded)]) + encoded + struct.pack("<H", directory_id)


def _synthetic_rom(
    *, missing_scenario: bool = False, short_pl_msg_fat: bool = False
) -> tuple[bytes, int]:
    root_names = _dir_entry("msgdata", 0xF001) + _file_entry("root.bin") + b"\0"
    msg_names = (
        _file_entry("msg.narc")
        + _file_entry("pl_msg.narc")
        + (b"" if missing_scenario else _dir_entry("scenario", 0xF002))
        + b"\0"
    )
    scenario_names = b"\0" if missing_scenario else _file_entry("scr_msg.narc") + b"\0"
    table_size = 3 * 8
    root_offset = table_size
    msg_offset = root_offset + len(root_names)
    scenario_offset = msg_offset + len(msg_names)
    fnt = bytearray(table_size) + root_names + msg_names + scenario_names
    struct.pack_into("<IHH", fnt, 0, root_offset, 0, 3)
    struct.pack_into("<IHH", fnt, 8, msg_offset, 1, 0xF000)
    struct.pack_into("<IHH", fnt, 16, scenario_offset, 3, 0xF001)

    files = [b"ROOT", _narc(b"MSG1"), _narc(b"PLUR"), _narc(b"SCEN")]
    fnt_offset = 0x200
    fat_offset = (fnt_offset + len(fnt) + 3) & ~3
    fat_size = len(files) * 8
    data_offset = (fat_offset + fat_size + 3) & ~3

    ranges: list[tuple[int, int, int]] = []
    cursor = data_offset
    for file_id, item in enumerate(files):
        start, actual_end = cursor, cursor + len(item)
        fat_end = actual_end - 2 if short_pl_msg_fat and file_id == 2 else actual_end
        ranges.append((start, fat_end, actual_end))
        cursor = actual_end + 64

    rom = bytearray(cursor)
    rom[:12] = b"POKEMON PL\0\0"
    rom[12:16] = b"CPUE"
    struct.pack_into("<II", rom, 0x40, fnt_offset, len(fnt))
    struct.pack_into("<II", rom, 0x48, fat_offset, fat_size)
    rom[fnt_offset:fnt_offset + len(fnt)] = fnt

    fat = bytearray()
    for item, (start, fat_end, actual_end) in zip(files, ranges):
        fat += struct.pack("<II", start, fat_end)
        rom[start:actual_end] = item
    rom[fat_offset:fat_offset + len(fat)] = fat
    return bytes(rom), fat_offset


class LocalizationImportTests(unittest.TestCase):
    def test_extracts_only_the_three_expected_text_archives(self) -> None:
        rom_data, _fat_offset = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "test.nds"
            destination = root / "out"
            rom.write_bytes(rom_data)
            result = extract_localization(rom, destination)
            self.assertEqual(
                [entry["path"] for entry in result],
                ["msgdata/msg.narc", "msgdata/pl_msg.narc", "msgdata/scenario/scr_msg.narc"],
            )
            self.assertEqual((destination / "msgdata/msg.narc").read_bytes(), _narc(b"MSG1"))
            self.assertEqual((destination / "msgdata/pl_msg.narc").read_bytes(), _narc(b"PLUR"))
            self.assertEqual((destination / "msgdata/scenario/scr_msg.narc").read_bytes(), _narc(b"SCEN"))
            self.assertEqual(len(list(destination.rglob("*.*"))), 3)

    def test_recovers_narc_size_when_short_fat_end_is_inside_unallocated_gap(self) -> None:
        rom_data, _fat_offset = _synthetic_rom(short_pl_msg_fat=True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "patched.nds"
            destination = root / "out"
            rom.write_bytes(rom_data)
            result = extract_localization(rom, destination)
            recovered = result[1]
            self.assertEqual(recovered["path"], "msgdata/pl_msg.narc")
            self.assertTrue(recovered["size_recovered_from_narc_header"])
            self.assertEqual((destination / "msgdata/pl_msg.narc").read_bytes(), _narc(b"PLUR"))

    def test_rejects_narc_size_recovery_that_overlaps_another_fat_file(self) -> None:
        rom_data, fat_offset = _synthetic_rom(short_pl_msg_fat=True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "overlap.nds"
            destination = root / "out"
            altered = bytearray(rom_data)
            pl_start = struct.unpack_from("<I", altered, fat_offset + 2 * 8)[0]
            overlap_start = pl_start + len(_narc(b"PLUR")) - 1
            struct.pack_into("<II", altered, fat_offset + 3 * 8, overlap_start, overlap_start + 20)
            rom.write_bytes(altered)
            with self.assertRaisesRegex(RomFormatError, "sobrepõe outro arquivo FAT"):
                extract_localization(rom, destination)
            self.assertFalse(destination.exists())

    def test_rejects_a_different_game_code(self) -> None:
        rom_data, _fat_offset = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "wrong.nds"
            altered = bytearray(rom_data)
            altered[12:16] = b"XXXX"
            rom.write_bytes(altered)
            with self.assertRaises(RomFormatError):
                extract_localization(rom, root / "out")

    def test_missing_text_file_fails_without_creating_output(self) -> None:
        rom_data, _fat_offset = _synthetic_rom(missing_scenario=True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "missing.nds"
            destination = root / "out"
            rom.write_bytes(rom_data)
            with self.assertRaises(RomFormatError):
                extract_localization(rom, destination)
            self.assertFalse(destination.exists())

    def test_invalid_fat_range_is_rejected(self) -> None:
        rom_data, fat_offset = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "bad-fat.nds"
            altered = bytearray(rom_data)
            struct.pack_into("<II", altered, fat_offset + 8, len(altered) + 100, len(altered) + 120)
            rom.write_bytes(altered)
            with self.assertRaises(RomFormatError):
                extract_localization(rom, root / "out")

    def test_existing_output_is_not_overwritten_without_force(self) -> None:
        rom_data, _fat_offset = _synthetic_rom()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "test.nds"
            destination = root / "out"
            target = destination / "msgdata/msg.narc"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"preserve me")
            rom.write_bytes(rom_data)
            with self.assertRaises(FileExistsError):
                extract_localization(rom, destination)
            self.assertEqual(target.read_bytes(), b"preserve me")


if __name__ == "__main__":
    unittest.main()
