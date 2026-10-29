#!/usr/bin/env python3
"""Prepare the pinned native runtime, filesystem fallback, configuration and save path."""
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

PATCHED_HEADER_LOAD = r'''  // Prefer the imported ROM header selected by the desktop launcher.
  // Keep header.bin as a fallback for manual and legacy desktop launches.
  const char *importedRomPath = getenv("PLATINA_IMPORTED_ROM");
  FILE *romFile = NULL;
  if (importedRomPath != NULL && importedRomPath[0] != '\0') {
    romFile = fopen(importedRomPath, "rb");
    if (romFile == NULL) {
      fprintf(stderr, "Unable to open imported desktop ROM: %s\n", importedRomPath);
      return 1;
    }
  } else {
    romFile = fopen("header.bin", "rb");
  }
  if (romFile != NULL) {
    const size_t headerBytesRead = fread((void *)HW_ROM_HEADER_BUF, 1, 0x160, romFile);
    fclose(romFile);
    if (headerBytesRead != 0x160) {
      fprintf(stderr, "Incomplete ROM header: expected 352 bytes, read %zu\n", headerBytesRead);
      return 1;
    }
  }'''

ROM_PREFLIGHT_INCLUDE_ORIGINAL = "#include <SDL2/SDL.h>"
ROM_PREFLIGHT_INCLUDE_PATCHED = r'''#include <SDL2/SDL.h>
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <exception>
#include <iomanip>
#include <sstream>
#include <string>
#include <system_error>
#include <vector>
#include "nds-extract.hpp"'''
ROM_PREFLIGHT_ENTRY_ORIGINAL = "int main(int argc, char *argv[]) {\n#ifdef SDK_BUILD_NX"
ROM_PREFLIGHT_ENTRY_PATCHED = r'''int main(int argc, char *argv[]) {
  // The native runtime package contains a path-only manifest derived from the
  // pinned filesys.csv. No ROM or extracted game contents are packaged.
  const auto isRegularFileWithoutSymlinks = [](const std::filesystem::path &relativePath) {
    if (relativePath.empty() || relativePath.is_absolute() || relativePath.has_root_name()) {
      return false;
    }
    std::filesystem::path currentPath;
    auto component = relativePath.begin();
    for (; component != relativePath.end(); ++component) {
      const std::string part = component->string();
      if (part.empty() || part == "." || part == ".." ||
          part.find('\\') != std::string::npos || part.find(':') != std::string::npos) {
        return false;
      }
      currentPath /= *component;
      std::error_code statusError;
      const auto status = std::filesystem::symlink_status(currentPath, statusError);
      if (statusError || std::filesystem::is_symlink(status)) return false;
      auto next = component;
      ++next;
      if (next != relativePath.end()) {
        if (!std::filesystem::is_directory(status)) return false;
      } else if (!std::filesystem::is_regular_file(status)) {
        return false;
      }
    }
    return true;
  };

  const auto encodePathHex = [](const std::string &value) {
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (const unsigned char byte : value) {
      output << std::setw(2) << static_cast<unsigned int>(byte);
    }
    return output.str();
  };

  const auto inspectFileCrc32 = [&](const std::string &relativeName,
                                    std::uint64_t &fileSize,
                                    std::uint32_t &crc32) {
    if (!isRegularFileWithoutSymlinks(std::filesystem::path(relativeName))) return false;
    std::ifstream input(relativeName, std::ios::binary);
    if (!input.is_open()) return false;

    std::uint64_t totalBytes = 0;
    std::uint32_t crc = 0xFFFFFFFFu;
    char buffer[64 * 1024];
    while (input) {
      input.read(buffer, sizeof(buffer));
      const std::streamsize bytesRead = input.gcount();
      if (bytesRead > 0) {
        totalBytes += static_cast<std::uint64_t>(bytesRead);
        for (std::streamsize index = 0; index < bytesRead; ++index) {
          crc ^= static_cast<std::uint8_t>(buffer[index]);
          for (int bit = 0; bit < 8; ++bit) {
            crc = (crc & 1u) ? ((crc >> 1) ^ 0xEDB88320u) : (crc >> 1);
          }
        }
      }
    }
    if (input.bad()) return false;
    fileSize = totalBytes;
    crc32 = crc ^ 0xFFFFFFFFu;
    return true;
  };

  const auto loadExpectedDataPaths = [&](std::vector<std::string> &paths) {
    const char *manifestPath = "platinum-data-paths.txt";
    if (!isRegularFileWithoutSymlinks(std::filesystem::path(manifestPath))) return false;
    std::ifstream manifest(manifestPath);
    if (!manifest.is_open()) return false;

    std::string line;
    if (!std::getline(manifest, line) || line != "PLATINA_DATA_PATHS_V1") return false;
    if (!std::getline(manifest, line) || line.empty()) return false;

    std::size_t expectedCount = 0;
    try {
      std::size_t parsedCharacters = 0;
      const unsigned long long parsed = std::stoull(line, &parsedCharacters, 10);
      if (parsedCharacters != line.size() || parsed < 300 || parsed > 2000) return false;
      expectedCount = static_cast<std::size_t>(parsed);
    } catch (...) {
      return false;
    }

    std::string previousPath;
    while (std::getline(manifest, line)) {
      if (line.empty() || line.find('\\') != std::string::npos ||
          line.find(':') != std::string::npos || line.find('\0') != std::string::npos) {
        return false;
      }
      const std::filesystem::path relativePath(line);
      if (relativePath.empty() || relativePath.is_absolute() || relativePath.has_root_name()) return false;
      for (const auto &part : relativePath) {
        const std::string component = part.string();
        if (component.empty() || component == "." || component == "..") return false;
      }
      if (!previousPath.empty() && line <= previousPath) return false;
      previousPath = line;
      paths.push_back(line);
    }
    if (manifest.bad() || paths.size() != expectedCount) return false;

    const std::vector<std::string> requiredRootFiles = {
      "header.bin", "firmware.bin", "wazaeffect/we.arc", "battle/skill/waza_seq.narc"
    };
    for (const std::string &required : requiredRootFiles) {
      if (!std::binary_search(paths.begin(), paths.end(), required)) return false;
    }
    return true;
  };

  const auto validateExtractedData = [&](const std::vector<std::string> &paths,
                                         std::string *missingPath) {
    for (const std::string &relativeName : paths) {
      std::uint64_t fileSize = 0;
      std::uint32_t crc32 = 0;
      if (!inspectFileCrc32(relativeName, fileSize, crc32)) {
        if (missingPath != NULL) *missingPath = relativeName;
        return false;
      }
      if ((relativeName == "header.bin" && fileSize < 0x4000) ||
          (relativeName == "firmware.bin" && fileSize == 0) ||
          (relativeName == "wazaeffect/we.arc" && fileSize == 0) ||
          (relativeName == "battle/skill/waza_seq.narc" && fileSize == 0)) {
        if (missingPath != NULL) *missingPath = relativeName + " (tamanho inválido)";
        return false;
      }
    }
    return true;
  };

  const auto verifyExtractionCache = [&](const std::vector<std::string> &paths,
                                         const std::string &romSha256) {
    const char *cachePath = "platina-rom-extraction.manifest";
    if (!isRegularFileWithoutSymlinks(std::filesystem::path(cachePath))) return false;
    std::ifstream cache(cachePath);
    if (!cache.is_open()) return false;

    std::string line;
    if (!std::getline(cache, line) || line != "PLATINA_EXTRACTION_CACHE_V1") return false;
    if (!std::getline(cache, line) || line != romSha256) return false;
    if (!std::getline(cache, line)) return false;

    std::size_t cachedCount = 0;
    try {
      std::size_t parsedCharacters = 0;
      const unsigned long long parsed = std::stoull(line, &parsedCharacters, 10);
      if (parsedCharacters != line.size() || parsed != paths.size()) return false;
      cachedCount = static_cast<std::size_t>(parsed);
    } catch (...) {
      return false;
    }

    for (std::size_t index = 0; index < cachedCount; ++index) {
      if (!std::getline(cache, line)) return false;
      std::istringstream entry(line);
      std::string pathHex;
      std::string sizeText;
      std::string crcText;
      std::string extra;
      if (!(entry >> pathHex >> sizeText >> crcText) || (entry >> extra)) return false;
      if (pathHex != encodePathHex(paths[index]) || crcText.size() != 8) return false;

      std::uint64_t cachedSize = 0;
      std::uint32_t cachedCrc = 0;
      try {
        std::size_t sizeCharacters = 0;
        const unsigned long long parsedSize = std::stoull(sizeText, &sizeCharacters, 10);
        if (sizeCharacters != sizeText.size()) return false;
        cachedSize = static_cast<std::uint64_t>(parsedSize);

        std::size_t crcCharacters = 0;
        const unsigned long parsedCrc = std::stoul(crcText, &crcCharacters, 16);
        if (crcCharacters != crcText.size() || parsedCrc > 0xFFFFFFFFul) return false;
        cachedCrc = static_cast<std::uint32_t>(parsedCrc);
      } catch (...) {
        return false;
      }

      std::uint64_t actualSize = 0;
      std::uint32_t actualCrc = 0;
      if (!inspectFileCrc32(paths[index], actualSize, actualCrc) ||
          actualSize != cachedSize || actualCrc != cachedCrc) return false;
    }

    if (std::getline(cache, line)) return false;
    return !cache.bad();
  };

  const auto writeExtractionCache = [&](const std::vector<std::string> &paths,
                                        const std::string &romSha256) {
    const std::filesystem::path cachePath("platina-rom-extraction.manifest");
    const std::filesystem::path tempPath("platina-rom-extraction.manifest.tmp");
    const std::filesystem::path previousPath("platina-rom-extraction.manifest.previous");
    std::error_code fileError;
    const auto cacheStatus = std::filesystem::symlink_status(cachePath, fileError);
    if (!fileError && std::filesystem::is_symlink(cacheStatus)) return false;
    if (fileError && fileError != std::errc::no_such_file_or_directory) return false;

    fileError.clear();
    const auto tempStatus = std::filesystem::symlink_status(tempPath, fileError);
    if (!fileError && std::filesystem::is_symlink(tempStatus)) return false;
    if (!fileError && std::filesystem::exists(tempStatus)) {
      if (!std::filesystem::is_regular_file(tempStatus)) return false;
      std::filesystem::remove(tempPath, fileError);
      if (fileError) return false;
    } else if (fileError && fileError != std::errc::no_such_file_or_directory) {
      return false;
    }

    std::ofstream output(tempPath, std::ios::binary | std::ios::out | std::ios::trunc);
    if (!output.is_open()) return false;
    output << "PLATINA_EXTRACTION_CACHE_V1\n" << romSha256 << '\n' << paths.size() << '\n';
    for (const std::string &relativeName : paths) {
      std::uint64_t fileSize = 0;
      std::uint32_t crc32 = 0;
      if (!inspectFileCrc32(relativeName, fileSize, crc32)) {
        output.close();
        std::filesystem::remove(tempPath, fileError);
        return false;
      }
      output << encodePathHex(relativeName) << ' ' << fileSize << ' '
             << std::hex << std::setw(8) << std::setfill('0') << crc32
             << std::dec << std::setfill(' ') << '\n';
    }
    output.flush();
    if (!output.good()) {
      output.close();
      std::filesystem::remove(tempPath, fileError);
      return false;
    }
    output.close();
    if (output.fail()) {
      std::filesystem::remove(tempPath, fileError);
      return false;
    }

    // Rename the old marker aside, then promote the fully written temporary
    // manifest. If promotion fails, preserve/restore the previous marker.
    bool movedPrevious = false;
    fileError.clear();
    const auto previousStatus = std::filesystem::symlink_status(previousPath, fileError);
    if (!fileError && std::filesystem::is_symlink(previousStatus)) return false;
    if (!fileError && std::filesystem::exists(previousStatus)) {
      if (!std::filesystem::is_regular_file(previousStatus)) return false;
      std::filesystem::remove(previousPath, fileError);
      if (fileError) return false;
    } else if (fileError && fileError != std::errc::no_such_file_or_directory) {
      return false;
    }

    fileError.clear();
    if (std::filesystem::exists(cachePath, fileError)) {
      if (fileError) return false;
      std::filesystem::rename(cachePath, previousPath, fileError);
      if (fileError) return false;
      movedPrevious = true;
    } else if (fileError && fileError != std::errc::no_such_file_or_directory) {
      return false;
    }

    fileError.clear();
    std::filesystem::rename(tempPath, cachePath, fileError);
    if (fileError) {
      if (movedPrevious) {
        std::error_code restoreError;
        std::filesystem::rename(previousPath, cachePath, restoreError);
      }
      return false;
    }
    if (movedPrevious) {
      std::error_code cleanupError;
      std::filesystem::remove(previousPath, cleanupError);
    }
    return true;
  };

  const char *managedRomPath = getenv("PLATINA_IMPORTED_ROM");
  if (managedRomPath != NULL && managedRomPath[0] != '\0') {
    std::error_code romError;
    const std::filesystem::path importedRom(managedRomPath);
    if (!std::filesystem::is_regular_file(importedRom, romError) || romError) {
      fprintf(stderr, "[Platina] Imported ROM is not a readable regular file: %s\n", managedRomPath);
      return 2;
    }

    const char *managedRomSha256 = getenv("PLATINA_IMPORTED_ROM_SHA256");
    if (managedRomSha256 == NULL || std::strlen(managedRomSha256) != 64 ||
        !std::all_of(managedRomSha256, managedRomSha256 + 64,
                     [](unsigned char value) { return std::isxdigit(value) != 0; })) {
      fprintf(stderr, "[Platina] Imported ROM has no valid SHA-256 identity in the launcher environment.\n");
      return 2;
    }
    const std::string romSha256(managedRomSha256);

    std::vector<std::string> expectedDataPaths;
    if (!loadExpectedDataPaths(expectedDataPaths)) {
      fprintf(stderr, "[Platina] The packaged Platinum data-path manifest is missing or invalid. Rebuild the desktop package.\n");
      return 4;
    }

    if (!verifyExtractionCache(expectedDataPaths, romSha256)) {
      fprintf(stdout, "[Platina] Verifying or extracting local game data before renderer startup.\n");
      fflush(stdout);
      int extractionStatus = -1;
      try {
        extractionStatus = SIM_NDSExtract(std::string(managedRomPath));
      } catch (const std::exception &exception) {
        fprintf(stderr, "[Platina] ROM extraction threw an exception: %s\n", exception.what());
        return 3;
      }
      if (extractionStatus != 0) {
        fprintf(stderr, "[Platina] ROM extraction failed with status %d.\n", extractionStatus);
        return 3;
      }

      std::string missingDataPath;
      if (!validateExtractedData(expectedDataPaths, &missingDataPath)) {
        fprintf(stderr, "[Platina] Extractor returned success, but required local data is missing/corrupted: %s\n",
                missingDataPath.c_str());
        return 4;
      }
      if (!writeExtractionCache(expectedDataPaths, romSha256)) {
        fprintf(stderr, "[Platina] Warning: extracted data passed validation, but its integrity manifest could not be saved; the next launch will verify/extract again.\n");
      } else {
        // Re-read the just-written manifest to ensure it can be trusted on the
        // next launch, before renderer startup begins.
        if (!verifyExtractionCache(expectedDataPaths, romSha256)) {
          fprintf(stderr, "[Platina] Integrity manifest self-check failed after extraction.\n");
          return 4;
        }
      }

      fprintf(stdout, "[Platina] Local game data extraction and integrity check completed.\n");
      fflush(stdout);
    } else {
      fprintf(stdout, "[Platina] Reusing local game data after per-file CRC32 verification.\n");
      fflush(stdout);
    }
  }
#ifdef SDK_BUILD_NX'''

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
GL_LOADER_PATCHED = r'''  if (!gladLoadGLLoader(SDL_GL_GetProcAddress)) {
    fprintf(stderr, "OpenGL function loader initialization failed.\n");
    SDL_GL_DeleteContext(context);
    SDL_DestroyWindow(window);
    context = NULL;
    window = NULL;
    return NULL;
  }'''

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
FS_OPEN_FALLBACK_PATCHED = r'''        const char *managedRomPath = getenv("PLATINA_IMPORTED_ROM");
        if (managedRomPath != NULL && managedRomPath[0] != '\0') {
            if (sLauncherManagedRomExtractionAttempted) {
                fprintf(stderr, "[file-system] Resource still missing after one extraction attempt: %s\n", path);
                return FALSE;
            }
            sLauncherManagedRomExtractionAttempted = TRUE;
            fprintf(stderr, "[file-system] Missing resource %s; extracting data from the imported ROM once.\n", path);
            SIM_ShowRomExtractionDialog();
            return FS_OpenFile(p_file, path);
        }
        #if FS_FILE_OPEN_DEBUG
        char messageBuf[200] = {0};
        snprintf(messageBuf, 199, "Failed to open file '%s'.", path);
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_INFORMATION, "ROM Extraction Required", messageBuf, NULL);
        #else
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_INFORMATION, "ROM Extraction Required", "ROM filesystem is missing. Select 'OK' and choose a NDS ROM file in the next step.", NULL);
        #endif

        SIM_ShowRomExtractionDialog();

        // Manual desktop launches may still use the legacy extraction flow.
        return FS_OpenFile(p_file, path);'''
