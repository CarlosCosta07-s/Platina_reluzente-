import tempfile
import unittest
from pathlib import Path

from scripts.prepare_native_runtime import (
    ANDROID_MAIN_INIT,
    CONFIG_ALARM_SECOND_PATCHED,
    CONFIG_SAVE_OPEN_PATCHED,
    FS_OPEN_FALLBACK_PATCHED,
    GL_LOADER_PATCHED,
    SDL_INIT_PATCHED,
    SDL_WINDOW_CONTEXT_PATCHED,
    MAIN_RENDER_HANDOFF_PATCHED,
    LEGACY_ANDROID_MAIN_INIT,
    LEGACY_PATCHED_HEADER_LOAD,
    ORIGINAL_HEADER_LOAD,
    PREVIOUS_PATCHED_HEADER_LOAD,
    PATCHED_HEADER_LOAD,
    RuntimePreparationError,
    prepare_native_runtime,
)

UPSTREAM_SIM_CONFIG = r'''#include <stdio.h>
#define SIM_CONFIG_FILE_PATH "./sim_config.ini"
static int IniHandler(void* user, const char* section, const char* name, const char* value) {
    if(MATCH("OSNVRAM", "Alarm_Second")) {
        config->osNvramConfig.ncd.alarm.minute = atoi(value);
    }
    return 0;
}
void SIM_Config_SaveConfigFile(SIM_config_type * aConfig)
{
    FILE * configFile = fopen(SIM_CONFIG_FILE_PATH, "w");
    fprintf(configFile, "test=%d\n", aConfig->internalResolutionScale);
    fclose(configFile);
}'''

UPSTREAM_FS_FILE = r'''#include <nitro/os.h>
#ifdef SDK_PORT
#include <string.h>
#include <SDL2/SDL.h>
#include <simulator/sim_RomExtractor.h>
#endif

BOOL FS_OpenFile (FSFile *p_file, const char *path)
{
    if (p_file->pcFilePtr == NULL) {
        #if FS_FILE_OPEN_DEBUG
        char messageBuf[200] = {0};
        snprintf(messageBuf, 199, "Failed to open file '%s'.", path);
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_INFORMATION, "ROM Extraction Required", messageBuf, NULL);
        #else
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_INFORMATION, "ROM Extraction Required", "ROM filesystem is missing. Select 'OK' and choose a NDS ROM file in the next step.", NULL);
        #endif

        SIM_ShowRomExtractionDialog();

        // try again, because the ROM should be extracted at this point
        // yes, this is recursive, so if the user is dumb enough to keep extracting the wrong ROM and does this enough times, it will crash
        return FS_OpenFile(p_file, path);
    }
    return TRUE;
}'''

UPSTREAM_HEADER = r'''#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>

void *SIM_RenderInit(void *arg) {
  SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_TIMER |
           SDL_INIT_JOYSTICK);
  SIM_Audio_Init(44100);
  SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
  SDL_GL_SetSwapInterval(s_SIM_config.vsyncInterval);
  window = SDL_CreateWindow(
      windowTitle.c_str(), 100, 100, windowWidth, windowHeight,
      SDL_WINDOW_SHOWN | SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE);
  context = SDL_GL_CreateContext(window);
  gladLoadGLLoader(SDL_GL_GetProcAddress);
  return NULL;
}

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
  SIM_RenderInit(NULL);
  G3SIM_DrawInit();
  return 0;
}'''


