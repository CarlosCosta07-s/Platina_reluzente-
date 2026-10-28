from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_runtime_data as checker  # noqa: E402
from import_localization import TARGET_FILES  # noqa: E402


def _narc(label: bytes = b"TEST") -> bytes:
    payload = label[:4].ljust(4, b"_")
    btaf = b"BTAF" + (12).to_bytes(4, "little") + b"\x00\x00\x00\x00"
    btnf = b"BTNF" + (8).to_bytes(4, "little")
    gmif = b"GMIF" + (8 + len(payload)).to_bytes(4, "little") + payload
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


def _mock_ptbr_hashes(label: bytes = b"TEST") -> dict[str, str]:
    digest = hashlib.sha256(_narc(label)).hexdigest()
    return {relative.as_posix(): digest for relative in TARGET_FILES}


class RuntimeDataCheckTests(unittest.TestCase):
    def test_core_runtime_files_pass_without_localization_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = checker.inspect_runtime_directory(_runtime(Path(tmp) / "runtime"))
            self.assertTrue(report["ready_for_launch_attempt"])
            self.assertEqual(report["executable"], "main")
            self.assertEqual(report["missing"], [])
            self.assertEqual(report["invalid"], [])

    def test_require_localized_resources_checks_narc_and_reference_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _runtime(Path(tmp) / "runtime")
            with patch.dict(checker.PTBR_RESOURCE_SHA256, _mock_ptbr_hashes()):
                report = checker.inspect_runtime_directory(root, require_localized_resources=True)
            self.assertTrue(report["ready_for_launch_attempt"])
            self.assertEqual(len(report["localized_resources_valid"]), len(TARGET_FILES))
            self.assertTrue(all(item["status"] == "ptbr_sha256_match" for item in report["localized_resources_valid"]))

    def test_valid_but_wrong_localized_resource_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _runtime(Path(tmp) / "runtime")
            expected = _mock_ptbr_hashes(label=b"GOOD")
            with patch.dict(checker.PTBR_RESOURCE_SHA256, expected):
                # The NARC is structurally sound, but its payload is not the approved payload.
                report = checker.inspect_runtime_directory(root, require_localized_resources=True)
            self.assertFalse(report["ready_for_launch_attempt"])
            self.assertTrue(any("SHA-256" in item["problem"] for item in report["invalid"]))

    def test_missing_runtime_core_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _runtime(Path(tmp) / "runtime")
            (root / "arm9.bin").unlink()
            report = checker.inspect_runtime_directory(root)
            self.assertFalse(report["ready_for_launch_attempt"])
            self.assertIn("arm9.bin", report["missing"])

    def test_missing_localized_archive_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _runtime(Path(tmp) / "runtime", include_all_narc=False)
            report = checker.inspect_runtime_directory(root, require_localized_resources=True)
            self.assertFalse(report["ready_for_launch_attempt"])
            self.assertEqual(len(report["missing"]), len(TARGET_FILES))

    def test_invalid_narc_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _runtime(Path(tmp) / "runtime")
            target = root.joinpath(*TARGET_FILES[0].parts)
            target.write_bytes(b"not a NARC")
            report = checker.inspect_runtime_directory(root, require_localized_resources=True)
            self.assertFalse(report["ready_for_launch_attempt"])
            self.assertTrue(any(item["path"] == TARGET_FILES[0].as_posix() for item in report["invalid"]))

    def test_missing_runtime_directory_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(checker.RuntimeDataError):
                checker.inspect_runtime_directory(Path(tmp) / "missing")


if __name__ == "__main__":
    unittest.main()