SIM_ROM_EXTRACTOR_ORIGINAL = r'''void SIM_ShowRomExtractionDialog() {
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

SIM_ROM_EXTRACTOR_PATCHED = r'''void SIM_ShowRomExtractionDialog() {
    const char *managedRomPath = std::getenv("PLATINA_IMPORTED_ROM");
    if (managedRomPath != nullptr && managedRomPath[0] != '\0') {
        const int extractionStatus = SIM_NDSExtract(std::string(managedRomPath));
        if (extractionStatus != 0) {
            std::fprintf(stderr, "[rom-extract] Automatic extraction failed with status %d.\n", extractionStatus);
        } else {
            std::fprintf(stderr, "[rom-extract] Missing runtime data extracted from the imported ROM.\n");
        }
        return;
    }

    bool fileSelected = false;
    SIM::GUI::Enable();
    SIM::GUI::OpenFileDialog([&fileSelected](std::string fileName) {
        SIM_NDSExtract(fileName);
        fileSelected = true;
    });
    while(!fileSelected) {
        SIM_Render(nullptr);
    }
}'''

SIM_ROM_EXTRACTOR_INCLUDE_ORIGINAL = "#include <SDL2/SDL.h>\n#include <string>"
SIM_ROM_EXTRACTOR_INCLUDE_PATCHED = "#include <SDL2/SDL.h>\n#include <cstdio>\n#include <cstdlib>\n#include <string>"

BACKUP_SAVE_PATH_INCLUDE_ORIGINAL = '''#ifdef SDK_PORT
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#endif'''
BACKUP_SAVE_PATH_INCLUDE_PATCHED = '''#ifdef SDK_PORT
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CARDI_BACKUP_SAVE_FILE "save.bin"
#endif'''

