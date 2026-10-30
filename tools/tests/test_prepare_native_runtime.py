import tempfile
import unittest
from pathlib import Path

from scripts.prepare_native_runtime import (
    CONFIG_ALARM_SECOND_PATCHED,
    BACKUP_FILE_IO_HELPERS_PATCHED,
    BACKUP_READ_BODY_PATCHED,
    BACKUP_SAVE_PATH_INCLUDE_PATCHED,
    BACKUP_WRITE_BODY_PATCHED,
    BACKUP_WRITE_VERIFY_BODY_PATCHED,
    CARD_IDENTIFY_BACKUP_ORIGINAL,
    CARD_IDENTIFY_BACKUP_PATCHED,
    CONFIG_SAVE_OPEN_PATCHED,
    FS_OPEN_FALLBACK_PATCHED,
    FS_OPEN_FALLBACK_PATCHED_LEGACY,
    FS_OPEN_FALLBACK_ORIGINAL,
    GL_LOADER_PATCHED,
    SDL_INIT_PATCHED,
    SDL_WINDOW_CONTEXT_PATCHED,
    SDL_VIEWPORT_PATCHED,
    INPUT_RELEASE_HELPER_PATCHED,
    MOUSE_DOWN_DECLARATION_ORIGINAL,
    MOUSE_DOWN_DECLARATION_PATCHED,
    WINDOW_EVENT_PATCHED,
    KEYDOWN_PATCHED,
    MAIN_RENDER_HANDOFF_PATCHED,
    NDS_EXTRACTOR_INPUT_CHECK_ORIGINAL,
    NDS_EXTRACTOR_INPUT_CHECK_PATCHED,
    NVRAM_FILE_READ_PATCHED,
    SIM_AUDIO_OPEN_PATCHED,
    ORIGINAL_HEADER_LOAD,
    PATCHED_HEADER_LOAD,
    ROM_PREFLIGHT_ENTRY_PATCHED,
    ROM_PREFLIGHT_INCLUDE_PATCHED,
    RuntimePreparationError,
    SIM_ROM_EXTRACTOR_ORIGINAL,
    SIM_ROM_EXTRACTOR_PATCHED,
    prepare_native_runtime,
)

UPSTREAM_SIM_AUDIO = r'''#include <stdio.h>
#include <SDL2/SDL.h>
void SIM_Audio_Init(int aAudioFrequency) {
    SDL_AudioSpec s_requestedAudioSpec;
    s_requestedAudioSpec.callback = SIM_Audio_Callback;
    if(SDL_OpenAudio(&s_requestedAudioSpec, NULL) < 0) {
        printf("SDL Error %s\n", SDL_GetError());
    }
    SDL_PauseAudio(0);
}'''

UPSTREAM_NVRAM_INSTRUCTION = r'''#include <stdio.h>
typedef unsigned int u32;
typedef int s32;
typedef unsigned char u8;
#ifndef SDK_BUILD_ARM
static FILE * s_nvramFilePtr = NULL;
#define NVRAM_FILE_PATH "firmware.bin"
#endif

void NVRAM_ReadDataBytes(u32 address, u32 size, u8 *buf)
{
    s32 i;
    if (size < 1) return;
#ifdef SDK_BUILD_ARM
    // Hardware NVRAM path omitted from this desktop fixture.
#else
    if(s_nvramFilePtr == NULL) {
        s_nvramFilePtr = fopen(NVRAM_FILE_PATH, "rb+");
    }

    fseek(s_nvramFilePtr, address, SEEK_SET);
    fread(buf, 1, size, s_nvramFilePtr);
    fclose(s_nvramFilePtr);
    s_nvramFilePtr = NULL;
#endif
}'''

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

