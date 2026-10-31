from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEST_SOURCES = (
    ROOT / "tools" / "tests" / "cpp" / "touch_input_router_test.cpp",
    ROOT / "tools" / "tests" / "cpp" / "virtual_touch_controls_test.cpp",
)


class MobileTouchControlsTests(unittest.TestCase):
    def test_touch_router_and_virtual_overlay_contracts(self):
        compiler = shutil.which("c++") or shutil.which("g++")
        if compiler is None:
            self.skipTest("A host C++ compiler is not available.")

        for source in TEST_SOURCES:
            self.assertTrue(source.is_file(), f"Missing C++ test: {source}")

        with tempfile.TemporaryDirectory(prefix="platina-virtual-touch-controls-") as directory:
            for source in TEST_SOURCES:
                executable = Path(directory) / source.stem
                compile_result = subprocess.run(
                    [
                        compiler,
                        "-std=c++20",
                        "-Wall",
                        "-Wextra",
                        "-Wpedantic",
                        "-Werror",
                        "-I",
                        str(ROOT),
                        str(source),
                        "-o",
                        str(executable),
                    ],
                    check=False,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(
                    compile_result.returncode,
                    0,
                    compile_result.stdout + compile_result.stderr,
                )

                run_result = subprocess.run(
                    [str(executable)],
                    check=False,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(
                    run_result.returncode,
                    0,
                    run_result.stdout + run_result.stderr,
                )
                print(run_result.stdout, end="")


if __name__ == "__main__":
    unittest.main()
