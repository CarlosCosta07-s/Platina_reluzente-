from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools" / "tests" / "cpp" / "touch_input_router_test.cpp"
HEADER = ROOT / "mobile" / "input" / "touch_input_router.hpp"


class MobileTouchInputRouterTests(unittest.TestCase):
    def test_host_contracts_compile_and_run(self):
        compiler = shutil.which("c++") or shutil.which("g++")
        if compiler is None:
            self.skipTest("A host C++ compiler is not available.")

        self.assertTrue(HEADER.is_file(), f"Missing touch router header: {HEADER}")
        self.assertTrue(SOURCE.is_file(), f"Missing touch router test: {SOURCE}")

        with tempfile.TemporaryDirectory(prefix="platina-touch-router-") as directory:
            executable = Path(directory) / "touch-input-router-test"
            compile_result = subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Wpedantic",
                    "-Werror",
                    "-I",
                    str(ROOT),
                    str(SOURCE),
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
            self.assertIn("6 scenarios", run_result.stdout)


if __name__ == "__main__":
    unittest.main()