BACKUP_FILE_IO_HELPERS_PATCHED = "static inline FILE *CARDi_OpenBackupFileForRange("
BACKUP_READ_BODY_ORIGINAL = r'''    FILE * backupFilePtr;
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

    return TRUE;'''
BACKUP_READ_BODY_PATCHED = r'''    FILE * backupFilePtr;
    size_t bytesRead;
    int closeStatus;
    if (len == 0) {
      if (callback != NULL) callback(arg);
      return TRUE;
    }
    if (dst == NULL) return FALSE;
    backupFilePtr = CARDi_OpenBackupFileForRange(src, len);
    if (backupFilePtr == NULL) return FALSE;
    if (fseek(backupFilePtr, (long)src, SEEK_SET) != 0) {
      fclose(backupFilePtr);
      return FALSE;
    }
    bytesRead = fread(dst, 1, len, backupFilePtr);
    closeStatus = fclose(backupFilePtr);
    if (bytesRead != (size_t)len || closeStatus != 0) return FALSE;
    if (callback != NULL)
    {
      callback(arg);
    }
    return TRUE;'''

BACKUP_WRITE_BODY_ORIGINAL = r'''    FILE * backupFilePtr;
    backupFilePtr = fopen("save.bin", "rb+");
    fseek(backupFilePtr, dst, SEEK_SET);
    fwrite(src, 1, len, backupFilePtr);
    fclose(backupFilePtr);
    if( callback != NULL )
    {
      callback(arg);
    }
    return TRUE;'''
