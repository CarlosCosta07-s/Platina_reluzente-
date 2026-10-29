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
    changed = current != original
    if changed:
        path.write_text(current, encoding="utf-8")
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