class NativeRuntimePreparationTests(unittest.TestCase):
    def make_source(self, root: Path, content: str = UPSTREAM_HEADER) -> Path:
        source_dir = root / "subprojects/libntr/libraries/sim/src"
        source_dir.mkdir(parents=True)
        source = source_dir / "sim_main.cpp"
        source.write_text(content, encoding="utf-8")
        config = source_dir / "config" / "sim_config.c"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(UPSTREAM_SIM_CONFIG, encoding="utf-8")
        fs_source = root / "subprojects/libntr/libraries/fs/src/fs_file.c"
        fs_source.parent.mkdir(parents=True, exist_ok=True)
        fs_source.write_text(UPSTREAM_FS_FILE, encoding="utf-8")
        return source

    def test_uses_imported_rom_header_and_keeps_desktop_only_fallback(self):
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
            self.assertIn("headerBytesRead != 0x160", content)
            self.assertIn("Incomplete ROM header: expected 352 bytes, read %zu", content)
            self.assertEqual(content.count(PATCHED_HEADER_LOAD), 1)
            config_content = (source.parent / "config" / "sim_config.c").read_text(encoding="utf-8")
            self.assertIn('config->osNvramConfig.ncd.alarm.second = atoi(value);', config_content)
            self.assertNotIn('config->osNvramConfig.ncd.alarm.minute = atoi(value);', config_content)
            self.assertIn('if (configFile == NULL) {\n        return;\n    }', config_content)
            fs_content = (root / "subprojects/libntr/libraries/fs/src/fs_file.c").read_text(encoding="utf-8")
            self.assertIn(FS_OPEN_FALLBACK_PATCHED, fs_content)
            self.assertIn('getenv("PLATINA_IMPORTED_ROM")', fs_content)
            self.assertIn("#ifdef SDK_BUILD_ANDROID", fs_content)
            self.assertIn(SDL_INIT_PATCHED, content)
            self.assertIn(SDL_WINDOW_CONTEXT_PATCHED, content)
            self.assertIn('SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);\n  // Apply VSync only after SDL_GL_CreateContext succeeds.', content)
            self.assertIn('if (SDL_GL_SetSwapInterval(s_SIM_config.vsyncInterval) != 0)', content)
            self.assertIn(GL_LOADER_PATCHED, content)
            self.assertIn(MAIN_RENDER_HANDOFF_PATCHED, content)
            self.assertFalse(prepare_native_runtime(root))

    def test_android_rom_open_failure_does_not_fall_back_to_packaged_header(self):
        android_branch, desktop_branch = PATCHED_HEADER_LOAD.split("#else", 1)
        self.assertIn("Unable to open imported Android ROM", android_branch)
        self.assertIn("return 1;", android_branch)
        self.assertNotIn('fopen("header.bin", "rb")', android_branch)
        self.assertIn('fopen("header.bin", "rb")', desktop_branch)

    def test_upgrades_legacy_android_runtime_path_patch_without_duplicate_chdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy_content = UPSTREAM_HEADER.replace(
                "int main(int argc, char *argv[]) {\n",
                "int main(int argc, char *argv[]) {\n" + LEGACY_ANDROID_MAIN_INIT + "\n",
                1,
            )
            source = self.make_source(root, legacy_content)

            self.assertTrue(prepare_native_runtime(root))
            content = source.read_text(encoding="utf-8")
            self.assertEqual(1, content.count(ANDROID_MAIN_INIT))
            self.assertNotIn(LEGACY_ANDROID_MAIN_INIT, content)
            self.assertIn('perror("Changing to the game runtime directory");', content)
            self.assertEqual(1, content.count("const char *androidRuntimeStoragePath = SDL_AndroidGetInternalStoragePath();"))
            self.assertFalse(prepare_native_runtime(root))


    def test_upgrades_the_previous_patched_rom_header_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous_source = UPSTREAM_HEADER.replace(
                ORIGINAL_HEADER_LOAD, PREVIOUS_PATCHED_HEADER_LOAD, 1
            )
            source = self.make_source(root, previous_source)

            self.assertTrue(prepare_native_runtime(root))
            content = source.read_text(encoding="utf-8")
            self.assertEqual(content.count(PATCHED_HEADER_LOAD), 1)
            self.assertNotIn(PREVIOUS_PATCHED_HEADER_LOAD, content)
            self.assertIn("headerBytesRead != 0x160", content)
            self.assertFalse(prepare_native_runtime(root))

    def test_upgrades_the_previous_desktop_only_rom_handoff_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy_source = UPSTREAM_HEADER.replace(
                ORIGINAL_HEADER_LOAD, LEGACY_PATCHED_HEADER_LOAD, 1
            )
            source = self.make_source(root, legacy_source)
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


    def test_config_patches_are_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.make_source(root)
            config = source.parent / "config" / "sim_config.c"

            self.assertTrue(prepare_native_runtime(root))
            once = config.read_text(encoding="utf-8")
            self.assertEqual(once.count(CONFIG_ALARM_SECOND_PATCHED), 1)
            self.assertEqual(once.count(CONFIG_SAVE_OPEN_PATCHED), 1)

            self.assertFalse(prepare_native_runtime(root))
            self.assertEqual(config.read_text(encoding="utf-8"), once)

    def test_unknown_fs_fallback_fails_before_any_source_file_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.make_source(root)
            original_main = source.read_text(encoding="utf-8")
            config = source.parent / "config" / "sim_config.c"
            original_config = config.read_text(encoding="utf-8")
            fs_source = root / "subprojects/libntr/libraries/fs/src/fs_file.c"
            fs_source.write_text("unknown filesystem fallback\n", encoding="utf-8")

            with self.assertRaises(RuntimePreparationError):
                prepare_native_runtime(root)

            self.assertEqual(source.read_text(encoding="utf-8"), original_main)
            self.assertEqual(config.read_text(encoding="utf-8"), original_config)
            self.assertEqual(fs_source.read_text(encoding="utf-8"), "unknown filesystem fallback\n")

    def test_unknown_sim_config_fails_before_any_source_file_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.make_source(root)
            original_main = source.read_text(encoding="utf-8")
            config = source.parent / "config" / "sim_config.c"
            config.write_text("unknown upstream config implementation\n", encoding="utf-8")

            with self.assertRaises(RuntimePreparationError):
                prepare_native_runtime(root)

            self.assertEqual(source.read_text(encoding="utf-8"), original_main)
            self.assertEqual(
                config.read_text(encoding="utf-8"),
                "unknown upstream config implementation\n",
            )