BACKUP_WRITE_BODY_PATCHED = r'''    FILE * backupFilePtr;
    size_t bytesWritten;
    int flushStatus;
    int closeStatus;
    if (len == 0) {
      if (callback != NULL) callback(arg);
      return TRUE;
    }
    if (src == NULL) return FALSE;
    backupFilePtr = CARDi_OpenBackupFileForRange(dst, len);
    if (backupFilePtr == NULL) return FALSE;
    if (fseek(backupFilePtr, (long)dst, SEEK_SET) != 0) {
      fclose(backupFilePtr);
      return FALSE;
    }
    bytesWritten = fwrite(src, 1, len, backupFilePtr);
    flushStatus = fflush(backupFilePtr);
    closeStatus = fclose(backupFilePtr);
    if (bytesWritten != (size_t)len || flushStatus != 0 || closeStatus != 0) {
      return FALSE;
    }
    if (callback != NULL)
    {
      callback(arg);
    }
    return TRUE;'''

BACKUP_WRITE_VERIFY_BODY_ORIGINAL = r'''    FILE * backupFilePtr;
    backupFilePtr = fopen("save.bin", "rb+");
    fseek(backupFilePtr, dst, SEEK_SET);
    fwrite(src, 1, len, backupFilePtr);
    fclose(backupFilePtr);
    if( callback != NULL )
    {
      callback(arg);
    }
    return CARD_RESULT_SUCCESS;'''
