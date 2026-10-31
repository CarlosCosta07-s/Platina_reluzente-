from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools" / "tests" / "cpp" / "imgui_touch_overlay_compile_test.cpp"
TRACKED_HEADER = ROOT / "mobile" / "input" / "imgui_touch_overlay.hpp"
LIBNTR_ROOT: Path | None = None


class MobileImGuiOverlayCompileTests(unittest.TestCase):
    def test_real_pinned_imgui_api_compiles_for_android_surface(self):
        compiler = shutil.which("c++") or shutil.which("g++")
        if compiler is None:
            self.skipTest("A host C++ compiler is not available.")

        if LIBNTR_ROOT is None:
            self.fail("Expected the prepared pinned libntr checkout path as an argument.")

        libntr_root = LIBNTR_ROOT
        include_root = libntr_root / "include"
        simulator_source = libntr_root / "libraries" / "sim" / "src"
        installed_header = simulator_source / "imgui_touch_overlay.hpp"

        for path in (include_root, simulator_source):
            self.assertTrue(path.is_dir(), f"Missing pinned libntr include directory: {path}")
        self.assertTrue(installed_header.is_file(), f"Missing installed overlay header: {installed_header}")
        self.assertEqual(
            installed_header.read_bytes(),
            TRACKED_HEADER.read_bytes(),
            "Installed ImGui overlay header differs from tracked source.",
        )
        self.assertTrue(SOURCE.is_file(), f"Missing overlay compile test: {SOURCE}")

        with tempfile.TemporaryDirectory(prefix="platina-imgui-touch-overlay-") as directory:
            # Syntax-only compilation deliberately uses the real ImGui 1.93
            # header from the pinned libntr source, with the mobile branch enabled.
            command = [
                compiler,
                "-std=c++20",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-DSDK_BUILD_ANDROID",
                "-fsyntax-only",
                "-I", str(simulator_source),
                "-I", str(include_root),
                "-I", str(ROOT / "mobile" / "input"),
                str(SOURCE),
            ]
            result = subprocess.run(
                command,
                check=False,
                text=True,
                capture_output=True,
                cwd=directory,
            )
            self.assertEqual(
                result.returncode,
                0,
                result.stdout + result.stderr,
            )
            print("Pinned ImGui Android overlay header compiled successfully (syntax-only).")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        raise SystemExit("Usage: test_mobile_imgui_overlay_compile.py <pinned-libntr-root>")
    LIBNTR_ROOT = Path(sys.argv.pop(1)).resolve()
    unittest.main()
