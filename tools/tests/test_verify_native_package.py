from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_native_package import PackageVerificationError, verify_native_package  # noqa: E402


def _narc(label: bytes = b"TEST") -> bytes:
    payload = label[:4].ljust(4, b"_")
    btaf = b"BTAF" + (12).to_bytes(4, "little") + b"\x00\x00\x00\x00"
    btnf = b"BTNF" + (8).to_bytes(4, "little")
    gmif = b"GMIF" + (8 + len(payload)).to_bytes(4, "little") + payload
    size = 16 + len(btaf) + len(btnf) + len(gmif)
    header = b"NARC\xfe\xff\x00\x01" + size.to_bytes(4, "little") + (16).to_bytes(2, "little") + (3).to_bytes(2, "little")
    return header + btaf + btnf + gmif


def _tree(root: Path) -> tuple[Path, Path, Path]:
    build = root / "build_linux"
    package = build / "pokeplatinum"
    manifest = root / "platinum.us" / "filesys.csv"
    (build / "res" / "icons").mkdir(parents=True)
    (build / "res" / "moves").mkdir(parents=True)
    (build / "res" / "battle" / "scripts").mkdir(parents=True)
    (package / "icons").mkdir(parents=True)
    (package / "wazaeffect").mkdir(parents=True)
    (package / "battle" / "skill").mkdir(parents=True)
    (build / "res" / "icons" / "test.dat").write_bytes(b"icon")
    (build / "res" / "moves" / "anim_scripts.narc").write_bytes(_narc(b"ANIM"))
    (build / "res" / "battle" / "scripts" / "waza_seq.narc").write_bytes(_narc(b"WAZA"))
    (package / "icons" / "test.dat").write_bytes(b"icon")
    (package / "wazaeffect" / "we.arc").write_bytes(_narc(b"ANIM"))
    (package / "battle" / "skill" / "waza_seq.narc").write_bytes(_narc(b"WAZA"))
    (package / "main").write_bytes(b"native executable")
    (package / "header.bin").write_bytes(b"header")
    (package / "firmware.bin").write_bytes(b"firmware")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Source File", "Target File"])
        writer.writerow(["res/icons/test.dat", "/icons/test.dat"])
        writer.writerow(["res/moves/anim_scripts.narc", "/wazaeffect/we.arc"])
        writer.writerow(["res/battle/scripts/waza_seq.narc", "/battle/skill/waza_seq.narc"])
    return build, package, manifest


class VerifyNativePackageTests(unittest.TestCase):
    def test_complete_package_passes_all_manifest_and_animation_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            build, package, manifest = _tree(Path(tmp))
            report = verify_native_package(build, package, manifest)
            self.assertTrue(report["ready"])
            self.assertEqual(report["manifest_entries"], 3)
            self.assertEqual(report["missing_sources"], [])
            self.assertEqual(report["missing_package_files"], [])

    def test_missing_mapped_package_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            build, package, manifest = _tree(Path(tmp))
            (package / "icons" / "test.dat").unlink()
            report = verify_native_package(build, package, manifest)
            self.assertFalse(report["ready"])
            self.assertTrue(any("icons/test.dat" in p for p in report["missing_package_files"]))

    def test_mismatched_copy_hash_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            build, package, manifest = _tree(Path(tmp))
            (package / "icons" / "test.dat").write_bytes(b"modified")
            report = verify_native_package(build, package, manifest)
            self.assertFalse(report["ready"])
            self.assertTrue(report["hash_mismatches"])

    def test_missing_source_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            build, package, manifest = _tree(Path(tmp))
            (build / "res" / "icons" / "test.dat").unlink()
            report = verify_native_package(build, package, manifest)
            self.assertFalse(report["ready"])
            self.assertTrue(report["missing_sources"])

    def test_invalid_animation_archive_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            build, package, manifest = _tree(Path(tmp))
            (package / "wazaeffect" / "we.arc").write_bytes(b"corrupt")
            report = verify_native_package(build, package, manifest)
            self.assertFalse(report["ready"])
            self.assertEqual(len(report["invalid_animation_archives"]), 1)

    def test_unsafe_path_in_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            build, package, manifest = _tree(Path(tmp))
            with manifest.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["Source File", "Target File"])
                writer.writerow(["../outside.bin", "/icons/test.dat"])
            with self.assertRaises(PackageVerificationError):
                verify_native_package(build, package, manifest)


if __name__ == "__main__":
    unittest.main()