BACKUP_WRITE_VERIFY_BODY_PATCHED = r'''    FILE * backupFilePtr;
    size_t bytesWritten;
    int flushStatus;
    int closeStatus;
    if (len == 0) {
      if (callback != NULL) callback(arg);
      return TRUE;
    }
    if (src == NULL) return FALSE;
    backupFilePtr = CARDi_OpenBackupFileForRange(dst, len);
    if (backupFilePtr == NULL) return FALSE;
    if (fseek(backupFilePtr, (long)dst, SEEK_SET) != 0) {
      fclose(backupFilePtr);
      return FALSE;
    }
    bytesWritten = fwrite(src, 1, len, backupFilePtr);
    flushStatus = fflush(backupFilePtr);
    closeStatus = fclose(backupFilePtr);
    if (bytesWritten != (size_t)len || flushStatus != 0 || closeStatus != 0) {
      return FALSE;
    }
    if (!CARDi_VerifyBackupFileRange(dst, src, len)) return FALSE;
    if (callback != NULL)
    {
      callback(arg);
    }
    return TRUE;'''

BACKUP_FILE_IO_HELPERS = r'''#ifdef SDK_PORT
static inline BOOL CARDi_EnsureBackupFileSize(FILE *backupFilePtr, u32 requiredSize)
{
    static const u8 zeroBuffer[4096] = {0};
    long currentSize;
    u32 remaining;

    if (backupFilePtr == NULL || fseek(backupFilePtr, 0, SEEK_END) != 0) {
        return FALSE;
    }
    currentSize = ftell(backupFilePtr);
    if (currentSize < 0) return FALSE;
    if ((unsigned long)currentSize >= (unsigned long)requiredSize) return TRUE;
    if (fseek(backupFilePtr, currentSize, SEEK_SET) != 0) return FALSE;

    remaining = requiredSize - (u32)currentSize;
    while (remaining > 0) {
        size_t chunkSize = remaining < sizeof(zeroBuffer)
            ? (size_t)remaining : sizeof(zeroBuffer);
        if (fwrite(zeroBuffer, 1, chunkSize, backupFilePtr) != chunkSize) {
            return FALSE;
        }
        remaining -= (u32)chunkSize;
    }
    return fflush(backupFilePtr) == 0;
}

static inline FILE *CARDi_OpenBackupFileForRange(u32 offset, u32 length)
{
    FILE *backupFilePtr;
    int openError;

    if (offset > ((u32)-1) - length) return NULL;
    backupFilePtr = fopen(CARDI_BACKUP_SAVE_FILE, "rb+");
    if (backupFilePtr == NULL) {
        openError = errno;
        // Never fall back to "wb+" for access or I/O errors: that could
        // truncate an existing save that simply could not be opened.
        if (openError != ENOENT) return NULL;
        backupFilePtr = fopen(CARDI_BACKUP_SAVE_FILE, "wb+");
        if (backupFilePtr == NULL) return NULL;
    }

    if (!CARDi_EnsureBackupFileSize(backupFilePtr, offset + length)) {
        fclose(backupFilePtr);
        return NULL;
    }
    return backupFilePtr;
}

static inline BOOL CARDi_VerifyBackupFileRange(u32 offset, const void *expectedBytes, u32 length)
{
    FILE *backupFilePtr;
    const u8 *expected = (const u8 *)expectedBytes;
    u8 verifyBuffer[4096];
    u32 remaining = length;

    if (length == 0) return TRUE;
    if (expectedBytes == NULL) return FALSE;
    backupFilePtr = fopen(CARDI_BACKUP_SAVE_FILE, "rb");
    if (backupFilePtr == NULL) return FALSE;
    if (fseek(backupFilePtr, (long)offset, SEEK_SET) != 0) {
        fclose(backupFilePtr);
        return FALSE;
    }

    while (remaining > 0) {
        size_t chunkSize = remaining < sizeof(verifyBuffer)
            ? (size_t)remaining : sizeof(verifyBuffer);
        size_t bytesRead = fread(verifyBuffer, 1, chunkSize, backupFilePtr);
        if (bytesRead != chunkSize || memcmp(verifyBuffer, expected, chunkSize) != 0) {
            fclose(backupFilePtr);
            return FALSE;
        }
        expected += chunkSize;
        remaining -= (u32)chunkSize;
    }
    return fclose(backupFilePtr) == 0;
}
#endif /* SDK_PORT */

'''

