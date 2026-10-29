from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.create_runtime_manifest import RuntimeManifestError, create_runtime_manifest


class RuntimeManifestTests(unittest.TestCase):
    def test_manifest_is_sorted_size_accurate_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime-data"
            nested = runtime / "battle" / "skill"
            nested.mkdir(parents=True)
            runtime.mkdir(exist_ok=True)
            header_data = b"header"
            version_data = b"abc123\n"
            archive_data = b"archive data"
            (runtime / "header.bin").write_bytes(header_data)
            (runtime / "build-version.txt").write_bytes(version_data)
            (nested / "waza_seq.narc").write_bytes(archive_data)

            manifest = create_runtime_manifest(runtime)
            first = manifest.read_text(encoding="utf-8")
            expected = [
                f"battle/skill/waza_seq.narc\t{len(archive_data)}",
                f"build-version.txt\t{len(version_data)}",
                f"header.bin\t{len(header_data)}",
            ]
            self.assertEqual(expected, first.splitlines())
            self.assertNotIn("runtime-manifest.txt", first)

            create_runtime_manifest(runtime)
            self.assertEqual(first, manifest.read_text(encoding="utf-8"))

    def test_manifest_rejects_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime-data"
            runtime.mkdir()
            external = Path(tmp) / "external.bin"
            external.write_bytes(b"outside")
            (runtime / "link.bin").symlink_to(external)

            with self.assertRaisesRegex(RuntimeManifestError, "Symlinks are not allowed"):
                create_runtime_manifest(runtime)

    def test_manifest_rejects_missing_runtime_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeManifestError, "Runtime directory does not exist"):
                create_runtime_manifest(Path(tmp) / "missing")


if __name__ == "__main__":
    unittest.main()
