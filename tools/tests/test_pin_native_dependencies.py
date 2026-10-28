from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent / "scripts"))
from pin_native_dependencies import (  # noqa: E402
    PINNED_DEPENDENCIES,
    PinningError,
    pin_native_dependencies,
)


def _make_native_root(root: Path, *, revision: str = "main") -> Path:
    subprojects = root / "subprojects"
    subprojects.mkdir(parents=True)
    for filename, (url, _sha) in PINNED_DEPENDENCIES.items():
        (subprojects / filename).write_text(
            f"[wrap-git]\nurl = {url}\nrevision = {revision}\ndepth = 1\n",
            encoding="utf-8",
        )
    return root


class PinNativeDependenciesTests(unittest.TestCase):
    def test_pins_all_moving_wrap_revisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            changed = pin_native_dependencies(root)
            self.assertEqual(set(changed), set(PINNED_DEPENDENCIES))
            for filename, (_url, sha) in PINNED_DEPENDENCIES.items():
                content = (root / "subprojects" / filename).read_text(encoding="utf-8")
                self.assertIn(f"revision = {sha}\n", content)
                self.assertNotIn("revision = main", content)

    def test_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            pin_native_dependencies(root)
            self.assertEqual(pin_native_dependencies(root), [])

    def test_rejects_unknown_revision_instead_of_rewriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            path = root / "subprojects" / "libntr.wrap"
            path.write_text(
                path.read_text(encoding="utf-8").replace("revision = main", "revision = feature/custom"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PinningError, "Revisão desconhecida"):
                pin_native_dependencies(root)

    def test_rejects_unexpected_dependency_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            path = root / "subprojects" / "libntr.wrap"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "https://github.com/cybervisi0n/libntr.git",
                    "https://example.invalid/libntr.git",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PinningError, "URL inesperada"):
                pin_native_dependencies(root)

    def test_fails_if_expected_wrap_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            (root / "subprojects" / "libntrdwc.wrap").unlink()
            with self.assertRaisesRegex(PinningError, "ausente"):
                pin_native_dependencies(root)


if __name__ == "__main__":
    unittest.main()