CONFIG_SAVE_OPEN_PATCHED = (
    CONFIG_SAVE_OPEN_ORIGINAL
    + "\n    if (configFile == NULL) {\n        return;\n    }"
)


class RuntimePreparationError(RuntimeError):
    pass


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


def _prepare_backup_save_path(source_root: str | Path) -> tuple[Path, str, bool]:
    """Keep save I/O safe and fail closed on errors."""
    header_path = (
        Path(source_root).expanduser().resolve()
        / "subprojects" / "libntr" / "include" / "nitro" / "card" / "backup.h"
    )
    if not header_path.is_file():
        raise RuntimePreparationError(f"Card backup header missing: {header_path}")

    original = header_path.read_text(encoding="utf-8")
    current = original

    if BACKUP_FILE_IO_HELPERS_PATCHED in current:
        if current.count(BACKUP_FILE_IO_HELPERS_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate checked card-backup I/O helper block.")
        if "#ifdef SDK_PORT\nstatic inline BOOL CARDi_EnsureBackupFileSize" not in current:
            raise RuntimePreparationError("Card-backup I/O helper is not guarded by SDK_PORT.")
        if "#endif /* SDK_PORT */\n\n  SDK_INLINE BOOL CARDi_ReadBackup(" not in current:
            raise RuntimePreparationError("Card-backup I/O helper SDK_PORT guard is incomplete.")
        expected_patched = (
            BACKUP_READ_BODY_PATCHED,
            BACKUP_WRITE_BODY_PATCHED,
            BACKUP_WRITE_VERIFY_BODY_PATCHED,
        )
        expected_original = (
            BACKUP_READ_BODY_ORIGINAL,
            BACKUP_WRITE_BODY_ORIGINAL,
            BACKUP_WRITE_VERIFY_BODY_ORIGINAL,
        )
        if any(current.count(block) != 1 for block in expected_patched):
            raise RuntimePreparationError("Card-backup I/O patch is incomplete or duplicated.")
        if any(block in current for block in expected_original):
            raise RuntimePreparationError("Both original and hardened card-backup bodies exist.")
        if 'fopen("save.bin",' in current:
            raise RuntimePreparationError("Legacy save.bin fopen call remains after hardening.")
        return header_path, current, current != original

    # Upgrade an earlier desktop save-path-only patch, or start from upstream.
    legacy_include = '''#ifdef SDK_PORT
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CARDI_BACKUP_SAVE_FILE "save.bin"
#endif'''
    if BACKUP_SAVE_PATH_INCLUDE_PATCHED in current:
        if current.count(BACKUP_SAVE_PATH_INCLUDE_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate desktop save-path macro in backup.h.")
    elif legacy_include in current:
        if current.count(legacy_include) != 1:
            raise RuntimePreparationError("Duplicate legacy desktop save-path macro in backup.h.")
        current = current.replace(legacy_include, BACKUP_SAVE_PATH_INCLUDE_PATCHED, 1)
    else:
        if current.count(BACKUP_SAVE_PATH_INCLUDE_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected exactly one SDK_PORT include block in backup.h; refusing uncertain save-path patch."
            )
        current = current.replace(
            BACKUP_SAVE_PATH_INCLUDE_ORIGINAL, BACKUP_SAVE_PATH_INCLUDE_PATCHED, 1
        )

    original_open_count = current.count('fopen("save.bin",')
    previous_patch_open_count = current.count("fopen(CARDI_BACKUP_SAVE_FILE,")
    if original_open_count == 5 and previous_patch_open_count == 0:
        body_replacements = (
            (BACKUP_READ_BODY_ORIGINAL, BACKUP_READ_BODY_PATCHED, "CARDi_ReadBackup"),
            (BACKUP_WRITE_BODY_ORIGINAL, BACKUP_WRITE_BODY_PATCHED, "CARDi_WriteBackup"),
            (BACKUP_WRITE_VERIFY_BODY_ORIGINAL, BACKUP_WRITE_VERIFY_BODY_PATCHED, "CARDi_WriteAndVerifyBackup"),
        )
    elif original_open_count == 0 and previous_patch_open_count == 5:
        # Upgrade a checkout prepared by the earlier save-path-only patcher.
        macro_read = BACKUP_READ_BODY_ORIGINAL.replace(
            'fopen("save.bin",', "fopen(CARDI_BACKUP_SAVE_FILE,"
        )
        macro_write = BACKUP_WRITE_BODY_ORIGINAL.replace(
            'fopen("save.bin",', "fopen(CARDI_BACKUP_SAVE_FILE,"
        )
        macro_write_verify = BACKUP_WRITE_VERIFY_BODY_ORIGINAL.replace(
            'fopen("save.bin",', "fopen(CARDI_BACKUP_SAVE_FILE,"
        )
        body_replacements = (
            (macro_read, BACKUP_READ_BODY_PATCHED, "CARDi_ReadBackup"),
            (macro_write, BACKUP_WRITE_BODY_PATCHED, "CARDi_WriteBackup"),
            (macro_write_verify, BACKUP_WRITE_VERIFY_BODY_PATCHED, "CARDi_WriteAndVerifyBackup"),
        )
    else:
        raise RuntimePreparationError(
            "Expected five consistent save.bin call sites (upstream or previous save-path patch); "
            f"found {original_open_count} upstream and {previous_patch_open_count} patched calls."
        )

    for expected, hardened, label in body_replacements:
        if current.count(expected) != 1:
            raise RuntimePreparationError(
                f"Expected exactly one recognized {label} body in backup.h; refusing uncertain I/O patch."
            )
        current = current.replace(expected, hardened, 1)

    insertion_marker = "  SDK_INLINE BOOL CARDi_ReadBackup("
    if current.count(insertion_marker) != 1:
        raise RuntimePreparationError("Cannot locate the card-backup read function for helper insertion.")
    current = current.replace(insertion_marker, BACKUP_FILE_IO_HELPERS + insertion_marker, 1)

    if 'fopen("save.bin",' in current:
        raise RuntimePreparationError("Legacy save.bin fopen call remains after hardening.")
    if current.count(BACKUP_FILE_IO_HELPERS_PATCHED) != 1:
        raise RuntimePreparationError("Checked card-backup I/O helper was not installed exactly once.")
    return header_path, current, current != original



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
    patched_include = (
        "#include <string.h>\n#include <stdlib.h>\n#include <stdio.h>\n#include <SDL2/SDL.h>\n"
        "static BOOL sLauncherManagedRomExtractionAttempted = FALSE;"
    )
    if patched_include in current:
        if current.count(patched_include) != 1:
            raise RuntimePreparationError("Duplicate stdlib include in fs_file.c.")
    else:
        if current.count(original_include) != 1:
            raise RuntimePreparationError("Expected exactly one SDK_PORT include block in fs_file.c.")
        current = current.replace(original_include, patched_include, 1)
        patched = True

    return fs_path, current, current != original


def _prepare_sim_rom_extractor(source_root: str | Path) -> tuple[Path, str, bool]:
    """Use the launcher-imported ROM automatically when runtime data is missing."""
    extractor_path = (
        Path(source_root).expanduser().resolve()
        / "subprojects" / "libntr" / "libraries" / "sim" / "src" / "sim_RomExtractor.cpp"
    )
    if not extractor_path.is_file():
        raise RuntimePreparationError(f"Simulator ROM extractor source missing: {extractor_path}")

    original = extractor_path.read_text(encoding="utf-8")
    current = original
    if SIM_ROM_EXTRACTOR_PATCHED in current:
        if current.count(SIM_ROM_EXTRACTOR_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate automatic ROM extractor patch detected.")
        if SIM_ROM_EXTRACTOR_ORIGINAL in current:
            raise RuntimePreparationError("Both original and patched ROM extractor functions exist.")
    else:
        if current.count(SIM_ROM_EXTRACTOR_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected exactly one known SIM_ShowRomExtractionDialog implementation; refusing uncertain patch."
            )
        current = current.replace(SIM_ROM_EXTRACTOR_ORIGINAL, SIM_ROM_EXTRACTOR_PATCHED, 1)

    if SIM_ROM_EXTRACTOR_INCLUDE_PATCHED in current:
        if current.count(SIM_ROM_EXTRACTOR_INCLUDE_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate include block in sim_RomExtractor.cpp.")
    else:
        if current.count(SIM_ROM_EXTRACTOR_INCLUDE_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected exactly one known include block in sim_RomExtractor.cpp."
            )
        current = current.replace(
            SIM_ROM_EXTRACTOR_INCLUDE_ORIGINAL, SIM_ROM_EXTRACTOR_INCLUDE_PATCHED, 1
        )

    return extractor_path, current, current != original


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


def _prepare_rom_preflight(source: str) -> tuple[str, bool]:
    """Move first-launch ROM extraction before SDL/window startup; fail closed on upstream drift."""
    current = source
    if ROM_PREFLIGHT_ENTRY_PATCHED in current:
        if current.count(ROM_PREFLIGHT_ENTRY_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate managed-ROM preflight patch detected.")
        if ROM_PREFLIGHT_ENTRY_ORIGINAL in current:
            raise RuntimePreparationError("Original and patched managed-ROM entry blocks both exist.")
    else:
        if current.count(ROM_PREFLIGHT_ENTRY_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected one recognized main() entry point for managed-ROM preflight."
            )
        current = current.replace(ROM_PREFLIGHT_ENTRY_ORIGINAL, ROM_PREFLIGHT_ENTRY_PATCHED, 1)

    if ROM_PREFLIGHT_INCLUDE_PATCHED in current:
        if current.count(ROM_PREFLIGHT_INCLUDE_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate managed-ROM preflight includes detected.")
    else:
        if current.count(ROM_PREFLIGHT_INCLUDE_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected one SDL include marker for managed-ROM preflight; refusing uncertain patch."
            )
        current = current.replace(
            ROM_PREFLIGHT_INCLUDE_ORIGINAL, ROM_PREFLIGHT_INCLUDE_PATCHED, 1
        )
    return current, current != source


def prepare_native_runtime(source_root: str | Path) -> bool:
    """Prepare the desktop ROM handoff, renderer startup, config, filesystem and saves."""
    path = (Path(source_root).expanduser().resolve() / "subprojects" / "libntr"
            / "libraries" / "sim" / "src" / "sim_main.cpp")
    if not path.is_file():
        raise RuntimePreparationError(f"Simulator source missing: {path}")

    original = path.read_text(encoding="utf-8")
    current = original
    current_load_count = current.count(PATCHED_HEADER_LOAD)
    upstream_count = current.count(ORIGINAL_HEADER_LOAD)

    if current_load_count == 1 and upstream_count == 0:
        pass
    elif current_load_count == 0 and upstream_count == 1:
        current = current.replace(ORIGINAL_HEADER_LOAD, PATCHED_HEADER_LOAD, 1)
    else:
        raise RuntimePreparationError(
            "Expected exactly one recognized upstream or desktop-patched ROM-header loader; refusing an uncertain patch."
        )

    current, _ = _prepare_renderer_startup(current)
    current, _ = _prepare_rom_preflight(current)

    # Validate every source file before writing any of them.
    config_path = path.parent / "config" / "sim_config.c"
    config_updated, config_changed = _prepare_sim_config(config_path)
    fs_path, fs_updated, fs_changed = _prepare_fs_missing_resource_fallback(source_root)
    extractor_path, extractor_updated, extractor_changed = _prepare_sim_rom_extractor(source_root)
    backup_path, backup_updated, backup_changed = _prepare_backup_save_path(source_root)

    changed = (
        current != original or config_changed or fs_changed or extractor_changed or backup_changed
    )
    if current != original:
        path.write_text(current, encoding="utf-8")
    if config_changed:
        config_path.write_text(config_updated, encoding="utf-8")
    if fs_changed:
        fs_path.write_text(fs_updated, encoding="utf-8")
    if extractor_changed:
        extractor_path.write_text(extractor_updated, encoding="utf-8")
    if backup_changed:
        backup_path.write_text(backup_updated, encoding="utf-8")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", help="Pinned pokeplatinum source root")
    args = parser.parse_args(argv)
    try:
        changed = prepare_native_runtime(args.source_root)
    except (OSError, RuntimePreparationError) as exc:
        print(f"Native runtime preparation failed: {exc}", file=sys.stderr)
        return 2
    print("Native runtime preparation patches applied." if changed else "Native runtime preparation already applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
