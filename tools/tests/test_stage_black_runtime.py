import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.stage_black_runtime import (
    RuntimeStageError,
    parse_ldd_dependencies,
    parse_objdump_imports,
    stage_black_runtime,
    _windows_dependencies,
)


class BlackRuntimeStagingTests(unittest.TestCase):
    def test_linux_dependency_parser_keeps_shared_library_names(self):
        output = """\
        linux-vdso.so.1 (0x00007fff00000000)
        libSDL3.so.0 => /tmp/sdl/libSDL3.so.0 (0x00007f0000000000)
        libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f0000000001)
        /lib64/ld-linux-x86-64.so.2 (0x00007f0000000002)
        """
        parsed = parse_ldd_dependencies(output)
        self.assertEqual(
            [(name, str(path)) for name, path in parsed],
            [
                ("libSDL3.so.0", "/tmp/sdl/libSDL3.so.0"),
                ("libc.so.6", "/lib/x86_64-linux-gnu/libc.so.6"),
                ("ld-linux-x86-64.so.2", "/lib64/ld-linux-x86-64.so.2"),
            ],
        )

    def test_linux_dependency_parser_fails_closed_when_a_library_is_missing(self):
        with self.assertRaisesRegex(RuntimeStageError, "não resolvida"):
            parse_ldd_dependencies("libSDL3.so.0 => not found")

    def test_windows_import_parser_deduplicates_names_case_insensitively(self):
        self.assertEqual(
            parse_objdump_imports(
                "  DLL Name: SDL3.dll\n  DLL Name: KERNEL32.dll\n  DLL Name: sdl3.DLL\n"
            ),
            ["SDL3.dll", "KERNEL32.dll"],
        )


    def test_windows_dependency_closure_is_case_insensitive_across_dlls(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "build"
            source.mkdir()
            executable = source / "eidos.exe"
            executable.write_bytes(b"fake executable")
            sdl = source / "SDL3.dll"
            sdl.write_bytes(b"fake SDL")
            dependency_dir = root / "toolchain" / "bin"
            dependency_dir.mkdir(parents=True)
            helper = dependency_dir / "Helper.dll"
            helper.write_bytes(b"fake helper")

            def fake_objdump(args, **kwargs):
                image_name = Path(args[-1]).name.casefold()
                if image_name == "eidos.exe":
                    output = "  DLL Name: SDL3.dll\n  DLL Name: Helper.dll\n"
                elif image_name == "sdl3.dll":
                    output = "  DLL Name: HELPER.DLL\n"
                elif image_name == "helper.dll":
                    output = "  DLL Name: KERNEL32.dll\n"
                else:
                    raise AssertionError("Unexpected dependency inspected: " + image_name)
                return SimpleNamespace(returncode=0, stdout=output, stderr="")

            with patch("scripts.stage_black_runtime.shutil.which", return_value="objdump"), patch(
                "scripts.stage_black_runtime.subprocess.run", side_effect=fake_objdump
            ), patch(
                "scripts.stage_black_runtime._is_windows_system_dll", return_value=True
            ):
                dependencies = _windows_dependencies(executable, source, [dependency_dir])

            self.assertEqual(set(dependencies), {"SDL3.dll", "Helper.dll"})
            self.assertEqual(dependencies["SDL3.dll"], sdl.resolve())
            self.assertEqual(dependencies["Helper.dll"], helper.resolve())

    def test_linux_staging_copies_only_native_runtime_and_resolved_non_system_libraries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "eidos-build" / "build64" / "host"
            source.mkdir(parents=True)
            executable = source / "eidos"
            executable.write_bytes(b"fake native executable")
            executable.chmod(0o755)

            library = root / "sdl-prefix" / "libSDL3.so.0"
            library.parent.mkdir(parents=True)
            library.write_bytes(b"fake SDL3 shared library")

            # Deliberately put ROM-like and extracted data beside the build. The
            # staging helper must not copy arbitrary files from the build tree.
            (source / "local.nds").write_bytes(b"not to be copied")
            (source / "data").mkdir()
            (source / "data" / "asset.narc").write_bytes(b"not to be copied")

            destination = root / "launcher-app" / "black-runtime"
            with patch(
                "scripts.stage_black_runtime._linux_dependencies",
                return_value={"libSDL3.so.0": library},
            ):
                report = stage_black_runtime(source, destination, "linux")

            self.assertTrue((destination / "eidos").is_file())
            self.assertTrue((destination / "eidos").stat().st_mode & 0o111)
            self.assertEqual(
                (destination / "libSDL3.so.0").read_bytes(),
                b"fake SDL3 shared library",
            )
            self.assertEqual(
                sorted(item.name for item in destination.iterdir()),
                ["eidos", "libSDL3.so.0"],
            )
            self.assertEqual(report["file_count"], 2)
            self.assertFalse((destination / "local.nds").exists())
            self.assertFalse((destination / "data").exists())

    def test_windows_staging_requires_and_copies_sdl3_and_native_dll_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "eidos-build" / "build64" / "host"
            source.mkdir(parents=True)
            (source / "eidos.exe").write_bytes(b"fake Windows executable")
            sdl = source / "SDL3.dll"
            sdl.write_bytes(b"fake SDL3 DLL")
            toolchain = root / "toolchain" / "bin"
            toolchain.mkdir(parents=True)
            c_runtime = toolchain / "libstdc++-6.dll"
            c_runtime.write_bytes(b"fake C++ runtime")
            destination = root / "launcher-app" / "black-runtime"

            with patch(
                "scripts.stage_black_runtime._windows_dependencies",
                return_value={"SDL3.dll": sdl, "libstdc++-6.dll": c_runtime},
            ):
                report = stage_black_runtime(source, destination, "windows")

            self.assertEqual((destination / "eidos.exe").read_bytes(), b"fake Windows executable")
            self.assertEqual((destination / "SDL3.dll").read_bytes(), b"fake SDL3 DLL")
            self.assertEqual((destination / "libstdc++-6.dll").read_bytes(), b"fake C++ runtime")
            self.assertEqual(report["file_count"], 3)

    def test_failed_staging_preserves_previous_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "incomplete-build"
            source.mkdir()
            destination = root / "black-runtime"
            destination.mkdir()
            marker = destination / "preserve.txt"
            marker.write_text("existing runtime", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeStageError, "Executável nativo Eidos"):
                stage_black_runtime(source, destination, "linux")

            self.assertEqual(marker.read_text(encoding="utf-8"), "existing runtime")
            self.assertEqual(sorted(item.name for item in destination.iterdir()), ["preserve.txt"])

    def test_interrupted_staging_restores_previous_runtime_before_new_build_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "incomplete-build"
            source.mkdir()
            destination = root / "black-runtime"
            backup = root / "black-runtime.previous"
            backup.mkdir()
            marker = backup / "preserve.txt"
            marker.write_text("last known runtime", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeStageError, "Executável nativo Eidos"):
                stage_black_runtime(source, destination, "linux")

            self.assertEqual(
                (destination / "preserve.txt").read_text(encoding="utf-8"),
                "last known runtime",
            )
            self.assertFalse(backup.exists())

    def test_failed_atomic_promotion_restores_previous_runtime(self):
        import os

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "eidos-build"
            source.mkdir()
            executable = source / "eidos"
            executable.write_bytes(b"new executable")
            executable.chmod(0o755)

            dependency = root / "libs" / "libSDL3.so.0"
            dependency.parent.mkdir()
            dependency.write_bytes(b"SDL library")

            destination = root / "black-runtime"
            destination.mkdir()
            previous_marker = destination / "preserve.txt"
            previous_marker.write_text("last known runtime", encoding="utf-8")

            real_replace = os.replace

            def fail_new_runtime_promotion(src, dst):
                src_path = Path(src)
                dst_path = Path(dst)
                if src_path.name.startswith(destination.name + ".staging-") and dst_path == destination:
                    raise OSError("simulated atomic promotion failure")
                return real_replace(src, dst)

            with patch(
                "scripts.stage_black_runtime._linux_dependencies",
                return_value={"libSDL3.so.0": dependency},
            ), patch(
                "scripts.stage_black_runtime.os.replace",
                side_effect=fail_new_runtime_promotion,
            ):
                with self.assertRaisesRegex(OSError, "simulated atomic promotion failure"):
                    stage_black_runtime(source, destination, "linux")

            self.assertEqual(
                (destination / "preserve.txt").read_text(encoding="utf-8"),
                "last known runtime",
            )
            self.assertFalse((destination / "eidos").exists())
            self.assertFalse(destination.with_name(destination.name + ".previous").exists())

    def test_runtime_destination_cannot_contain_or_be_contained_by_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "launcher-app" / "black-runtime"
            source = destination / "build64" / "host"
            source.mkdir(parents=True)
            (source / "eidos").write_bytes(b"should not be staged")

            with self.assertRaisesRegex(RuntimeStageError, "não podem conter um ao outro"):
                stage_black_runtime(source, destination, "linux")


if __name__ == "__main__":
    unittest.main()