UPSTREAM_BACKUP_HEADER = r'''#ifndef NITRO_CARD_BACKUP_H_
#define NITRO_CARD_BACKUP_H_
#include <nitro/types.h>
#ifdef SDK_PORT
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#endif
#ifdef __cplusplus
extern "C" {
#endif
void CARDi_RequestWriteSectorCommand(u32 src, u32 dst, u32 len, BOOL verify,
                                     MIDmaCallback callback, void *arg, BOOL is_async);

  SDK_INLINE BOOL CARDi_ReadBackup(u32 src, void *dst, u32 len,
                                 MIDmaCallback callback, void *arg, BOOL is_async)
{
    #ifdef SDK_PORT
    FILE * backupFilePtr;
    backupFilePtr = fopen("save.bin", "rb");
    if(!backupFilePtr) {
      // File does not exist. Create the file
      backupFilePtr = fopen("save.bin", "wb");

      // Zero out the file with the len
      u8 * buf = (u8*)malloc(len + src);
      memset(buf, 0, len + src);
      fwrite(buf, 1, len + src, backupFilePtr);
      fclose(backupFilePtr);
      free(buf);

      // Reopen file
      backupFilePtr = fopen("save.bin", "rb");
    }
    fseek(backupFilePtr, src, SEEK_SET);
    fread(dst, 1, len, backupFilePtr);
    fclose(backupFilePtr);
    if( callback != NULL )
    {
      callback(arg);
    }

    return TRUE;
    #else
    return CARDi_RequestStreamCommand((u32)src, (u32)dst, len,
                                      callback, arg, is_async,
                                      CARD_REQ_READ_BACKUP, 1, CARD_REQUEST_MODE_RECV);
    #endif
}

  SDK_INLINE BOOL CARDi_WriteBackup(u32 dst, const void *src, u32 len,
                                  MIDmaCallback callback, void *arg, BOOL is_async)
{
    #ifdef SDK_PORT
    FILE * backupFilePtr;
    backupFilePtr = fopen("save.bin", "rb+");
    fseek(backupFilePtr, dst, SEEK_SET);
    fwrite(src, 1, len, backupFilePtr);
    fclose(backupFilePtr);
    if( callback != NULL )
    {
      callback(arg);
    }
    return TRUE;
    #else
    return CARDi_RequestStreamCommand((u32)src, (u32)dst, len, callback, arg, is_async,
                                      CARD_REQ_WRITE_BACKUP, CARD_RETRY_COUNT_MAX,
                                      CARD_REQUEST_MODE_SEND);
    #endif
}

  SDK_INLINE BOOL CARDi_WriteAndVerifyBackup(u32 dst, const void *src, u32 len,
                                           MIDmaCallback callback, void *arg, BOOL is_async)
{
    #ifdef SDK_PORT
    FILE * backupFilePtr;
    backupFilePtr = fopen("save.bin", "rb+");
    fseek(backupFilePtr, dst, SEEK_SET);
    fwrite(src, 1, len, backupFilePtr);
    fclose(backupFilePtr);
    if( callback != NULL )
    {
      callback(arg);
    }
    return CARD_RESULT_SUCCESS;
    #else
    return CARDi_RequestStreamCommand((u32)src, (u32)dst, len, callback, arg, is_async,
                                      CARD_REQ_WRITE_BACKUP, CARD_RETRY_COUNT_MAX,
                                      CARD_REQUEST_MODE_SEND_VERIFY);
    #endif
}
#ifdef __cplusplus
}
#endif
#endif'''

UPSTREAM_CARD_BACKUP_SOURCE = (
    "#include <nitro.h>\n"
    "BOOL CARD_IdentifyBackup(CARDBackupType type)\n"
    "{\n"
    "#if SDK_VERSION_MAJOR == 5\n"
    + CARD_IDENTIFY_BACKUP_ORIGINAL
    + "\n#endif\n}\n"
)

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

static bool sFastForward = false;
static u8 isMouseDown = 0;

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
  glViewport(0, 0, windowWidth, windowHeight);
  return NULL;
}

