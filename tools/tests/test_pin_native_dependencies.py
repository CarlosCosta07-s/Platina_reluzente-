from __future__ import annotations

import re
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import pin_native_dependencies as pin_module  # noqa: E402
from pin_native_dependencies import (  # noqa: E402
    PINNED_DEPENDENCIES,
    PinningError,
    pin_native_dependencies,
    restore_native_dependencies,
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


def _revision(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^revision = (\S+)$", content)
    if match is None:
        raise AssertionError(f"No revision found in {path}")
    return match.group(1)


class PinNativeDependenciesTests(unittest.TestCase):
    def test_libvct_is_pinned_to_the_verified_upstream_revision(self) -> None:
        self.assertEqual(
            PINNED_DEPENDENCIES["libvct.wrap"],
            (
                "https://github.com/cybervisi0n/libvct.git",
                "a34ad47fc0d7d964483c287759b704b3b1f3b967",
            ),
        )

    def test_pins_all_moving_wrap_revisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            changed = pin_native_dependencies(root)
            self.assertEqual(set(changed), set(PINNED_DEPENDENCIES))
            for filename, (_url, sha) in PINNED_DEPENDENCIES.items():
                self.assertEqual(_revision(root / "subprojects" / filename), sha)

    def test_failed_wrap_write_rolls_back_earlier_pins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            subprojects = root / "subprojects"
            before = {
                filename: (subprojects / filename).read_text(encoding="utf-8")
                for filename in PINNED_DEPENDENCIES
            }
            real_atomic_write = pin_module._atomic_write
            failed_once = False

            def fail_on_second_wrap(path: Path, content: str) -> None:
                nonlocal failed_once
                if path.name == "libntrsystem.wrap" and not failed_once:
                    failed_once = True
                    raise OSError("simulated failure while pinning second wrap")
                real_atomic_write(path, content)

            with patch.object(pin_module, "_atomic_write", side_effect=fail_on_second_wrap):
                with self.assertRaisesRegex(OSError, "simulated failure"):
                    pin_native_dependencies(root)

            after = {
                filename: (subprojects / filename).read_text(encoding="utf-8")
                for filename in PINNED_DEPENDENCIES
            }
            self.assertTrue(failed_once)
            self.assertEqual(after, before)

    def test_pin_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            pin_native_dependencies(root)
            self.assertEqual(pin_native_dependencies(root), [])

    def test_restore_returns_all_wraps_to_moving_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            pin_native_dependencies(root)
            restored = restore_native_dependencies(root)
            self.assertEqual(set(restored), set(PINNED_DEPENDENCIES))
            for filename in PINNED_DEPENDENCIES:
                self.assertEqual(_revision(root / "subprojects" / filename), "main")

    def test_restore_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            self.assertEqual(restore_native_dependencies(root), [])

    def test_rejects_unknown_revision_without_partial_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            path = root / "subprojects" / "libntrdwc.wrap"
            path.write_text(
                path.read_text(encoding="utf-8").replace("revision = main", "revision = feature/custom"),
                encoding="utf-8",
            )
            before = {
                name: (root / "subprojects" / name).read_text(encoding="utf-8")
                for name in PINNED_DEPENDENCIES
            }
            with self.assertRaisesRegex(PinningError, "Revisão desconhecida"):
                pin_native_dependencies(root)
            after = {
                name: (root / "subprojects" / name).read_text(encoding="utf-8")
                for name in PINNED_DEPENDENCIES
            }
            self.assertEqual(after, before)

    def test_restore_refuses_unknown_revision_without_partial_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            pin_native_dependencies(root)
            path = root / "subprojects" / "libntrdwc.wrap"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "revision = " + PINNED_DEPENDENCIES["libntrdwc.wrap"][1],
                    "revision = feature/custom",
                ),
                encoding="utf-8",
            )
            before = {
                name: (root / "subprojects" / name).read_text(encoding="utf-8")
                for name in PINNED_DEPENDENCIES
            }
            with self.assertRaisesRegex(PinningError, "revisão inesperada"):
                restore_native_dependencies(root)
            after = {
                name: (root / "subprojects" / name).read_text(encoding="utf-8")
                for name in PINNED_DEPENDENCIES
            }
            self.assertEqual(after, before)

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

    def test_fails_if_expected_wrap_is_missing_without_partial_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_native_root(Path(tmp))
            (root / "subprojects" / "libntrdwc.wrap").unlink()
            before = {
                name: (root / "subprojects" / name).read_text(encoding="utf-8")
                for name in PINNED_DEPENDENCIES if (root / "subprojects" / name).exists()
            }
            with self.assertRaisesRegex(PinningError, "ausente"):
                pin_native_dependencies(root)
            after = {
                name: (root / "subprojects" / name).read_text(encoding="utf-8")
                for name in PINNED_DEPENDENCIES if (root / "subprojects" / name).exists()
            }
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
