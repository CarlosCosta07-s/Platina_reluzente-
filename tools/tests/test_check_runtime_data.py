from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from import_localization import TARGET_FILES  # noqa: E402
from check_runtime_data import RuntimeDataError, inspect_runtime_directory  # noqa: E402


def _narc() -> bytes:
    btaf = b"BTAF" + (12).to_bytes(4, "little") + b"\x00\x00\x00\x00"
    btnf = b"BTNF" + (8).to_bytes(4, "little")
    gmif = b"GMIF" + (8).to_bytes(4, "little")
    size = 16 + len(btaf) + len(btnf) + len(gmif)
    header = b"NARC\xfe\xff\x00\x01" + size.to_bytes(4, "little") + (16).to_bytes(2, "little") + (3).to_bytes(2, "little")
    return header + btaf + btnf + gmif


def _runtime(root: Path, *, include_all_narc: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "main").write_bytes(b"native executable")
    (root / "header.bin").write_bytes(b"H" * 0x4000)
    for name in ("arm9.bin", "arm7.bin", "arm9ovt.bin", "arm7ovt.bin", "banner.bin", "rsasig.bin"):
        (root / name).write_bytes(b"data")
    (root / "fnt.bin").write_bytes(b"FNT DATA!")
    (root / "fat.bin").write_bytes(b"F" * 8)
    (root / "overlay9").mkdir()
    (root / "overlay7").mkdir()
    (root / "overlay9" / "overlay9_1.bin").write_bytes(b"ov9")
    (root / "overlay7" / "overlay7_1.bin").write_bytes(b"ov7")
    if include_all_narc:
        for relative in TARGET_FILES:
            target = root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_narc())
    return root


class RuntimeDataCheckTests(unittest.TestCase):
    def test_core_runtime_files_pass_without_localization_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = inspect_runtime_directory(_runtime(Path(tmp) / "runtime"))
            self.assertTrue(report["ready_for_launch_attempt"])
            self.assertEqual(report["executable"], "main")
            self.assertEqual(report["missing"], [])
            self.assertEqual(report["invalid"], [])

    def test_require_localized_resources_checks_all_allowlisted_narc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = inspect_runtime_directory(
                _runtime(Path(tmp) / "runtime"),
                require_localized_resources=True,
            )
            self.assertTrue(report["ready_for_launch_attempt"])
            self.assertEqual(len(report["localized_resources_valid"]), len(TARGET_FILES))

    def test_missing_runtime_core_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _runtime(Path(tmp) / "runtime")
            (root / "arm9.bin").unlink()
            report = inspect_runtime_directory(root)
            self.assertFalse(report["ready_for_launch_attempt"])
            self.assertIn("arm9.bin", report["missing"])

    def test_missing_localized_archive_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _runtime(Path(tmp) / "runtime", include_all_narc=False)
            report = inspect_runtime_directory(root, require_localized_resources=True)
            self.assertFalse(report["ready_for_launch_attempt"])
            self.assertEqual(len(report["missing"]), len(TARGET_FILES))

    def test_invalid_narc_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _runtime(Path(tmp) / "runtime")
            target = root.joinpath(*TARGET_FILES[0].parts)
            target.write_bytes(b"not a NARC")
            report = inspect_runtime_directory(root, require_localized_resources=True)
            self.assertFalse(report["ready_for_launch_attempt"])
            self.assertTrue(any(item["path"] == TARGET_FILES[0].as_posix() for item in report["invalid"]))

    def test_missing_runtime_directory_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeDataError):
                inspect_runtime_directory(Path(tmp) / "missing")


if __name__ == "__main__":
    unittest.main()