void SIM_Render(void) {
  SDL_Event Event;
    while (SDL_PollEvent(&Event)) {
      if (Event.type == SDL_WINDOWEVENT) {
        switch (Event.window.event) {
        case SDL_WINDOWEVENT_CLOSE:
          exit(0);
          break;
        }
      }
      if (Event.type == SDL_KEYDOWN) {
        int keyRead = Event.key.keysym.sym;
        (void)keyRead;
      }
    }
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

UPSTREAM_SIM_ROM_EXTRACTOR = r'''#include "simulator/sim.h"
#include "simulator/imgui/imgui.hpp"
#include "simulator/sim_RomExtractor.h"
#include "simulator/sim_gui.hpp"
#include "nds-extract.hpp"

#include <SDL2/SDL.h>
#include <string>


void SIM_ShowRomExtractionDialog() {
    bool fileSelected = false;
    SIM::GUI::Enable();
    SIM::GUI::OpenFileDialog([&fileSelected](std::string fileName) {
        SIM_NDSExtract(fileName);
        fileSelected = true;
    });
    while(!fileSelected) {
        SIM_Render(nullptr);
    }


    int foo = 1;
    foo++;
    printf("%d", foo);
}'''

UPSTREAM_NDS_EXTRACTOR = r'''#include <filesystem>
#include <iostream>
#include <string>
namespace fs = std::filesystem;

int SIM_NDSExtract(std::string ndsFilePath) {
	fs::path ndsInputPath(ndsFilePath);
	fs::path fsOutputPath = fs::current_path();
	fs::path ov9Path = fsOutputPath.string() + "/overlay9";
	fs::path ov7Path = fsOutputPath.string() + "/overlay7";
	fs::path dataPath = fsOutputPath.string() + "/";
''' + NDS_EXTRACTOR_INPUT_CHECK_ORIGINAL + r'''
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
        extractor_source = root / "subprojects/libntr/libraries/sim/src/sim_RomExtractor.cpp"
        extractor_source.write_text(UPSTREAM_SIM_ROM_EXTRACTOR, encoding="utf-8")
        nds_extractor_source = root / "subprojects/libntr/libraries/sim/src/fireflower/nds-extract.cpp"
        nds_extractor_source.parent.mkdir(parents=True, exist_ok=True)
        nds_extractor_source.write_text(UPSTREAM_NDS_EXTRACTOR, encoding="utf-8")
        backup_header = root / "subprojects/libntr/include/nitro/card/backup.h"
        backup_header.parent.mkdir(parents=True, exist_ok=True)
        backup_header.write_text(UPSTREAM_BACKUP_HEADER, encoding="utf-8")
        card_source = root / "subprojects/libntr/libraries/card/src/card_backup.c"
        card_source.parent.mkdir(parents=True, exist_ok=True)
        card_source.write_text(UPSTREAM_CARD_BACKUP_SOURCE, encoding="utf-8")
        nvram_source = root / "subprojects/libntr/libraries/sim7/src/spi/nvram/nvram_instruction.c"
        nvram_source.parent.mkdir(parents=True, exist_ok=True)
        nvram_source.write_text(UPSTREAM_NVRAM_INSTRUCTION, encoding="utf-8")
        audio_source = root / "subprojects/libntr/libraries/sim/src/sim_audio.cpp"
        audio_source.write_text(UPSTREAM_SIM_AUDIO, encoding="utf-8")
        return source

    def test_uses_imported_rom_header_and_hardens_desktop_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.make_source(root)
            self.assertTrue(prepare_native_runtime(root))
            content = source.read_text(encoding="utf-8")
            self.assertIn('getenv("PLATINA_IMPORTED_ROM")', content)
            self.assertIn('fopen(importedRomPath, "rb")', content)
            self.assertIn(ROM_PREFLIGHT_ENTRY_PATCHED, content)
            self.assertIn(ROM_PREFLIGHT_INCLUDE_PATCHED, content)
            self.assertIn('getenv("PLATINA_IMPORTED_ROM_SHA256")', content)
            self.assertIn("platina-rom-extraction.manifest", content)
            self.assertIn("Reusing local game data after per-file CRC32 verification.", content)
            self.assertLess(
                content.index("SIM_NDSExtract(std::string(managedRomPath))"),
                content.index("SIM_RenderInit(NULL)"),
            )
            self.assertNotIn("SDL_AndroidGetInternalStoragePath", content)
            self.assertNotIn("SDK_BUILD_ANDROID", content)
            self.assertIn("#define SDL_MAIN_HANDLED", content)
            self.assertIn("importedRomPath[0]", content)
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
            self.assertNotIn("sLauncherManagedRomExtractionAttempted", fs_content)
            managed_fallback = FS_OPEN_FALLBACK_PATCHED.split("#if FS_FILE_OPEN_DEBUG", 1)[0]
            self.assertNotIn("SIM_ShowRomExtractionDialog();", managed_fallback)
            self.assertIn("SIM_ShowRomExtractionDialog();", FS_OPEN_FALLBACK_PATCHED)
            self.assertNotIn("return FS_OpenFile(p_file, path);", managed_fallback)
            manual_fallback = FS_OPEN_FALLBACK_PATCHED.split("#if FS_FILE_OPEN_DEBUG", 1)[1]
            self.assertIn("SIM_ShowRomExtractionDialog();", manual_fallback)
            self.assertIn("return FS_OpenFile(p_file, path);", manual_fallback)
            self.assertIn("No extraction will be attempted while the game window is open.", FS_OPEN_FALLBACK_PATCHED)
            self.assertIn("return FALSE;", FS_OPEN_FALLBACK_PATCHED)
            self.assertNotIn("SDK_BUILD_ANDROID", fs_content)
            extractor_content = (root / "subprojects/libntr/libraries/sim/src/sim_RomExtractor.cpp").read_text(encoding="utf-8")
            self.assertIn(SIM_ROM_EXTRACTOR_PATCHED, extractor_content)
            self.assertIn('std::getenv("PLATINA_IMPORTED_ROM")', extractor_content)
            managed_extractor_guard = SIM_ROM_EXTRACTOR_PATCHED.split("bool fileSelected", 1)[0]
            self.assertIn("Refusing synchronous extraction from an imported ROM", managed_extractor_guard)
            self.assertNotIn("SIM_NDSExtract(", managed_extractor_guard)
            manual_extractor_flow = SIM_ROM_EXTRACTOR_PATCHED.split("bool fileSelected", 1)[1]
            self.assertIn("SIM_NDSExtract(fileName);", manual_extractor_flow)
            self.assertIn("SIM_Render(nullptr);", manual_extractor_flow)
            self.assertNotIn(SIM_ROM_EXTRACTOR_ORIGINAL, extractor_content)
            backup_content = (root / "subprojects/libntr/include/nitro/card/backup.h").read_text(encoding="utf-8")
            self.assertIn(BACKUP_SAVE_PATH_INCLUDE_PATCHED, backup_content)
            self.assertIn(BACKUP_FILE_IO_HELPERS_PATCHED, backup_content)
            self.assertIn("static inline BOOL CARDi_VerifyBackupFileRange(", backup_content)
            self.assertIn("CARDi_VerifyBackupFileRange(dst, src, len)", backup_content)
            self.assertEqual(1, backup_content.count(BACKUP_WRITE_BODY_PATCHED))
            self.assertEqual(1, backup_content.count(BACKUP_WRITE_VERIFY_BODY_PATCHED))
            self.assertIn("#ifdef SDK_PORT\nstatic inline BOOL CARDi_EnsureBackupFileSize", backup_content)
            self.assertIn("#endif /* SDK_PORT */\n\n  SDK_INLINE BOOL CARDi_ReadBackup(", backup_content)
            self.assertIn(BACKUP_READ_BODY_PATCHED, backup_content)
            self.assertIn(BACKUP_WRITE_BODY_PATCHED, backup_content)
            self.assertIn(BACKUP_WRITE_VERIFY_BODY_PATCHED, backup_content)
            self.assertEqual(1, backup_content.count('fopen(CARDI_BACKUP_SAVE_FILE, "rb+")'))
            self.assertEqual(1, backup_content.count('fopen(CARDI_BACKUP_SAVE_FILE, "wb+")'))
            self.assertNotIn('fopen("save.bin",', backup_content)
            self.assertIn('CARDI_BACKUP_SAVE_FILE "save.bin"', backup_content)
            self.assertNotIn("return CARD_RESULT_SUCCESS;", backup_content)
            card_content = (root / "subprojects/libntr/libraries/card/src/card_backup.c").read_text(encoding="utf-8")
            self.assertIn(CARD_IDENTIFY_BACKUP_PATCHED, card_content)
            self.assertNotIn(CARD_IDENTIFY_BACKUP_ORIGINAL, card_content)
            self.assertIn("CARDi_IdentifyBackupCore2(type);", CARD_IDENTIFY_BACKUP_PATCHED)
            self.assertIn("CARDi_EndTask(&cardi_common);", CARD_IDENTIFY_BACKUP_PATCHED)
            self.assertIn("#else\n  return CARDi_ExecuteOldTypeTask", CARD_IDENTIFY_BACKUP_PATCHED)
            self.assertIn(SDL_INIT_PATCHED, content)
            self.assertIn(SDL_WINDOW_CONTEXT_PATCHED, content)
            self.assertIn('SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);\n  // Apply VSync only after SDL_GL_CreateContext succeeds.', content)
            self.assertIn('if (SDL_GL_SetSwapInterval(s_SIM_config.vsyncInterval) != 0)', content)
            self.assertIn(GL_LOADER_PATCHED, content)
            self.assertIn(MAIN_RENDER_HANDOFF_PATCHED, content)
            self.assertIn(SDL_VIEWPORT_PATCHED, content)
            nvram_content = (root / "subprojects/libntr/libraries/sim7/src/spi/nvram/nvram_instruction.c").read_text(encoding="utf-8")
            self.assertIn(NVRAM_FILE_READ_PATCHED, nvram_content)
            self.assertIn('fopen(NVRAM_FILE_PATH, "rb")', nvram_content)
            audio_content = (root / "subprojects/libntr/libraries/sim/src/sim_audio.cpp").read_text(encoding="utf-8")
            self.assertIn(SIM_AUDIO_OPEN_PATCHED, audio_content)
            self.assertIn('SDL_AudioInit("dummy")', audio_content)
            self.assertIn("buf[i] = 0xFF;", nvram_content)
            self.assertNotIn('fseek(s_nvramFilePtr, address, SEEK_SET);', nvram_content)
            self.assertFalse(prepare_native_runtime(root))
            self.assertIn(INPUT_RELEASE_HELPER_PATCHED, content)
            self.assertIn(MOUSE_DOWN_DECLARATION_PATCHED, content)
            self.assertEqual(sum(line.strip() == MOUSE_DOWN_DECLARATION_ORIGINAL for line in content.splitlines()), 0)
            self.assertLess(
                content.index("static u8 isMouseDown = 0;"),
                content.index("static void ReleaseDesktopInputState()"),
            )
            self.assertIn(WINDOW_EVENT_PATCHED, content)
            self.assertIn(KEYDOWN_PATCHED, content)
            self.assertIn("SDL_WINDOW_ALLOW_HIGHDPI", content)
            self.assertIn("SDL_JOYDEVICEREMOVED", content)
            self.assertIn("SDL_WINDOWEVENT_FOCUS_LOST", content)
            self.assertFalse(prepare_native_runtime(root))

    def test_nds_extractor_checks_file_type_and_size_errors_before_reading_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root)

            self.assertTrue(prepare_native_runtime(root))
            extractor = (
                root / "subprojects/libntr/libraries/sim/src/fireflower/nds-extract.cpp"
            ).read_text(encoding="utf-8")

            self.assertIn(NDS_EXTRACTOR_INPUT_CHECK_PATCHED, extractor)
            self.assertNotIn(NDS_EXTRACTOR_INPUT_CHECK_ORIGINAL, extractor)
            self.assertLess(extractor.index("fs::status(ndsInputPath"), extractor.index("fs::file_size(ndsInputPath"))
            self.assertIn("fs::file_size(ndsInputPath, inputError)", extractor)
            self.assertIn("if (inputError)", extractor)
            self.assertIn("const unsigned ndsFileSize = static_cast<unsigned>(ndsFileSizeValue);", extractor)

            # Re-running the patcher must not reapply the extractor patch.
            self.assertFalse(prepare_native_runtime(root))

    def test_extraction_cache_requires_the_complete_path_manifest_and_per_file_integrity(self):
        self.assertIn("PLATINA_DATA_PATHS_V1", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("platinum-data-paths.txt", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("verifyExtractionCache", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("--platina-prepared", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("bool verifyFullCrc", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("if (verifyFullCrc)", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("file_size(relativePath, sizeError)", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("Prepared game data changed after launcher verification", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("inspectFileCrc32", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("platina-rom-extraction.manifest", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("required local data is missing/corrupted", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("collectOverlayPaths", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("bool verifyContents", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("if (verifyContents)", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("!platinaPreparedByLauncher", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("collectOverlayPaths(expectedDataPaths, true, true", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("Overlay validation failed: %s", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn('return fail("required " + prefix + " overlay directory is missing:', ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("unexpected entry in ", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("could not fully read or verify overlay file", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("Extraction did not produce a valid ARM9 overlay set: %s", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn('const std::string stem = prefix + "_";', ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn('collectOne("overlay9", "overlay9", requireAll)', ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn('collectOne("overlay7", "overlay7", false)', ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("hasOverlay9", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("if (!hasOverlay9) return false;", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertNotIn("if (!hasOverlay9 || !hasOverlay7)", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("the group may be empty", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn('"arm9.bin"', ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn('"arm7.bin"', ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertNotIn('"firmware.bin"', ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertNotIn('std::filesystem::path("msgdata/msg.narc")', ROM_PREFLIGHT_ENTRY_PATCHED)

    def test_valid_rom_extraction_does_not_require_separate_arm7_overlay_files(self):
        self.assertIn(
            'if (!collectOne("overlay9", "overlay9", requireAll) ||',
            ROM_PREFLIGHT_ENTRY_PATCHED,
        )
        self.assertIn('!collectOne("overlay7", "overlay7", false)', ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("ARM7's static", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("ARM7 overlay-table data can legitimately be empty", ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertNotIn('relativeName == "arm7ovt.bin"', ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn('relativeName == "arm9ovt.bin"', ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn('"arm7ovt.bin"', ROM_PREFLIGHT_ENTRY_PATCHED)
        self.assertIn("if (!hasOverlay9) return false;", ROM_PREFLIGHT_ENTRY_PATCHED)

    def test_desktop_first_launch_can_start_without_a_rom_header(self):
        self.assertIn('romFile = fopen("header.bin", "rb");', PATCHED_HEADER_LOAD)
        self.assertIn("Unable to open imported desktop ROM", PATCHED_HEADER_LOAD)
        self.assertIn("if (romFile != NULL) {", PATCHED_HEADER_LOAD)

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

    def test_unknown_sim_rom_extractor_fails_before_any_source_file_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.make_source(root)
            original_main = source.read_text(encoding="utf-8")
            config = source.parent / "config" / "sim_config.c"
            original_config = config.read_text(encoding="utf-8")
            fs_source = root / "subprojects/libntr/libraries/fs/src/fs_file.c"
            original_fs = fs_source.read_text(encoding="utf-8")
            extractor_source = root / "subprojects/libntr/libraries/sim/src/sim_RomExtractor.cpp"
            extractor_source.write_text("unknown ROM extractor implementation\\n", encoding="utf-8")

            with self.assertRaises(RuntimePreparationError):
                prepare_native_runtime(root)

            self.assertEqual(source.read_text(encoding="utf-8"), original_main)
            self.assertEqual(config.read_text(encoding="utf-8"), original_config)
            self.assertEqual(fs_source.read_text(encoding="utf-8"), original_fs)
            self.assertEqual(
                extractor_source.read_text(encoding="utf-8"),
                "unknown ROM extractor implementation\\n",
            )

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

    def test_upgrades_legacy_managed_rom_fallback_without_extracting_inside_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root)
            fs_source = root / "subprojects/libntr/libraries/fs/src/fs_file.c"
            legacy_include = (
                "#include <string.h>\n#include <stdlib.h>\n#include <stdio.h>\n#include <SDL2/SDL.h>\n"
                "static BOOL sLauncherManagedRomExtractionAttempted = FALSE;"
            )
            source = UPSTREAM_FS_FILE.replace(
                FS_OPEN_FALLBACK_ORIGINAL, FS_OPEN_FALLBACK_PATCHED_LEGACY, 1
            ).replace(
                "#include <string.h>\n#include <SDL2/SDL.h>", legacy_include, 1
            )
            fs_source.write_text(source, encoding="utf-8")

            self.assertTrue(prepare_native_runtime(root))
            upgraded = fs_source.read_text(encoding="utf-8")
            self.assertIn(FS_OPEN_FALLBACK_PATCHED, upgraded)
            self.assertNotIn(FS_OPEN_FALLBACK_PATCHED_LEGACY, upgraded)
            self.assertNotIn("sLauncherManagedRomExtractionAttempted", upgraded)
            managed_fallback = FS_OPEN_FALLBACK_PATCHED.split("#if FS_FILE_OPEN_DEBUG", 1)[0]
            self.assertNotIn("SIM_ShowRomExtractionDialog();", managed_fallback)
            self.assertIn("SIM_ShowRomExtractionDialog();", FS_OPEN_FALLBACK_PATCHED)
            self.assertFalse(prepare_native_runtime(root))
            self.assertEqual(fs_source.read_text(encoding="utf-8"), upgraded)

    def test_backup_io_hardening_upgrades_the_earlier_save_path_only_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root)
            backup_header = root / "subprojects/libntr/include/nitro/card/backup.h"
            content = backup_header.read_text(encoding="utf-8")
            original_include = """#ifdef SDK_PORT
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#endif"""
            legacy_include = """#ifdef SDK_PORT
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CARDI_BACKUP_SAVE_FILE "save.bin"
#endif"""
            self.assertEqual(content.count(original_include), 1)
            self.assertEqual(content.count('fopen("save.bin",'), 5)
            content = content.replace(original_include, legacy_include, 1)
            content = content.replace(
                'fopen("save.bin",', "fopen(CARDI_BACKUP_SAVE_FILE,"
            )
            backup_header.write_text(content, encoding="utf-8")

            self.assertTrue(prepare_native_runtime(root))
            hardened = backup_header.read_text(encoding="utf-8")
            self.assertIn(BACKUP_FILE_IO_HELPERS_PATCHED, hardened)
            self.assertIn(BACKUP_READ_BODY_PATCHED, hardened)
            self.assertIn(BACKUP_WRITE_BODY_PATCHED, hardened)
            self.assertIn(BACKUP_WRITE_VERIFY_BODY_PATCHED, hardened)
            self.assertNotIn('fopen("save.bin",', hardened)
            self.assertNotIn("return CARD_RESULT_SUCCESS;", hardened)
            self.assertFalse(prepare_native_runtime(root))
            self.assertEqual(backup_header.read_text(encoding="utf-8"), hardened)

    def test_card_identification_uses_local_backup_geometry_on_desktop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root)
            card_source = root / "subprojects/libntr/libraries/card/src/card_backup.c"
            original = card_source.read_text(encoding="utf-8")

            self.assertTrue(prepare_native_runtime(root))
            patched = card_source.read_text(encoding="utf-8")
            self.assertIn(CARD_IDENTIFY_BACKUP_PATCHED, patched)
            self.assertNotIn(CARD_IDENTIFY_BACKUP_ORIGINAL, patched)
            self.assertTrue(CARD_IDENTIFY_BACKUP_PATCHED.startswith(
                "  CARDi_BeginBackupCommand(CARD_ACCESS_LEVEL_NONE, NULL, NULL);"
            ))
            self.assertIn("CARDi_IdentifyBackupCore2(type);", CARD_IDENTIFY_BACKUP_PATCHED)
            self.assertIn("CARDi_EndTask(&cardi_common);", CARD_IDENTIFY_BACKUP_PATCHED)
            self.assertIn("#else\n  return CARDi_ExecuteOldTypeTask", CARD_IDENTIFY_BACKUP_PATCHED)
            self.assertFalse(prepare_native_runtime(root))
            self.assertEqual(card_source.read_text(encoding="utf-8"), patched)
            self.assertNotEqual(original, patched)

    def test_unknown_card_backup_implementation_fails_before_any_source_file_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.make_source(root)
            original_main = source.read_text(encoding="utf-8")
            config = source.parent / "config" / "sim_config.c"
            original_config = config.read_text(encoding="utf-8")
            card_source = root / "subprojects/libntr/libraries/card/src/card_backup.c"
            card_source.write_text("unknown card backup implementation\n", encoding="utf-8")

            with self.assertRaises(RuntimePreparationError):
                prepare_native_runtime(root)

            self.assertEqual(source.read_text(encoding="utf-8"), original_main)
            self.assertEqual(config.read_text(encoding="utf-8"), original_config)
            self.assertEqual(
                card_source.read_text(encoding="utf-8"),
                "unknown card backup implementation\n",
            )

    def test_unknown_backup_header_fails_before_any_source_file_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.make_source(root)
            original_main = source.read_text(encoding="utf-8")
            config = source.parent / "config" / "sim_config.c"
            original_config = config.read_text(encoding="utf-8")
            fs_source = root / "subprojects/libntr/libraries/fs/src/fs_file.c"
            original_fs = fs_source.read_text(encoding="utf-8")
            backup_header = root / "subprojects/libntr/include/nitro/card/backup.h"
            backup_header.write_text("unknown backup implementation\n", encoding="utf-8")

            with self.assertRaises(RuntimePreparationError):
                prepare_native_runtime(root)

            self.assertEqual(source.read_text(encoding="utf-8"), original_main)
            self.assertEqual(config.read_text(encoding="utf-8"), original_config)
            self.assertEqual(fs_source.read_text(encoding="utf-8"), original_fs)
            self.assertEqual(
                backup_header.read_text(encoding="utf-8"),
                "unknown backup implementation\n",
            )

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

