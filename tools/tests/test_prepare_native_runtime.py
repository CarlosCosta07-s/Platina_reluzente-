import tempfile
import unittest
from pathlib import Path

from scripts.prepare_native_runtime import (
    LEGACY_PATCHED_HEADER_LOAD,
    PATCHED_HEADER_LOAD,
    RuntimePreparationError,
    prepare_native_runtime,
)

UPSTREAM_HEADER = r'''#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>

int main(int argc, char *argv[]) {
#ifdef SDK_BUILD_NX
  // platform-specific setup
#endif
  // Read the first 0x160 bytes of the rom and put it in the HW_ROM_HEADER_BUF
  FILE *romFile;
  romFile = fopen("header.bin", "r");

  if (romFile != NULL) {
    // Read the fields of the struct
    fread((void *)HW_ROM_HEADER_BUF, 1, 0x160, romFile);
    fclose(romFile);
  }
  return 0;
}'''


class NativeRuntimePreparationTests(unittest.TestCase):
    def make_source(self, root: Path, content: str = UPSTREAM_HEADER) -> Path:
        source_dir = root / "subprojects/libntr/libraries/sim/src"
        source_dir.mkdir(parents=True)
        source = source_dir / "sim_main.cpp"
        source.write_text(content, encoding="utf-8")
        return source

    def test_uses_imported_rom_header_and_keeps_packaged_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.make_source(root)
            self.assertTrue(prepare_native_runtime(root))
            content = source.read_text(encoding="utf-8")
            self.assertIn('getenv("PLATINA_IMPORTED_ROM")', content)
            self.assertIn('fopen(importedRomPath, "rb")', content)
            self.assertIn('SDL_AndroidGetInternalStoragePath()', content)
            self.assertIn('std::string(androidInternalStoragePath) + "/roms/current.nds"', content)
            self.assertIn('std::string(androidRuntimeStoragePath) + "/pokeplatinum"', content)
            self.assertIn('std::string(androidInternalStoragePath) + "/roms/current.nds"', content)
            self.assertEqual(1, content.count('const char *androidRuntimeStoragePath = SDL_AndroidGetInternalStoragePath();'))
            self.assertEqual(1, content.count('const char *androidInternalStoragePath = SDL_AndroidGetInternalStoragePath();'))
            self.assertIn('chdir(androidRuntimeDirectory.c_str())', content)
            self.assertIn('#include <SDL2/SDL_system.h>', content)
            self.assertIn(
                """#ifndef SDK_BUILD_ANDROID
#define SDL_MAIN_HANDLED
#endif""",
                content,
            )
            self.assertEqual(1, content.count("SDL_MAIN_HANDLED"))
            self.assertIn(r"importedRomPath[0] != '\0'", content)
            self.assertIn(r'fprintf(stderr, "Android internal storage path is unavailable\n");', content)
            self.assertIn('perror("Changing to the game runtime directory");', content)
            self.assertIn("return 1;", content)
            self.assertIn('fopen("header.bin", "rb")', content)
            self.assertEqual(content.count(PATCHED_HEADER_LOAD), 1)
            self.assertFalse(prepare_native_runtime(root))

    def test_upgrades_the_previous_desktop_only_rom_handoff_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.make_source(
                root,
                '#define SDL_MAIN_HANDLED\n#include <SDL2/SDL.h>\n\nint main(int argc, char *argv[]) {\n'
                + LEGACY_PATCHED_HEADER_LOAD
                + '\n}\n',
            )
            self.assertTrue(prepare_native_runtime(root))
            content = source.read_text(encoding="utf-8")
            self.assertIn('SDL_AndroidGetInternalStoragePath()', content)
            self.assertEqual(content.count(PATCHED_HEADER_LOAD), 1)
            self.assertNotIn(LEGACY_PATCHED_HEADER_LOAD, content)
            self.assertFalse(prepare_native_runtime(root))

    def test_refuses_unknown_upstream_source_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.make_source(root, "// changed upstream source\n")
            with self.assertRaises(RuntimePreparationError):
                prepare_native_runtime(root)
            self.assertEqual(source.read_text(encoding="utf-8"), "// changed upstream source\n")
