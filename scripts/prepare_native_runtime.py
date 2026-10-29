#!/usr/bin/env python3
"""Patch the pinned libntr simulator to read the ROM imported through the launcher."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ORIGINAL_HEADER_LOAD = r'''  // Read the first 0x160 bytes of the rom and put it in the HW_ROM_HEADER_BUF
  FILE *romFile;
  romFile = fopen("header.bin", "r");

  if (romFile != NULL) {
    // Read the fields of the struct
    fread((void *)HW_ROM_HEADER_BUF, 1, 0x160, romFile);
    fclose(romFile);
  }'''

# Previous revision. Upgrade it in place so repeated runtime preparation is safe.
LEGACY_PATCHED_HEADER_LOAD = r'''  // Prefer the ROM selected in the launcher for the cartridge header.
  // Use the packaged header.bin as a safe fallback for direct/manual launches.
  const char *importedRomPath = getenv("PLATINA_IMPORTED_ROM");
  FILE *romFile = NULL;
  if (importedRomPath != NULL && importedRomPath[0] != '\0') {
    romFile = fopen(importedRomPath, "rb");
  }
  if (romFile == NULL) {
    romFile = fopen("header.bin", "rb");
  }
  if (romFile != NULL) {
    fread((void *)HW_ROM_HEADER_BUF, 1, 0x160, romFile);
    fclose(romFile);
  }'''

ANDROID_SYSTEM_INCLUDES = r'''#if defined(__ANDROID__)
#include <SDL2/SDL_system.h>
#include <unistd.h>
#endif'''

# SDLActivity resolves the exported SDL_main symbol on Android. Keep SDL_MAIN_HANDLED
# only on desktop, where the upstream simulator intentionally owns a normal main().
ANDROID_SDL_ENTRYPOINT_BLOCK = r'''#ifndef SDK_BUILD_ANDROID
#define SDL_MAIN_HANDLED
#endif'''

ANDROID_MAIN_INIT = r'''#ifdef __ANDROID__
  // The Android plugin extracts the complete runtime tree to this private path.
  // Fail early with a clear diagnostic if the native runtime cannot be entered.
  const char *androidRuntimeStoragePath = SDL_AndroidGetInternalStoragePath();
  if (androidRuntimeStoragePath == NULL || *androidRuntimeStoragePath == '\0') {
    fprintf(stderr, "Android internal storage path is unavailable\n");
    return 1;
  }
  std::string androidRuntimeDirectory =
      std::string(androidRuntimeStoragePath) + "/pokeplatinum";
  if (chdir(androidRuntimeDirectory.c_str()) != 0) {
    perror("Changing to the game runtime directory");
    return 1;
  }
#endif'''

# Older versions logged chdir failures but continued, which produced confusing
# later resource errors. Keep this exact pattern so existing prepared trees can
# be upgraded in place rather than receiving a second Android chdir block.
LEGACY_ANDROID_MAIN_INIT = r'''#ifdef __ANDROID__
  // The Android plugin extracts the complete runtime tree to this private path.
  // Set it as the working directory before relative game/config/data files load.
  const char *androidRuntimeStoragePath = SDL_AndroidGetInternalStoragePath();
  if (androidRuntimeStoragePath != NULL) {
    std::string androidRuntimeDirectory =
        std::string(androidRuntimeStoragePath) + "/pokeplatinum";
    if (chdir(androidRuntimeDirectory.c_str()) != 0) {
      fprintf(stderr, "Unable to enter Android runtime directory: %s\\n",
              androidRuntimeDirectory.c_str());
    }
  }
#endif'''

PREVIOUS_PATCHED_HEADER_LOAD = r'''  // Prefer the imported ROM header on all platforms.
  // Windows/Linux receive the file path from the launcher; Android uses SDL's
  // private app-storage path, matching Capacitor Filesystem Directory.Data.
  FILE *romFile = NULL;
#if defined(__ANDROID__)
  const char *androidInternalStoragePath = SDL_AndroidGetInternalStoragePath();
  std::string importedRomPath;
  if (androidInternalStoragePath != NULL && *androidInternalStoragePath != '\0') {
    importedRomPath = std::string(androidInternalStoragePath) + "/roms/current.nds";
    romFile = fopen(importedRomPath.c_str(), "rb");
  }
  if (romFile == NULL) {
    fprintf(stderr, "Unable to open imported Android ROM: %s\n",
            importedRomPath.empty() ? "(internal storage unavailable)" : importedRomPath.c_str());
    return 1;
  }
#else
  const char *importedRomPath = getenv("PLATINA_IMPORTED_ROM");
  if (importedRomPath != NULL && importedRomPath[0] != '\0') {
    romFile = fopen(importedRomPath, "rb");
  }
  if (romFile == NULL) {
    romFile = fopen("header.bin", "rb");
  }
#endif
  if (romFile != NULL) {
    fread((void *)HW_ROM_HEADER_BUF, 1, 0x160, romFile);
    fclose(romFile);
  }'''


PATCHED_HEADER_LOAD = r'''  // Prefer the imported ROM header on all platforms.
  // Windows/Linux receive the file path from the launcher; Android uses SDL's
  // private app-storage path, matching Capacitor Filesystem Directory.Data.
  FILE *romFile = NULL;
#if defined(__ANDROID__)
  const char *androidInternalStoragePath = SDL_AndroidGetInternalStoragePath();
  std::string importedRomPath;
  if (androidInternalStoragePath != NULL && *androidInternalStoragePath != '\0') {
    importedRomPath = std::string(androidInternalStoragePath) + "/roms/current.nds";
    romFile = fopen(importedRomPath.c_str(), "rb");
  }
  if (romFile == NULL) {
    fprintf(stderr, "Unable to open imported Android ROM: %s\n",
            importedRomPath.empty() ? "(internal storage unavailable)" : importedRomPath.c_str());
    return 1;
  }
#else
  const char *importedRomPath = getenv("PLATINA_IMPORTED_ROM");
  if (importedRomPath != NULL && importedRomPath[0] != '\0') {
    romFile = fopen(importedRomPath, "rb");
  }
  if (romFile == NULL) {
    romFile = fopen("header.bin", "rb");
  }
#endif
  if (romFile == NULL) {
    fprintf(stderr, "Unable to open a ROM header source or packaged header.bin\n");
    return 1;
  }
  const size_t headerBytesRead = fread((void *)HW_ROM_HEADER_BUF, 1, 0x160, romFile);
  fclose(romFile);
  if (headerBytesRead != 0x160) {
    fprintf(stderr, "Incomplete ROM header: expected 352 bytes, read %zu\n", headerBytesRead);
    return 1;
  }'''




CONFIG_ALARM_SECOND_ORIGINAL = r'''    if(MATCH("OSNVRAM", "Alarm_Second")) {
        config->osNvramConfig.ncd.alarm.minute = atoi(value);
    }'''
CONFIG_ALARM_SECOND_PATCHED = r'''    if(MATCH("OSNVRAM", "Alarm_Second")) {
        config->osNvramConfig.ncd.alarm.second = atoi(value);
    }'''
CONFIG_SAVE_OPEN_ORIGINAL = '    FILE * configFile = fopen(SIM_CONFIG_FILE_PATH, "w");'
SDL_INIT_ORIGINAL = r'''  SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_TIMER |
           SDL_INIT_JOYSTICK);
  SIM_Audio_Init(44100);'''
SDL_INIT_PATCHED = r'''  if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_TIMER |
               SDL_INIT_JOYSTICK) != 0) {
    fprintf(stderr, "SDL initialization failed: %s\n", SDL_GetError());
    return NULL;
  }
  SIM_Audio_Init(44100);'''

SDL_SWAP_INTERVAL_SETUP_ORIGINAL = r'''  SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
  SDL_GL_SetSwapInterval(s_SIM_config.vsyncInterval);'''
SDL_SWAP_INTERVAL_SETUP_PATCHED = r'''  SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
  // Apply VSync only after SDL_GL_CreateContext succeeds.'''

SDL_WINDOW_CONTEXT_ORIGINAL = r'''  window = SDL_CreateWindow(
      windowTitle.c_str(), 100, 100, windowWidth, windowHeight,
      SDL_WINDOW_SHOWN | SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE);
  context = SDL_GL_CreateContext(window);'''
SDL_WINDOW_CONTEXT_PATCHED = r'''  window = SDL_CreateWindow(
      windowTitle.c_str(), 100, 100, windowWidth, windowHeight,
      SDL_WINDOW_SHOWN | SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE);
  if (window == NULL) {
    fprintf(stderr, "SDL window creation failed: %s\n", SDL_GetError());
    return NULL;
  }
  context = SDL_GL_CreateContext(window);
  if (context == NULL) {
    fprintf(stderr, "SDL GL context creation failed: %s\n", SDL_GetError());
    SDL_DestroyWindow(window);
    window = NULL;
    return NULL;
  }
  if (SDL_GL_SetSwapInterval(s_SIM_config.vsyncInterval) != 0) {
    fprintf(stderr, "SDL swap interval unavailable: %s\n", SDL_GetError());
  }'''

GL_LOADER_ORIGINAL = "  gladLoadGLLoader(SDL_GL_GetProcAddress);"
GL_LOADER_PATCHED = r'''#ifndef SDK_BUILD_ANDROID
  if (!gladLoadGLLoader(SDL_GL_GetProcAddress)) {
    fprintf(stderr, "OpenGL function loader initialization failed.\n");
    SDL_GL_DeleteContext(context);
    SDL_DestroyWindow(window);
    context = NULL;
    window = NULL;
    return NULL;
  }
#endif'''

MAIN_RENDER_HANDOFF_ORIGINAL = "  SIM_RenderInit(NULL);\n  G3SIM_DrawInit();"
MAIN_RENDER_HANDOFF_PATCHED = r'''  SIM_RenderInit(NULL);
  if (window == NULL || context == NULL) {
    fprintf(stderr, "Native renderer initialization failed; aborting startup.\n");
    return 1;
  }
  G3SIM_DrawInit();'''


FS_OPEN_FALLBACK_ORIGINAL = r'''        #if FS_FILE_OPEN_DEBUG
        char messageBuf[200] = {0};
        snprintf(messageBuf, 199, "Failed to open file '%s'.", path);
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_INFORMATION, "ROM Extraction Required", messageBuf, NULL);
        #else
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_INFORMATION, "ROM Extraction Required", "ROM filesystem is missing. Select 'OK' and choose a NDS ROM file in the next step.", NULL);
        #endif

        SIM_ShowRomExtractionDialog();

        // try again, because the ROM should be extracted at this point
        // yes, this is recursive, so if the user is dumb enough to keep extracting the wrong ROM and does this enough times, it will crash
        return FS_OpenFile(p_file, path);'''
FS_OPEN_FALLBACK_PATCHED = r'''        #ifdef SDK_BUILD_ANDROID
        OS_Warning("[file-system] Required runtime resource is missing: %s.\n", path);
        return FALSE;
        #else
        const char *managedRomPath = getenv("PLATINA_IMPORTED_ROM");
        if (managedRomPath != NULL && managedRomPath[0] != '\0') {
            OS_Warning("[file-system] Required runtime resource is missing: %s.\n", path);
            return FALSE;
        }
        #if FS_FILE_OPEN_DEBUG
        char messageBuf[200] = {0};
        snprintf(messageBuf, 199, "Failed to open file '%s'.", path);
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_INFORMATION, "ROM Extraction Required", messageBuf, NULL);
        #else
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_INFORMATION, "ROM Extraction Required", "ROM filesystem is missing. Select 'OK' and choose a NDS ROM file in the next step.", NULL);
        #endif

        SIM_ShowRomExtractionDialog();

        // Manual upstream launches may still use the legacy extraction flow.
        return FS_OpenFile(p_file, path);
        #endif'''
CONFIG_SAVE_OPEN_PATCHED = (
    CONFIG_SAVE_OPEN_ORIGINAL
    + "\n    if (configFile == NULL) {\n        return;\n    }"
)


class RuntimePreparationError(RuntimeError):
    pass


def _ensure_android_sdl_entrypoint(source: str) -> tuple[str, bool]:
    """Let SDL rename the native entrypoint to SDL_main only for Android."""
    original = "#define SDL_MAIN_HANDLED"
    if source.count(ANDROID_SDL_ENTRYPOINT_BLOCK) == 1:
        return source, False
    if ANDROID_SDL_ENTRYPOINT_BLOCK in source:
        raise RuntimePreparationError("Duplicate or partial Android SDL entrypoint patch detected.")
    if source.count(original) != 1:
        raise RuntimePreparationError("Expected exactly one SDL_MAIN_HANDLED definition for entrypoint patch.")
    return source.replace(original, ANDROID_SDL_ENTRYPOINT_BLOCK, 1), True


def _ensure_android_system_includes(source: str) -> tuple[str, bool]:
    if ANDROID_SYSTEM_INCLUDES in source:
        return source, False
    if "SDL2/SDL_system.h" in source or "#include <unistd.h>" in source:
        raise RuntimePreparationError("Partial Android SDL/system include patch detected.")
    marker = "#include <SDL2/SDL.h>"
    if source.count(marker) != 1:
        raise RuntimePreparationError("Expected exactly one SDL.h include to add Android path support.")
    return source.replace(marker, marker + "\n" + ANDROID_SYSTEM_INCLUDES, 1), True


def _ensure_android_working_directory(source: str) -> tuple[str, bool]:
    main_entry = "int main(int argc, char *argv[]) {\n"
    patched_entry = main_entry + ANDROID_MAIN_INIT
    legacy_entry = main_entry + LEGACY_ANDROID_MAIN_INIT

    if source.count(patched_entry) == 1:
        return source, False
    if source.count(patched_entry) > 1:
        raise RuntimePreparationError("Duplicate Android runtime working-directory setup detected.")

    # Upgrade a previously prepared tree in place. Do not append a second
    # chdir block after changing the failure behavior.
    if source.count(legacy_entry) == 1:
        return source.replace(legacy_entry, patched_entry, 1), True
    if source.count(legacy_entry) > 1 or source.count(main_entry) != 1:
        raise RuntimePreparationError("Expected exactly one simulator main entrypoint for Android working-directory setup.")
    return source.replace(main_entry, patched_entry + "\n", 1), True


def _prepare_renderer_startup(source: str) -> tuple[str, bool]:
    """Fail cleanly when SDL or the desktop OpenGL loader cannot initialize."""
    current = source
    blocks = (
        (
            SDL_SWAP_INTERVAL_SETUP_ORIGINAL,
            SDL_SWAP_INTERVAL_SETUP_PATCHED,
            "defer swap interval until a context exists",
        ),
        (SDL_INIT_ORIGINAL, SDL_INIT_PATCHED, "SDL_Init result check"),
        (SDL_WINDOW_CONTEXT_ORIGINAL, SDL_WINDOW_CONTEXT_PATCHED, "SDL window/context checks"),
        (GL_LOADER_ORIGINAL, GL_LOADER_PATCHED, "desktop OpenGL loader check"),
        (MAIN_RENDER_HANDOFF_ORIGINAL, MAIN_RENDER_HANDOFF_PATCHED, "renderer startup handoff check"),
    )
    for original, patched, label in blocks:
        if patched in current:
            if current.count(patched) != 1:
                raise RuntimePreparationError(f"Duplicate {label} patch detected.")
            continue
        if current.count(original) != 1:
            raise RuntimePreparationError(
                f"Expected exactly one known upstream marker for {label}; refusing uncertain patch."
            )
        current = current.replace(original, patched, 1)
    return current, current != source


def _prepare_fs_missing_resource_fallback(source_root: str | Path) -> tuple[Path, str, bool]:
    """Avoid a recursive ROM picker when a launcher-managed runtime is incomplete."""
    fs_path = (
        Path(source_root).expanduser().resolve()
        / "subprojects" / "libntr" / "libraries" / "fs" / "src" / "fs_file.c"
    )
    if not fs_path.is_file():
        raise RuntimePreparationError(f"Simulator filesystem source missing: {fs_path}")

    original = fs_path.read_text(encoding="utf-8")
    current = original

    if FS_OPEN_FALLBACK_PATCHED in current:
        if current.count(FS_OPEN_FALLBACK_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate launcher-managed missing-resource guard in fs_file.c.")
        if FS_OPEN_FALLBACK_ORIGINAL in current:
            raise RuntimePreparationError("Both original and patched ROM-extraction fallback exist in fs_file.c.")
        patched = False
    else:
        if current.count(FS_OPEN_FALLBACK_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected exactly one known ROM-extraction fallback in fs_file.c; refusing uncertain patch."
            )
        current = current.replace(FS_OPEN_FALLBACK_ORIGINAL, FS_OPEN_FALLBACK_PATCHED, 1)
        patched = True

    original_include = "#include <string.h>\n#include <SDL2/SDL.h>"
    patched_include = "#include <string.h>\n#include <stdlib.h>\n#include <SDL2/SDL.h>"
    if patched_include in current:
        if current.count(patched_include) != 1:
            raise RuntimePreparationError("Duplicate stdlib include in fs_file.c.")
    else:
        if current.count(original_include) != 1:
            raise RuntimePreparationError("Expected exactly one SDK_PORT include block in fs_file.c.")
        current = current.replace(original_include, patched_include, 1)
        patched = True

    return fs_path, current, current != original


def _prepare_sim_config(config_path: Path) -> tuple[str, bool]:
    """Fix known simulator config bugs; reject unknown source rather than patching blindly."""
    if not config_path.is_file():
        raise RuntimePreparationError(f"Simulator config source missing: {config_path}")

    original = config_path.read_text(encoding="utf-8")
    current = original

    if CONFIG_ALARM_SECOND_PATCHED in current:
        if current.count(CONFIG_ALARM_SECOND_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate Alarm_Second patch in sim_config.c.")
        if CONFIG_ALARM_SECOND_ORIGINAL in current:
            raise RuntimePreparationError("Both old and patched Alarm_Second handlers exist.")
    else:
        if current.count(CONFIG_ALARM_SECOND_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected exactly one upstream Alarm_Second handler in sim_config.c."
            )
        current = current.replace(CONFIG_ALARM_SECOND_ORIGINAL, CONFIG_ALARM_SECOND_PATCHED, 1)

    if CONFIG_SAVE_OPEN_PATCHED in current:
        if current.count(CONFIG_SAVE_OPEN_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate configuration fopen guard in sim_config.c.")
    else:
        if current.count(CONFIG_SAVE_OPEN_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected exactly one SIM_Config_SaveConfigFile fopen marker in sim_config.c."
            )
        current = current.replace(CONFIG_SAVE_OPEN_ORIGINAL, CONFIG_SAVE_OPEN_PATCHED, 1)

    return current, current != original


def prepare_native_runtime(source_root: str | Path) -> bool:
    """Connect the imported ROM and use the extracted private runtime directory on Android."""
    path = (Path(source_root).expanduser().resolve() / "subprojects" / "libntr"
            / "libraries" / "sim" / "src" / "sim_main.cpp")
    if not path.is_file():
        raise RuntimePreparationError(f"Simulator source missing: {path}")

    original = path.read_text(encoding="utf-8")
    current = original
    current_load_count = current.count(PATCHED_HEADER_LOAD)
    previous_load_count = current.count(PREVIOUS_PATCHED_HEADER_LOAD)
    legacy_count = current.count(LEGACY_PATCHED_HEADER_LOAD)
    upstream_count = current.count(ORIGINAL_HEADER_LOAD)

    if current_load_count == 1:
        if previous_load_count or legacy_count or upstream_count:
            raise RuntimePreparationError("Multiple competing ROM-header loaders found; refusing an ambiguous patch.")
    elif current_load_count == 0 and previous_load_count == 1 and legacy_count == 0 and upstream_count == 0:
        current = current.replace(PREVIOUS_PATCHED_HEADER_LOAD, PATCHED_HEADER_LOAD, 1)
    elif current_load_count == 0 and previous_load_count == 0 and legacy_count == 1 and upstream_count == 0:
        current = current.replace(LEGACY_PATCHED_HEADER_LOAD, PATCHED_HEADER_LOAD, 1)
    elif current_load_count == 0 and previous_load_count == 0 and legacy_count == 0 and upstream_count == 1:
        current = current.replace(ORIGINAL_HEADER_LOAD, PATCHED_HEADER_LOAD, 1)
    else:
        raise RuntimePreparationError(
            "Expected exactly one recognized upstream or patched ROM-header loader in sim_main.cpp; refusing an uncertain patch."
        )

    current, entrypoint_changed = _ensure_android_sdl_entrypoint(current)
    current, include_changed = _ensure_android_system_includes(current)
    current, main_changed = _ensure_android_working_directory(current)
    current, renderer_changed = _prepare_renderer_startup(current)

    # Validate all three source files before writing any of them.
    config_path = path.parent / "config" / "sim_config.c"
    config_updated, config_changed = _prepare_sim_config(config_path)
    fs_path, fs_updated, fs_changed = _prepare_fs_missing_resource_fallback(source_root)

    changed = current != original or config_changed or fs_changed
    if current != original:
        path.write_text(current, encoding="utf-8")
    if config_changed:
        config_path.write_text(config_updated, encoding="utf-8")
    if fs_changed:
        fs_path.write_text(fs_updated, encoding="utf-8")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", help="Pinned pokeplatinum source root")
    args = parser.parse_args(argv)
    try:
        changed = prepare_native_runtime(args.source_root)
    except (OSError, RuntimePreparationError) as exc:
        print(f"Native ROM-header preparation failed: {exc}", file=sys.stderr)
        return 2
    print("ROM-header handoff patched." if changed else "ROM-header handoff already patched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
