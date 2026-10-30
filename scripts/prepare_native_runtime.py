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
  // "--platina-prepare": the launcher runs the extraction/verification phase
  // as a separate step (with progress in its own UI), then starts the game.
  bool platinaPrepareOnly = false;
  bool platinaPreparedByLauncher = false;
  for (int argIndex = 1; argIndex < argc; ++argIndex) {
    if (std::strcmp(argv[argIndex], "--platina-prepare") == 0) platinaPrepareOnly = true;
    if (std::strcmp(argv[argIndex], "--platina-prepared") == 0) platinaPreparedByLauncher = true;
  }
  if (!platinaPrepareOnly) {
    fprintf(stderr, "[Platina-Progress] native-boot-start\n");
    fflush(stderr);
  }
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
    std::ifstream input;
    for (int attempt = 0; attempt < 20 && !input.is_open(); ++attempt) {
      input.clear();
      input.open(relativeName, std::ios::binary);
      if (!input.is_open()) SDL_Delay(150);
    }
    if (!input.is_open()) {
      fprintf(stderr, "[Platina] Cannot open %s for verification (locked or missing).\n", relativeName.c_str());
      return false;
    }

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
      "header.bin", "arm9.bin", "arm7.bin", "arm9ovt.bin", "arm7ovt.bin",
      "banner.bin", "fnt.bin", "fat.bin", "rsasig.bin",
      "wazaeffect/we.arc", "battle/skill/waza_seq.narc"
    };
    for (const std::string &required : requiredRootFiles) {
      if (!std::binary_search(paths.begin(), paths.end(), required)) return false;
    }
    return true;
  };

  // ARM9 overlays are expected for the supported Platinum image. ARM7
  // overlays are optional: the extractor can validly produce none when the
  // ROM's ARM7 overlay table has no separate overlay payloads. Include every
  // discovered overlay in the integrity cache and validate every file that
  // exists, without rejecting a legitimate empty ARM7 overlay directory.
  const auto collectOverlayPaths = [&](std::vector<std::string> &paths,
                                       bool requireAll,
                                       bool verifyContents,
                                       std::string *failureReason) {
    const auto fail = [&](const std::string &reason) {
      if (failureReason != NULL) *failureReason = reason;
      fprintf(stderr, "[Platina] Overlay validation failed: %s\n", reason.c_str());
      return false;
    };
    const auto isOverlayFileName = [](const std::string &name, const std::string &prefix) {
      const std::string stem = prefix + "_";
      if (name.compare(0, stem.size(), stem) != 0 ||
          name.size() <= stem.size() + 4 ||
          name.compare(name.size() - 4, 4, ".bin") != 0) return false;
      const std::size_t digitsEnd = name.size() - 4;
      for (std::size_t index = stem.size(); index < digitsEnd; ++index) {
        if (name[index] < '0' || name[index] > '9') return false;
      }
      return digitsEnd > stem.size();
    };

    const auto collectOne = [&](const std::string &directoryName,
                                const std::string &prefix,
                                bool requireAtLeastOne) {
      std::error_code directoryError;
      const auto directoryStatus = std::filesystem::symlink_status(
          std::filesystem::path(directoryName), directoryError);
      if (directoryError == std::errc::no_such_file_or_directory ||
          (!directoryError && !std::filesystem::exists(directoryStatus))) {
        if (requireAtLeastOne) {
          return fail("required " + prefix + " overlay directory is missing: " + directoryName);
        }
        return true;
      }
      if (directoryError || std::filesystem::is_symlink(directoryStatus) ||
          !std::filesystem::is_directory(directoryStatus)) {
        return fail("overlay directory is inaccessible, linked, or not a directory: " + directoryName);
      }

      std::error_code iteratorError;
      std::filesystem::directory_iterator iterator(directoryName, iteratorError);
      const std::filesystem::directory_iterator end;
      if (iteratorError) {
        return fail("cannot enumerate overlay directory " + directoryName + ": " + iteratorError.message());
      }
      std::size_t count = 0;
      for (; iterator != end; iterator.increment(iteratorError)) {
        if (iteratorError) {
          return fail("failed while enumerating overlay directory " + directoryName + ": " + iteratorError.message());
        }
        const std::string name = iterator->path().filename().string();
        if (!isOverlayFileName(name, prefix)) {
          return fail("unexpected entry in " + directoryName + ": " + name);
        }
        const std::string relativeName = directoryName + "/" + name;
        const std::filesystem::path relativePath(relativeName);
        if (!isRegularFileWithoutSymlinks(relativePath)) {
          return fail("overlay is not a safe regular file: " + relativeName);
        }
        std::error_code sizeError;
        const std::uintmax_t fileSize = std::filesystem::file_size(relativePath, sizeError);
        if (sizeError) {
          return fail("cannot read overlay file size: " + relativeName + ": " + sizeError.message());
        }
        if (fileSize == 0 && (requireAll || verifyContents)) {
          return fail("overlay file is empty: " + relativeName);
        }
        if (verifyContents) {
          std::uint64_t verifiedSize = 0;
          std::uint32_t verifiedCrc = 0;
          if (!inspectFileCrc32(relativeName, verifiedSize, verifiedCrc) ||
              verifiedSize != fileSize) {
            return fail("could not fully read or verify overlay file: " + relativeName);
          }
        }
        paths.push_back(relativeName);
        ++count;
      }
      if (iteratorError) {
        return fail("failed while finishing overlay directory " + directoryName + ": " + iteratorError.message());
      }
      if (requireAtLeastOne && count == 0) {
        return fail("no " + prefix + " overlay files were produced in " + directoryName);
      }
      return true;
    };

    // The pinned USA Rev. 1 runtime needs ARM9's overlay set. ARM7's static
    // binary is sufficient for this source, so an empty/missing overlay7
    // directory is valid; if ARM7 overlays exist, validate and cache all of
    // them just like ARM9 overlays.
    if (!collectOne("overlay9", "overlay9", requireAll) ||
        !collectOne("overlay7", "overlay7", false)) return false;
    std::sort(paths.begin(), paths.end());
    return true;
  };

  const auto validateExtractedData = [&](const std::vector<std::string> &paths,
                                         std::string *missingPath) {
    for (const std::string &relativeName : paths) {
      const std::filesystem::path path(relativeName);
      if (!isRegularFileWithoutSymlinks(path)) {
        if (missingPath != NULL) *missingPath = relativeName;
        return false;
      }
      std::error_code sizeError;
      const std::uintmax_t fileSize = std::filesystem::file_size(path, sizeError);
      // ARM7 overlay-table data can legitimately be empty for Platinum
      // images with no separate ARM7 overlays. Keep the file path required,
      // but do not reject the valid zero-byte payload.
      const bool requiredCoreFileIsEmpty =
          ((relativeName == "arm9.bin" || relativeName == "arm7.bin" ||
            relativeName == "arm9ovt.bin" ||
            relativeName == "banner.bin" || relativeName == "fnt.bin" ||
            relativeName == "fat.bin" || relativeName == "rsasig.bin") && fileSize == 0);
      if (sizeError ||
          (relativeName == "header.bin" && fileSize < 0x4000) ||
          requiredCoreFileIsEmpty ||
          (relativeName == "wazaeffect/we.arc" && fileSize == 0) ||
          (relativeName == "battle/skill/waza_seq.narc" && fileSize == 0) ||
          ((relativeName.rfind("overlay9/", 0) == 0 ||
            relativeName.rfind("overlay7/", 0) == 0) && fileSize == 0)) {
        if (missingPath != NULL) *missingPath = relativeName + " (tamanho inválido)";
        return false;
      }
    }
    return true;
  };

  // A failed cache verification must not let stale files mask an incomplete
  // extraction. Remove only allowlisted ROM-derived files, never save/config,
  // the native executable, libraries or the imported ROM.
  const auto canRemoveRelativeFileWithoutSymlinks = [&](const std::string &relativeName) {
    const std::filesystem::path relativePath(relativeName);
    if (relativePath.empty() || relativePath.is_absolute() || relativePath.has_root_name()) return false;
    std::filesystem::path currentPath;
    auto component = relativePath.begin();
    for (; component != relativePath.end(); ++component) {
      const std::string part = component->string();
      if (part.empty() || part == "." || part == ".." ||
          part.find('\\') != std::string::npos || part.find(':') != std::string::npos) return false;
      currentPath /= *component;
      std::error_code statusError;
      const auto status = std::filesystem::symlink_status(currentPath, statusError);
      if (statusError == std::errc::no_such_file_or_directory) return true;
      if (statusError || std::filesystem::is_symlink(status)) return false;
      auto next = component;
      ++next;
      if (next != relativePath.end()) {
        if (!std::filesystem::exists(status)) return true;
        if (!std::filesystem::is_directory(status)) return false;
      } else {
        if (!std::filesystem::exists(status)) return true;
        return std::filesystem::is_regular_file(status);
      }
    }
    return true;
  };

  const auto removeRelativeFileWithoutSymlinks = [&](const std::string &relativeName) {
    const std::filesystem::path relativePath(relativeName);
    if (relativePath.empty() || relativePath.is_absolute() || relativePath.has_root_name()) return false;
    std::filesystem::path currentPath;
    auto component = relativePath.begin();
    for (; component != relativePath.end(); ++component) {
      const std::string part = component->string();
      if (part.empty() || part == "." || part == ".." ||
          part.find('\\') != std::string::npos || part.find(':') != std::string::npos) return false;
      currentPath /= *component;
      std::error_code statusError;
      const auto status = std::filesystem::symlink_status(currentPath, statusError);
      if (statusError == std::errc::no_such_file_or_directory) return true;
      if (statusError || std::filesystem::is_symlink(status)) return false;
      auto next = component;
      ++next;
      if (next != relativePath.end()) {
        if (!std::filesystem::exists(status)) return true;
        if (!std::filesystem::is_directory(status)) return false;
      } else {
        if (!std::filesystem::exists(status)) return true;
        if (!std::filesystem::is_regular_file(status)) return false;
        std::error_code removeError;
        return std::filesystem::remove(currentPath, removeError) && !removeError;
      }
    }
    return true;
  };

  const auto verifyExtractionCache = [&](const std::vector<std::string> &paths,
                                         const std::string &romSha256,
                                         bool verifyFullCrc) {
    bool hasOverlay9 = false;
    for (const std::string &relativeName : paths) {
      if (relativeName.rfind("overlay9/overlay9_", 0) == 0) hasOverlay9 = true;
    }
    // A usable Platinum cache must contain ARM9 overlays. ARM7 overlay files
    // are included and CRC-verified when present, but the group may be empty.
    if (!hasOverlay9) return false;

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

      const std::filesystem::path relativePath(paths[index]);
      if (!isRegularFileWithoutSymlinks(relativePath)) return false;
      std::error_code sizeError;
      const std::uintmax_t actualSize = std::filesystem::file_size(relativePath, sizeError);
      const bool emptyOverlay = actualSize == 0 &&
          (paths[index].rfind("overlay9/", 0) == 0 ||
           paths[index].rfind("overlay7/", 0) == 0);
      if (sizeError || actualSize != cachedSize || emptyOverlay) return false;
      if (verifyFullCrc) {
        std::uint64_t verifiedSize = 0;
        std::uint32_t actualCrc = 0;
        if (!inspectFileCrc32(paths[index], verifiedSize, actualCrc) ||
            verifiedSize != cachedSize || actualCrc != cachedCrc) return false;
      }
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
    const auto importedRomStatus = std::filesystem::symlink_status(importedRom, romError);
    if (romError || std::filesystem::is_symlink(importedRomStatus)
        || !std::filesystem::is_regular_file(importedRomStatus)) {
      fprintf(stderr, "[Platina] Imported ROM is not a safe regular file: %s\n", managedRomPath);
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

    std::vector<std::string> baseDataPaths;
    if (!loadExpectedDataPaths(baseDataPaths)) {
      fprintf(stderr, "[Platina] The packaged Platinum data-path manifest is missing or invalid. Rebuild the desktop package.\n");
      return 4;
    }
    std::vector<std::string> expectedDataPaths = baseDataPaths;
    std::string overlayInspectionFailure;
    if (!collectOverlayPaths(expectedDataPaths, false, false,
                             &overlayInspectionFailure)) {
      fprintf(stderr, "[Platina] The local overlay directories failed validation: %s\n",
              overlayInspectionFailure.c_str());
      return 4;
    }

    fprintf(stdout, "[Platina-Progress] verifying\n");
    fflush(stdout);
    if (!verifyExtractionCache(expectedDataPaths, romSha256, !platinaPreparedByLauncher)) {
      if (platinaPreparedByLauncher) {
        fprintf(stderr, "[Platina] Prepared game data changed after launcher verification. Close the game and run data preparation again from the launcher.\n");
        return 4;
      }
      fprintf(stdout, "[Platina-Progress] extracting\n");
      fprintf(stdout, "[Platina] Cache validation failed; rebuilding extracted data from the imported ROM.\n");
      fflush(stdout);
      // Keep the current cache untouched until a complete replacement has
      // been extracted and verified in a fresh directory.
      const std::vector<std::string> previousDataPaths = expectedDataPaths;
      std::error_code rootError;
      const std::filesystem::path runtimeRoot = std::filesystem::current_path(rootError);
      if (rootError) {
        fprintf(stderr, "[Platina] Cannot resolve the runtime working directory: %s\n",
                rootError.message().c_str());
        return 4;
      }
      rootError.clear();
      const std::filesystem::path absoluteRomPath =
          std::filesystem::absolute(importedRom, rootError);
      if (rootError) {
        fprintf(stderr, "[Platina] Cannot resolve the imported ROM path: %s\n",
                rootError.message().c_str());
        return 2;
      }

      const std::filesystem::path stagingRoot =
          runtimeRoot / ".platina-extraction-staging";
      std::error_code stagingError;
      const auto stagingStatus =
          std::filesystem::symlink_status(stagingRoot, stagingError);
      if (stagingError &&
          stagingError != std::errc::no_such_file_or_directory) {
        fprintf(stderr, "[Platina] Cannot inspect the extraction staging directory: %s\n",
                stagingError.message().c_str());
        return 4;
      }
      if (!stagingError && std::filesystem::exists(stagingStatus)) {
        if (std::filesystem::is_symlink(stagingStatus) ||
            !std::filesystem::is_directory(stagingStatus)) {
          fprintf(stderr, "[Platina] Refusing an unsafe extraction staging path.\n");
          return 4;
        }
        std::filesystem::remove_all(stagingRoot, stagingError);
        if (stagingError) {
          fprintf(stderr, "[Platina] Cannot clear the previous extraction staging directory: %s\n",
                  stagingError.message().c_str());
          return 4;
        }
      }

      stagingError.clear();
      const bool stagingCreated =
          std::filesystem::create_directory(stagingRoot, stagingError);
      if (stagingError || !stagingCreated) {
        fprintf(stderr, "[Platina] Cannot create a clean extraction staging directory: %s\n",
                stagingError ? stagingError.message().c_str() : "directory already exists");
        return 4;
      }
      const auto discardStaging = [&]() {
        std::error_code cleanupError;
        std::filesystem::remove_all(stagingRoot, cleanupError);
        if (cleanupError) {
          fprintf(stderr, "[Platina] Warning: could not remove the temporary extraction directory: %s\n",
                  cleanupError.message().c_str());
        }
      };

      std::vector<std::string> stagedDataPaths;
      std::string stagingFailure;
      bool stagingReady = false;
      try {
        std::error_code changeError;
        std::filesystem::current_path(stagingRoot, changeError);
        if (changeError) {
          stagingFailure = "cannot enter the clean staging directory: " +
                           changeError.message();
        } else {
          try {
            const int extractionStatus = SIM_NDSExtract(absoluteRomPath.string());
            if (extractionStatus != 0) {
              stagingFailure = "ROM extraction failed with status " +
                               std::to_string(extractionStatus);
            } else {
              stagedDataPaths = baseDataPaths;
              std::string overlayExtractionFailure;
              if (!collectOverlayPaths(stagedDataPaths, true, true,
                                       &overlayExtractionFailure)) {
                stagingFailure = "extracted overlay validation failed: " +
                                 overlayExtractionFailure;
              } else {
                std::string missingDataPath;
                if (!validateExtractedData(stagedDataPaths, &missingDataPath)) {
                  stagingFailure = "required extracted data is missing or invalid: " +
                                   missingDataPath;
                } else if (!writeExtractionCache(stagedDataPaths, romSha256)) {
                  stagingFailure = "could not write the staging integrity manifest";
                } else if (!verifyExtractionCache(stagedDataPaths, romSha256, true)) {
                  stagingFailure = "staging integrity manifest self-check failed";
                } else {
                  stagingReady = true;
                }
              }
            }
          } catch (const std::exception &exception) {
            stagingFailure = std::string("ROM extraction threw an exception: ") +
                             exception.what();
          } catch (...) {
            stagingFailure = "ROM extraction failed with an unknown exception";
          }
        }
      } catch (const std::exception &exception) {
        stagingFailure = std::string("staging setup failed: ") + exception.what();
      }

      std::error_code restoreError;
      std::filesystem::current_path(runtimeRoot, restoreError);
      if (restoreError) {
        stagingReady = false;
        stagingFailure = "cannot restore the runtime working directory: " +
                         restoreError.message();
      }
      if (!stagingReady) {
        discardStaging();
        fprintf(stderr, "[Platina] %s. The previous extracted data and cache marker were left untouched.\n",
                stagingFailure.empty() ? "Staged extraction was not validated" :
                                         stagingFailure.c_str());
        return 4;
      }

      // Preflight all source and destination paths before invalidating the
      // current marker. No runtime game data is changed before this point.
      const std::filesystem::path stagingRelativeRoot(
          ".platina-extraction-staging");
      for (const std::string &relativeName : stagedDataPaths) {
        const std::filesystem::path relativePath(relativeName);
        if (!isRegularFileWithoutSymlinks(stagingRelativeRoot / relativePath) ||
            !canRemoveRelativeFileWithoutSymlinks(relativeName)) {
          discardStaging();
          fprintf(stderr, "[Platina] Refusing unsafe staged or destination data path: %s\n",
                  relativeName.c_str());
          return 4;
        }
      }
      for (const std::string &relativeName : previousDataPaths) {
        const bool isOverlay =
            relativeName.rfind("overlay9/", 0) == 0 ||
            relativeName.rfind("overlay7/", 0) == 0;
        const bool stillPresent =
            std::find(stagedDataPaths.begin(), stagedDataPaths.end(),
                      relativeName) != stagedDataPaths.end();
        if (isOverlay && !stillPresent &&
            !canRemoveRelativeFileWithoutSymlinks(relativeName)) {
          discardStaging();
          fprintf(stderr, "[Platina] Refusing to remove an unsafe stale overlay path: %s\n",
                  relativeName.c_str());
          return 4;
        }
      }
      if (!canRemoveRelativeFileWithoutSymlinks("platina-rom-extraction.manifest") ||
          !removeRelativeFileWithoutSymlinks("platina-rom-extraction.manifest")) {
        discardStaging();
        fprintf(stderr, "[Platina] Could not safely invalidate the old extraction marker.\n");
        return 4;
      }

      // The old cache marker stays absent during publication. If any copy
      // fails, the next preparation must rebuild instead of accepting a
      // partially published set of files.
      for (const std::string &relativeName : stagedDataPaths) {
        const std::filesystem::path relativePath(relativeName);
        const std::filesystem::path sourcePath = stagingRoot / relativePath;
        const std::filesystem::path destinationPath = runtimeRoot / relativePath;
        std::error_code copyError;
        std::filesystem::create_directories(destinationPath.parent_path(), copyError);
        if (copyError) {
          discardStaging();
          fprintf(stderr, "[Platina] Cannot create destination directory for %s: %s\n",
                  relativeName.c_str(), copyError.message().c_str());
          return 4;
        }
        const bool copied = std::filesystem::copy_file(
            sourcePath, destinationPath,
            std::filesystem::copy_options::overwrite_existing, copyError);
        if (copyError || !copied) {
          discardStaging();
          fprintf(stderr, "[Platina] Could not publish staged data file %s: %s\n",
                  relativeName.c_str(),
                  copyError ? copyError.message().c_str() : "copy_file returned false");
          return 4;
        }
      }

      // Remove only old overlay files that are absent from the newly verified
      // set. Saves, configuration, ROM files and the native executable are
      // outside both manifests and are never moved or deleted.
      for (const std::string &relativeName : previousDataPaths) {
        const bool isOverlay =
            relativeName.rfind("overlay9/", 0) == 0 ||
            relativeName.rfind("overlay7/", 0) == 0;
        const bool stillPresent =
            std::find(stagedDataPaths.begin(), stagedDataPaths.end(),
                      relativeName) != stagedDataPaths.end();
        if (isOverlay && !stillPresent &&
            !removeRelativeFileWithoutSymlinks(relativeName)) {
          discardStaging();
          fprintf(stderr, "[Platina] Could not remove a stale overlay file: %s\n",
                  relativeName.c_str());
          return 4;
        }
      }

      expectedDataPaths = stagedDataPaths;
      std::string publishedMissingPath;
      if (!validateExtractedData(expectedDataPaths, &publishedMissingPath)) {
        discardStaging();
        fprintf(stderr, "[Platina] Published runtime data failed validation: %s\n",
                publishedMissingPath.c_str());
        return 4;
      }
      if (!writeExtractionCache(expectedDataPaths, romSha256)) {
        (void)removeRelativeFileWithoutSymlinks("platina-rom-extraction.manifest");
        discardStaging();
        fprintf(stderr, "[Platina] Could not write the final runtime integrity manifest.\n");
        return 4;
      }
      if (!verifyExtractionCache(expectedDataPaths, romSha256, true)) {
        (void)removeRelativeFileWithoutSymlinks("platina-rom-extraction.manifest");
        discardStaging();
        fprintf(stderr, "[Platina] Final runtime integrity manifest self-check failed.\n");
        return 4;
      }

      discardStaging();
      fprintf(stdout, "[Platina] Staged game data was validated and published successfully.\n");
      fflush(stdout);
    } else if (platinaPreparedByLauncher) {
      fprintf(stdout, "[Platina] Reusing launcher-prepared game data after regular-file and size verification.\n");
      fflush(stdout);
    } else {
      fprintf(stdout, "[Platina] Reusing local game data after per-file CRC32 verification.\n");
      fflush(stdout);
    }
  }
  if (platinaPrepareOnly) {
    const char *prepareRom = getenv("PLATINA_IMPORTED_ROM");
    if (prepareRom == NULL || prepareRom[0] == '\0') {
      fprintf(stderr, "[Platina] --platina-prepare requires PLATINA_IMPORTED_ROM.\n");
      return 2;
    }
    fprintf(stdout, "[Platina-Progress] ready\n");
    fflush(stdout);
    return 0;
  }
#ifdef SDK_BUILD_NX'''

CONFIG_ALARM_SECOND_ORIGINAL = r'''    if(MATCH("OSNVRAM", "Alarm_Second")) {
        config->osNvramConfig.ncd.alarm.minute = atoi(value);
    }'''
CONFIG_ALARM_SECOND_PATCHED = r'''    if(MATCH("OSNVRAM", "Alarm_Second")) {
        config->osNvramConfig.ncd.alarm.second = atoi(value);
    }'''
CONFIG_SAVE_OPEN_ORIGINAL = '    FILE * configFile = fopen(SIM_CONFIG_FILE_PATH, "w");'

PROJECT_SIM_CONFIG_HANDLER_ORIGINAL = r'''    if(MATCH("Cheats", "RunFromTrainerBattles")) {
        config->runFromTrainerBattles = StringToBool(value);
    }
}'''
PROJECT_SIM_CONFIG_HANDLER_PATCHED = r'''    if(MATCH("Cheats", "RunFromTrainerBattles")) {
        config->runFromTrainerBattles = StringToBool(value);
    }

    // inih uses zero to signal a handler error; ignore unknown keys safely.
    return 1;
}'''
PROJECT_SIM_CONFIG_PARSE_ORIGINAL = '    return (ini_parse(SIM_CONFIG_PRJ_FILE_PATH, IniHandler, aConfig) >= 0);'
PROJECT_SIM_CONFIG_PARSE_PATCHED = '    return (ini_parse(SIM_CONFIG_PRJ_FILE_PATH, IniHandler, aConfig) == 0);'

PROJECT_SIM_CONFIG_INIT_FAILURE_ORIGINAL = r'''  if(!SIM_Config_prj_LoadConfigFile(&s_SIM_config_prj)){
    //Config file does not exist. Save config file with defaults
    SIM_Config_prj_SaveConfigFile(&s_SIM_config_prj);
  }'''
PROJECT_SIM_CONFIG_INIT_FAILURE_PATCHED = r'''  if(!SIM_Config_prj_LoadConfigFile(&s_SIM_config_prj)){
    // Reject partially applied settings after a malformed or unreadable config.
    SIM_Config_prj_LoadDefaults(&s_SIM_config_prj);
    SIM_Config_prj_SaveConfigFile(&s_SIM_config_prj);
  }'''

PROJECT_SIM_CONFIG_SAVE_OPEN_ORIGINAL = '    FILE * configFile = fopen(SIM_CONFIG_PRJ_FILE_PATH, "w");'
PROJECT_SIM_CONFIG_SAVE_OPEN_PATCHED = (
    PROJECT_SIM_CONFIG_SAVE_OPEN_ORIGINAL
    + "\n    if (configFile == NULL) {\n"
      "        fprintf(stderr, \"[Platina] Unable to write simulator configuration file.\\n\");\n"
      "        return;\n"
      "    }"
)
PROJECT_SIM_CONFIG_CLOSE_ORIGINAL = '    fclose(configFile);'
PROJECT_SIM_CONFIG_CLOSE_PATCHED = (
    '    if (fclose(configFile) != 0) {\n'
    '        fprintf(stderr, "[Platina] Failed to flush simulator configuration file.\\n");\n'
    '    }'
)

SDL_INIT_ORIGINAL = r'''  SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_TIMER |
           SDL_INIT_JOYSTICK);
  SIM_Audio_Init(44100);'''
SDL_INIT_PATCHED = r'''  // Video and timing are required; audio and joystick are optional host devices.
  if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) != 0) {
    fprintf(stderr, "SDL video/timer initialization failed: %s\n", SDL_GetError());
    return NULL;
  }
  if (SDL_InitSubSystem(SDL_INIT_JOYSTICK) != 0) {
    fprintf(stderr, "SDL joystick initialization failed; keyboard/mouse input remains available: %s\n",
            SDL_GetError());
  }
  if (SDL_InitSubSystem(SDL_INIT_AUDIO) != 0) {
    fprintf(stderr, "SDL audio initialization failed; the audio layer will try its silent fallback: %s\n",
            SDL_GetError());
  }
  SIM_Audio_Init(44100);'''

SIM_AUDIO_OPEN_ORIGINAL = r'''    s_requestedAudioSpec.callback = SIM_Audio_Callback;
    if(SDL_OpenAudio(&s_requestedAudioSpec, NULL) < 0) {
        printf("SDL Error %s\n", SDL_GetError());
    }
    SDL_PauseAudio(0);'''
SIM_AUDIO_OPEN_PATCHED = r'''    s_requestedAudioSpec.callback = SIM_Audio_Callback;
    if(SDL_OpenAudio(&s_requestedAudioSpec, NULL) < 0) {
        printf("[Platina] SDL audio device failed: %s. Retrying with the silent dummy driver.\n",
               SDL_GetError());
        SDL_AudioQuit();
        if (SDL_AudioInit("dummy") < 0) {
            printf("[Platina] SDL dummy audio initialization failed: %s.\n", SDL_GetError());
            return;
        }
        if (SDL_OpenAudio(&s_requestedAudioSpec, NULL) < 0) {
            printf("[Platina] SDL dummy audio device failed: %s. Audio callback is unavailable.\n",
                   SDL_GetError());
            SDL_AudioQuit();
            return;
        }
        printf("[Platina] Silent SDL dummy audio driver is active; playback is disabled.\n");
    }
    SDL_PauseAudio(0);'''

SDL_SWAP_INTERVAL_SETUP_ORIGINAL = r'''  SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
  SDL_GL_SetSwapInterval(s_SIM_config.vsyncInterval);'''
SDL_SWAP_INTERVAL_SETUP_PATCHED = r'''  SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
  // Apply VSync only after SDL_GL_CreateContext succeeds.'''

SDL_WINDOW_CONTEXT_ORIGINAL = r'''  window = SDL_CreateWindow(
      windowTitle.c_str(), 100, 100, windowWidth, windowHeight,
      SDL_WINDOW_SHOWN | SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE);
  context = SDL_GL_CreateContext(window);'''
SDL_WINDOW_CONTEXT_PATCHED_LEGACY = r'''  window = SDL_CreateWindow(
      windowTitle.c_str(), 100, 100, windowWidth, windowHeight,
      SDL_WINDOW_SHOWN | SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE |
          SDL_WINDOW_ALLOW_HIGHDPI);
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

SDL_WINDOW_CONTEXT_PATCHED = r'''  window = SDL_CreateWindow(
      windowTitle.c_str(), 100, 100, windowWidth, windowHeight,
      SDL_WINDOW_HIDDEN | SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE |
          SDL_WINDOW_ALLOW_HIGHDPI);
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

PLATINA_WINDOW_DECLARATION_ORIGINAL = "static SDL_Window *window;"
PLATINA_WINDOW_DECLARATION_PATCHED_LEGACY = r'''static SDL_Window *window;
static bool sPlatinaFirstFramePresented = false;'''
PLATINA_WINDOW_DECLARATION_PATCHED = r'''static SDL_Window *window;
static bool sPlatinaFirstFramePresented = false;
static struct timespec sPlatinaLastHeartbeat = {};
static unsigned long long sPlatinaPresentedFrameCount = 0;'''

# This exact context occurs in SIM_Render, not the setup swap in SIM_RenderInit.
PLATINA_FIRST_FRAME_HANDOFF_ORIGINAL = (
    "    SDL_GL_SwapWindow(window);\n\n"
    "    if(sChangeInternalResAfterRender) {"
)
PLATINA_FIRST_FRAME_HANDOFF_PATCHED_LEGACY = r'''    SDL_GL_SwapWindow(window);

    // Reveal the native window only after a complete game frame reaches swap.
    if (!sPlatinaFirstFramePresented) {
      SDL_ShowWindow(window);
      sPlatinaFirstFramePresented = true;
      fprintf(stderr, "[Platina-Progress] window-ready\n");
      fflush(stderr);
    }

    if(sChangeInternalResAfterRender) {''';

PLATINA_FIRST_FRAME_HANDOFF_PATCHED = r'''    SDL_GL_SwapWindow(window);

    // Reveal the native window only after a complete game frame reaches swap.
    if (!sPlatinaFirstFramePresented) {
      SDL_ShowWindow(window);
      sPlatinaFirstFramePresented = true;
      fprintf(stderr, "[Platina-Progress] window-ready\n");
      fflush(stderr);
    }

    // Emit a bounded-rate heartbeat only after a completed game-frame swap.
    // It is deliberately independent of UI/event-pump activity and never
    // performs SDL or OpenGL work from another thread.
    ++sPlatinaPresentedFrameCount;
    struct timespec heartbeatNow = {};
    if (clock_gettime(CLOCK_MONOTONIC, &heartbeatNow) == 0) {
      const long long heartbeatElapsedNs =
          ((long long)heartbeatNow.tv_sec - (long long)sPlatinaLastHeartbeat.tv_sec) * 1000000000LL +
          ((long long)heartbeatNow.tv_nsec - (long long)sPlatinaLastHeartbeat.tv_nsec);
      if (sPlatinaPresentedFrameCount == 1ULL || heartbeatElapsedNs >= 5000000000LL) {
        sPlatinaLastHeartbeat = heartbeatNow;
        fprintf(stderr, "[Platina-Progress] heartbeat frame=%llu\n",
                sPlatinaPresentedFrameCount);
        fflush(stderr);
      }
    }

    if(sChangeInternalResAfterRender) {'''


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
  G3SIM_DrawInit();
  fprintf(stderr, "[Platina-Progress] renderer-ready\n");
  fflush(stderr);'''
SDL_VIEWPORT_ORIGINAL = "  glViewport(0, 0, windowWidth, windowHeight);"
SDL_VIEWPORT_PATCHED = r'''  int drawableWidth = 0;
  int drawableHeight = 0;
  SDL_GL_GetDrawableSize(window, &drawableWidth, &drawableHeight);
  if (drawableWidth <= 0 || drawableHeight <= 0) {
    fprintf(stderr, "Invalid OpenGL drawable size: %d x %d\n",
            drawableWidth, drawableHeight);
    SDL_GL_DeleteContext(context);
    SDL_DestroyWindow(window);
    context = NULL;
    window = NULL;
    return NULL;
  }
  glViewport(0, 0, drawableWidth, drawableHeight);'''

INPUT_RELEASE_HELPER_ORIGINAL = "static bool sFastForward = false;"
INPUT_RELEASE_HELPER_PATCHED = r'''// Must be declared before ReleaseDesktopInputState(), which clears it.
static u8 isMouseDown = 0; // Storage is declared before the focus-loss release helper.
static bool sFastForward = false;

// Release every DS button and the touch panel when focus is lost or a
// controller disconnects, so a held key cannot remain stuck in the game.
static void ReleaseDesktopInputState() {
  s_reg_PAD_KEYINPUT = 0x03FF;
  *(vu16 *)HW_BUTTON_XY_BUF = *(vu16 *)HW_BUTTON_XY_BUF | 0b0000110000000000;
  isMouseDown = 0;
  s_tpData.validity = 0;
  s_tpData.touch = 0;
  sFastForward = false;
  if (context != NULL) {
    (void)SDL_GL_SetSwapInterval(s_SIM_config.vsyncInterval);
  }
}'''

WINDOW_EVENT_ORIGINAL = r'''      if (Event.type == SDL_WINDOWEVENT) {
        switch (Event.window.event) {
        case SDL_WINDOWEVENT_CLOSE:
          exit(0);
          break;
        }
      }'''
WINDOW_EVENT_PATCHED = r'''      if (Event.type == SDL_WINDOWEVENT) {
        switch (Event.window.event) {
        case SDL_WINDOWEVENT_CLOSE:
          exit(0);
          break;
        case SDL_WINDOWEVENT_FOCUS_LOST:
          ReleaseDesktopInputState();
          break;
        case SDL_WINDOWEVENT_RESIZED:
        case SDL_WINDOWEVENT_SIZE_CHANGED: {
          int drawableWidth = 0;
          int drawableHeight = 0;
          SDL_GL_GetDrawableSize(window, &drawableWidth, &drawableHeight);
          if (drawableWidth > 0 && drawableHeight > 0) {
            glViewport(0, 0, drawableWidth, drawableHeight);
          } else {
            fprintf(stderr, "Ignoring invalid resized OpenGL drawable: %d x %d\n",
                    drawableWidth, drawableHeight);
          }
          break;
        }
        }
      }'''
KEYDOWN_ORIGINAL = "      if (Event.type == SDL_KEYDOWN) {"
MOUSE_DOWN_DECLARATION_ORIGINAL = "static u8 isMouseDown = 0;";
MOUSE_DOWN_DECLARATION_PATCHED = "// isMouseDown is declared above ReleaseDesktopInputState().";

KEYDOWN_PATCHED = r'''      if (Event.type == SDL_JOYDEVICEREMOVED) {
        if (s_SIM_SDLJoystick != NULL &&
            SDL_JoystickInstanceID(s_SIM_SDLJoystick) == Event.jdevice.which) {
          SDL_JoystickClose(s_SIM_SDLJoystick);
          s_SIM_SDLJoystick = NULL;
          ReleaseDesktopInputState();
          fprintf(stderr, "Controller disconnected; input state released.\n");
        }
      }
      if (Event.type == SDL_KEYDOWN && Event.key.repeat == 0) {'''



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
FS_OPEN_FALLBACK_PATCHED_LEGACY = r'''        const char *managedRomPath = getenv("PLATINA_IMPORTED_ROM");
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
FS_OPEN_FALLBACK_PATCHED = r'''        const char *managedRomPath = getenv("PLATINA_IMPORTED_ROM");
        if (managedRomPath != NULL && managedRomPath[0] != '\0') {
            fprintf(stderr, "[Platina] Required runtime resource is missing after launcher preparation: %s. Close the game and run data preparation again from the launcher. No extraction will be attempted while the game window is open.\n", path);
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

        // Manual desktop launches may still use the legacy extraction flow.
        return FS_OpenFile(p_file, path);'''

FS_LOCALIZATION_HELPERS_PATCHED = r'''static int Platina_LocalizationPathEquals(const char *path, const char *expected) {
    while (*path != '\0' && *expected != '\0') {
        unsigned char pathChar = (unsigned char)*path;
        unsigned char expectedChar = (unsigned char)*expected;
        if (pathChar == '\\') pathChar = '/';
        if (expectedChar == '\\') expectedChar = '/';
        if (tolower(pathChar) != tolower(expectedChar)) return FALSE;
        ++path;
        ++expected;
    }
    return *path == '\0' && *expected == '\0';
}

static const char *Platina_GetLocalizedResourcePath(const char *path) {
    // Keep this exact allowlist synchronized with tools/localization_manifest.py.
    static const char *const allowedResources[] = {
        "battle/graphic/pl_b_plist_gra.narc",
        "data/slot.narc",
        "demo/title/op_demo.narc",
        "graphic/pl_bag_gra.narc",
        "graphic/pl_plist_gra.narc",
        "graphic/pl_pst_gra.narc",
        "msgdata/pl_msg.narc"
    };
    size_t index;
    if (path == NULL) return NULL;
    for (index = 0; index < sizeof(allowedResources) / sizeof(allowedResources[0]); ++index) {
        if (Platina_LocalizationPathEquals(path, allowedResources[index])) {
            return allowedResources[index];
        }
    }
    return NULL;
}'''

FS_LOCALIZATION_OPEN_ORIGINAL = "\tp_file->pcFilePtr = NULL;\n\tp_file->pcFilePtr = fopen(path, \"rb\");"
FS_LOCALIZATION_OPEN_PATCHED = r'''	p_file->pcFilePtr = NULL;
	const char *requestedLocale = getenv("PLATINA_LANGUAGE");
	const char *localizedResourcePath = Platina_GetLocalizedResourcePath(path);
	if (requestedLocale != NULL && strcmp(requestedLocale, "pt-BR") == 0 &&
	    localizedResourcePath != NULL) {
		const char *localizationRoot = getenv("PLATINA_LOCALIZATION_DIR");
		char localizedPath[4096];
		if (localizationRoot == NULL || localizationRoot[0] == '\0') {
			fprintf(stderr, "[Platina][localization] PT-BR is selected but its package path is not configured: %s\n",
			        localizedResourcePath);
			return FALSE;
		}
		const int localizedPathLength = snprintf(
		    localizedPath, sizeof(localizedPath), "%s/%s",
		    localizationRoot, localizedResourcePath);
		if (localizedPathLength < 0 ||
		    (size_t)localizedPathLength >= sizeof(localizedPath)) {
			fprintf(stderr, "[Platina][localization] PT-BR resource path is too long: %s\n",
			        localizedResourcePath);
			return FALSE;
		}
		p_file->pcFilePtr = fopen(localizedPath, "rb");
		if (p_file->pcFilePtr == NULL) {
			fprintf(stderr, "[Platina][localization] Required PT-BR resource is missing or unreadable: %s\n",
			        localizedResourcePath);
			return FALSE;
		}
	} else {
		p_file->pcFilePtr = fopen(path, "rb");
	}'''

METROSKREW_DOWNLOAD_ORIGINAL = "wget --quiet --show-progress -O \"$SKREW_ARC\" \"$SKREW_URL\""
METROSKREW_DOWNLOAD_PATCHED = r'''# Use bounded retries and a second HTTP client for transient GitHub release failures.
# Download to a temporary name so a partial response is never treated as an archive.
download_archive="$SKREW_ARC.part"
rm -f -- "$download_archive"
if ! wget --quiet --show-progress --tries=5 --retry-connrefused --waitretry=2 --timeout=30 \
    -O "$download_archive" "$SKREW_URL"; then
    echo "metroskrew: wget failed; retrying the pinned release with curl." >&2
    rm -f -- "$download_archive"
    if ! command -v curl >/dev/null 2>&1; then
        echo "metroskrew: neither the wget nor curl download completed." >&2
        exit 1
    fi
    if ! curl --fail --location --silent --show-error --retry 5 --retry-all-errors \
        --retry-delay 2 --connect-timeout 30 --output "$download_archive" "$SKREW_URL"; then
        rm -f -- "$download_archive"
        echo "metroskrew: failed to download the pinned release after retries." >&2
        exit 1
    fi
fi
if [[ ! -s "$download_archive" ]]; then
    rm -f -- "$download_archive"
    echo "metroskrew: downloaded archive is empty." >&2
    exit 1
fi
mv -f -- "$download_archive" "$SKREW_ARC"'''

SHADER_LOG_LENGTH_QUERY_ORIGINAL = "glGetShaderiv(g2FragmentShader, GL_INFO_LOG_LENGTH, &logSize);"
SHADER_LOG_LENGTH_QUERY_PATCHED = "glGetShaderiv(_id, GL_INFO_LOG_LENGTH, &logSize);"

NDS_EXTRACTOR_INPUT_CHECK_ORIGINAL = r'''	unsigned ndsFileSize = fs::file_size(ndsInputPath);

	if (!fs::exists(ndsInputPath) || !fs::is_regular_file(ndsInputPath)) {
		std::cout << DERROR << "NDS input file " << ndsInputPath.string() << " is not a valid file" << std::endl;
		return -1;
	}

	if (ndsFileSize > oneGB) {
		std::cout << DERROR << "NDS input file " << ndsInputPath.string() << " is larger than 1GB" << std::endl;
		return -1;
	}'''
NDS_EXTRACTOR_INPUT_CHECK_PATCHED = r'''	std::error_code inputError;
	const auto inputStatus = fs::status(ndsInputPath, inputError);
	if (inputError || !fs::is_regular_file(inputStatus)) {
		std::cout << DERROR << "NDS input file " << ndsInputPath.string() << " is not a valid regular file" << std::endl;
		return -1;
	}

	const auto ndsFileSizeValue = fs::file_size(ndsInputPath, inputError);
	if (inputError) {
		std::cout << DERROR << "Could not read NDS input file size for " << ndsInputPath.string()
		          << ": " << inputError.message() << std::endl;
		return -1;
	}
	if (ndsFileSizeValue > oneGB) {
		std::cout << DERROR << "NDS input file " << ndsInputPath.string() << " is larger than 1GB" << std::endl;
		return -1;
	}
	const unsigned ndsFileSize = static_cast<unsigned>(ndsFileSizeValue);'''


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
        std::fprintf(stderr, "[rom-extract] Refusing synchronous extraction from an imported ROM while the game is running. Close the game and prepare data again from the launcher.\n");
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

NVRAM_FILE_READ_ORIGINAL = r'''#else
    if(s_nvramFilePtr == NULL) {
        s_nvramFilePtr = fopen(NVRAM_FILE_PATH, "rb+");
    }

    fseek(s_nvramFilePtr, address, SEEK_SET);
    fread(buf, 1, size, s_nvramFilePtr);
    fclose(s_nvramFilePtr);
    s_nvramFilePtr = NULL;
#endif'''
NVRAM_FILE_READ_PATCHED = r'''#else
    // firmware.bin is a local NVRAM backing file, not a ROM-extracted asset.
    // A first run has no backing file yet: emulate erased flash for reads.
    if (s_nvramFilePtr == NULL) {
        s_nvramFilePtr = fopen(NVRAM_FILE_PATH, "rb");
    }
    if (s_nvramFilePtr == NULL) {
        for (i = 0; i < (s32)size; i++) {
            buf[i] = 0xFF;
        }
        static int nvramFallbackWarned = 0;
        if (!nvramFallbackWarned) {
            fprintf(stderr, "[Platina] NVRAM backing file is unavailable; using erased flash bytes for this read.\n");
            nvramFallbackWarned = 1;
        }
        return;
    }
    if (fseek(s_nvramFilePtr, (long)address, SEEK_SET) != 0) {
        for (i = 0; i < (s32)size; i++) {
            buf[i] = 0xFF;
        }
        fprintf(stderr, "[Platina] NVRAM backing read seek failed; using erased flash bytes.\n");
        fclose(s_nvramFilePtr);
        s_nvramFilePtr = NULL;
        return;
    }
    {
        size_t bytesRead = fread(buf, 1, size, s_nvramFilePtr);
        if (bytesRead < size) {
            for (i = (s32)bytesRead; i < (s32)size; i++) {
                buf[i] = 0xFF;
            }
            if (ferror(s_nvramFilePtr)) {
                fprintf(stderr, "[Platina] NVRAM backing read was incomplete; the missing bytes were treated as erased flash.\n");
            }
        }
    }
    fclose(s_nvramFilePtr);
    s_nvramFilePtr = NULL;
#endif'''


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

CARD_IDENTIFY_BACKUP_ORIGINAL = """ \tCARDi_BeginBackupCommand(CARD_ACCESS_LEVEL_NONE, NULL, NULL);\n\n \tCARDi_IdentifyBackupCore2(type);\n\n \treturn CARDi_ExecuteOldTypeTask(CARDi_IdentifyBackupCore, FALSE);"""
CARD_IDENTIFY_BACKUP_PATCHED = """  CARDi_BeginBackupCommand(CARD_ACCESS_LEVEL_NONE, NULL, NULL);\n\n  // Desktop Platinum uses the launcher's file-backed save implementation.\n  // The SDK_PORT simulator does not provide an ARM7 card/PXI peer, so asking\n  // the emulated cartridge to identify its backup chip would block forever.\n  // Populate the same backup geometry locally and finish the normal task.\n  CARDi_IdentifyBackupCore2(type);\n#ifdef SDK_PORT\n  const BOOL supported = (cardi_common.cmd->type == type);\n  cardi_common.cmd->result = supported ? CARD_RESULT_SUCCESS : CARD_RESULT_UNSUPPORTED;\n  CARDi_EndTask(&cardi_common);\n  return supported;\n#else\n  return CARDi_ExecuteOldTypeTask(CARDi_IdentifyBackupCore, FALSE);\n#endif"""

CONFIG_SAVE_OPEN_PATCHED = (
    CONFIG_SAVE_OPEN_ORIGINAL
    + "\n    if (configFile == NULL) {\n        return;\n    }"
)


class RuntimePreparationError(RuntimeError):
    pass


def _prepare_renderer_startup(source: str) -> tuple[str, bool]:
    """Fail cleanly when SDL or the desktop OpenGL loader cannot initialize."""
    current = source
    # Move the upstream declaration before inserting a helper that references it.
    hasMovedComment = current.count(MOUSE_DOWN_DECLARATION_PATCHED) == 1
    if current.count(MOUSE_DOWN_DECLARATION_PATCHED) > 1:
        raise RuntimePreparationError("Duplicate moved desktop mouse-state declaration.")
    standalone_old_count = sum(
        line.strip() == MOUSE_DOWN_DECLARATION_ORIGINAL
        for line in current.splitlines()
    )
    if hasMovedComment:
        if standalone_old_count != 0:
            raise RuntimePreparationError("Both old and moved desktop mouse-state declarations remain.")
    elif standalone_old_count == 1:
        current = current.replace(
            MOUSE_DOWN_DECLARATION_ORIGINAL,
            MOUSE_DOWN_DECLARATION_PATCHED,
            1,
        )
    elif standalone_old_count > 1:
        raise RuntimePreparationError("Duplicate upstream mouse-state declarations detected.")
    legacy_blocks = (
        (SDL_WINDOW_CONTEXT_PATCHED_LEGACY, SDL_WINDOW_CONTEXT_PATCHED, "hidden SDL startup window"),
        (PLATINA_WINDOW_DECLARATION_PATCHED_LEGACY, PLATINA_WINDOW_DECLARATION_PATCHED, "heartbeat state"),
        (PLATINA_FIRST_FRAME_HANDOFF_PATCHED_LEGACY, PLATINA_FIRST_FRAME_HANDOFF_PATCHED, "heartbeat frame handoff"),
    )
    for legacy, current_patch, label in legacy_blocks:
        if legacy in current:
            if current.count(legacy) != 1 or current_patch in current:
                raise RuntimePreparationError(f"Ambiguous previous {label} patch; refusing an uncertain upgrade.")
            current = current.replace(legacy, current_patch, 1)

    blocks = (
        (
            PLATINA_WINDOW_DECLARATION_ORIGINAL,
            PLATINA_WINDOW_DECLARATION_PATCHED,
            "first-frame presentation state",
        ),
        (
            SDL_SWAP_INTERVAL_SETUP_ORIGINAL,
            SDL_SWAP_INTERVAL_SETUP_PATCHED,
            "defer swap interval until a context exists",
        ),
        (SDL_INIT_ORIGINAL, SDL_INIT_PATCHED, "SDL_Init result check"),
        (SDL_WINDOW_CONTEXT_ORIGINAL, SDL_WINDOW_CONTEXT_PATCHED, "SDL window/context checks"),
        (GL_LOADER_ORIGINAL, GL_LOADER_PATCHED, "desktop OpenGL loader check"),
        (MAIN_RENDER_HANDOFF_ORIGINAL, MAIN_RENDER_HANDOFF_PATCHED, "renderer startup handoff check"),
        (
            PLATINA_FIRST_FRAME_HANDOFF_ORIGINAL,
            PLATINA_FIRST_FRAME_HANDOFF_PATCHED,
            "first game frame presentation handoff",
        ),
        (SDL_VIEWPORT_ORIGINAL, SDL_VIEWPORT_PATCHED, "high-DPI OpenGL viewport"),
        (INPUT_RELEASE_HELPER_ORIGINAL, INPUT_RELEASE_HELPER_PATCHED, "desktop input release helper"),
        (WINDOW_EVENT_ORIGINAL, WINDOW_EVENT_PATCHED, "focus-loss and resize event handling"),
        (KEYDOWN_ORIGINAL, KEYDOWN_PATCHED, "keyboard key-repeat and controller-disconnect handling"),
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



def _prepare_card_backup_identification(source_root: str | Path) -> tuple[Path, str, bool]:
    """Avoid a desktop boot deadlock waiting for a nonexistent ARM7 card peer."""
    source_path = (
        Path(source_root).expanduser().resolve()
        / "subprojects" / "libntr" / "libraries" / "card" / "src" / "card_backup.c"
    )
    if not source_path.is_file():
        raise RuntimePreparationError(f"Card backup implementation missing: {source_path}")

    original = source_path.read_text(encoding="utf-8")
    current = original
    if CARD_IDENTIFY_BACKUP_PATCHED in current:
        if current.count(CARD_IDENTIFY_BACKUP_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate SDK_PORT card-identification patch detected.")
        if CARD_IDENTIFY_BACKUP_ORIGINAL in current:
            raise RuntimePreparationError("Both original and patched card-identification paths exist.")
        return source_path, current, False

    if current.count(CARD_IDENTIFY_BACKUP_ORIGINAL) != 1:
        raise RuntimePreparationError(
            "Expected exactly one known SDK v5 card-identification path; refusing an uncertain patch."
        )
    current = current.replace(CARD_IDENTIFY_BACKUP_ORIGINAL, CARD_IDENTIFY_BACKUP_PATCHED, 1)
    if current.count(CARD_IDENTIFY_BACKUP_PATCHED) != 1:
        raise RuntimePreparationError("SDK_PORT card-identification patch was not installed exactly once.")
    return source_path, current, current != original


def _prepare_fs_missing_resource_fallback(source_root: str | Path) -> tuple[Path, str, bool]:
    """Apply safe missing-resource handling and the allowlisted localization overlay."""
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
        if FS_OPEN_FALLBACK_ORIGINAL in current or FS_OPEN_FALLBACK_PATCHED_LEGACY in current:
            raise RuntimePreparationError("Multiple ROM-extraction fallback implementations exist in fs_file.c.")
    elif FS_OPEN_FALLBACK_PATCHED_LEGACY in current:
        if current.count(FS_OPEN_FALLBACK_PATCHED_LEGACY) != 1:
            raise RuntimePreparationError("Duplicate legacy launcher-managed fallback in fs_file.c.")
        current = current.replace(FS_OPEN_FALLBACK_PATCHED_LEGACY, FS_OPEN_FALLBACK_PATCHED, 1)
    else:
        if current.count(FS_OPEN_FALLBACK_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected exactly one known ROM-extraction fallback in fs_file.c; refusing uncertain patch."
            )
        current = current.replace(FS_OPEN_FALLBACK_ORIGINAL, FS_OPEN_FALLBACK_PATCHED, 1)

    original_include = "#include <string.h>\n#include <SDL2/SDL.h>"
    legacy_include = (
        "#include <string.h>\n#include <stdlib.h>\n#include <stdio.h>\n#include <SDL2/SDL.h>\n"
        "static BOOL sLauncherManagedRomExtractionAttempted = FALSE;"
    )
    previous_patched_include = (
        "#include <string.h>\n#include <stdlib.h>\n#include <stdio.h>\n#include <SDL2/SDL.h>"
    )
    patched_include = previous_patched_include + "\n#include <ctype.h>"

    # Upgrade earlier launcher patches as well as untouched pinned upstream source.
    if legacy_include in current:
        if current.count(legacy_include) != 1:
            raise RuntimePreparationError("Duplicate legacy extraction-state declaration in fs_file.c.")
        current = current.replace(legacy_include, patched_include, 1)
    elif patched_include in current:
        if current.count(patched_include) != 1:
            raise RuntimePreparationError("Duplicate SDK_PORT include block in fs_file.c.")
    elif previous_patched_include in current:
        if current.count(previous_patched_include) != 1:
            raise RuntimePreparationError("Duplicate previous SDK_PORT include block in fs_file.c.")
        current = current.replace(previous_patched_include, patched_include, 1)
    else:
        if current.count(original_include) != 1:
            raise RuntimePreparationError("Expected exactly one SDK_PORT include block in fs_file.c.")
        current = current.replace(original_include, patched_include, 1)

    if "sLauncherManagedRomExtractionAttempted" in current:
        raise RuntimePreparationError("Obsolete synchronous extraction state remains in fs_file.c.")

    if FS_LOCALIZATION_HELPERS_PATCHED in current:
        if current.count(FS_LOCALIZATION_HELPERS_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate PT-BR localization helper block in fs_file.c.")
    else:
        if current.count(patched_include) != 1:
            raise RuntimePreparationError("Cannot install the PT-BR helpers without a unique SDK_PORT include block.")
        current = current.replace(
            patched_include,
            patched_include + "\n\n" + FS_LOCALIZATION_HELPERS_PATCHED,
            1,
        )

    if FS_LOCALIZATION_OPEN_PATCHED in current:
        if current.count(FS_LOCALIZATION_OPEN_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate PT-BR localized file-open path in fs_file.c.")
        if FS_LOCALIZATION_OPEN_ORIGINAL in current:
            raise RuntimePreparationError("Both original and localized file-open paths exist in fs_file.c.")
    else:
        if current.count(FS_LOCALIZATION_OPEN_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected exactly one known SDK_PORT file-open call for localization; refusing an uncertain patch."
            )
        current = current.replace(FS_LOCALIZATION_OPEN_ORIGINAL, FS_LOCALIZATION_OPEN_PATCHED, 1)

    return fs_path, current, current != original

def _prepare_metroskrew_downloader(source_root: str | Path) -> tuple[Path, str, bool]:
    """Retry the pinned metroskrew release download and fail clearly on network errors."""
    helper_path = (
        Path(source_root).expanduser().resolve()
        / "tools" / "devtools" / "get_metroskrew.sh"
    )
    if not helper_path.is_file():
        raise RuntimePreparationError(f"Metroskrew download helper missing: {helper_path}")

    original = helper_path.read_text(encoding="utf-8")
    current = original
    if METROSKREW_DOWNLOAD_PATCHED in current:
        if current.count(METROSKREW_DOWNLOAD_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate metroskrew download retry patch detected.")
        if METROSKREW_DOWNLOAD_ORIGINAL in current:
            raise RuntimePreparationError("Both original and retry-enabled metroskrew download commands exist.")
    else:
        if current.count(METROSKREW_DOWNLOAD_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected exactly one pinned metroskrew download command; refusing an uncertain patch."
            )
        current = current.replace(METROSKREW_DOWNLOAD_ORIGINAL, METROSKREW_DOWNLOAD_PATCHED, 1)

    if "SKREW_URL" not in current or "metroskrew-$SKREW_SYS$SKREW_EXT" not in current:
        raise RuntimePreparationError("Metroskrew release identity or platform selection changed unexpectedly.")
    return helper_path, current, current != original


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


def _prepare_shader_log_query(source: str) -> tuple[str, bool]:
    """Query the info-log length for the shader currently being compiled."""
    current = source
    if SHADER_LOG_LENGTH_QUERY_PATCHED in current:
        if current.count(SHADER_LOG_LENGTH_QUERY_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate shader info-log query patch detected.")
        if SHADER_LOG_LENGTH_QUERY_ORIGINAL in current:
            raise RuntimePreparationError("Both original and patched shader info-log queries exist.")
    else:
        if current.count(SHADER_LOG_LENGTH_QUERY_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected exactly one recognized shader info-log query; refusing an uncertain patch."
            )
        current = current.replace(
            SHADER_LOG_LENGTH_QUERY_ORIGINAL,
            SHADER_LOG_LENGTH_QUERY_PATCHED,
            1,
        )
    return current, current != source


def _prepare_nds_extractor(source_root: str | Path) -> tuple[Path, str, bool]:
    """Validate the input image before querying its size; avoid filesystem exceptions."""
    extractor_path = (
        Path(source_root).expanduser().resolve()
        / "subprojects" / "libntr" / "libraries" / "sim" / "src"
        / "fireflower" / "nds-extract.cpp"
    )
    if not extractor_path.is_file():
        raise RuntimePreparationError(f"NDS extractor source missing: {extractor_path}")

    original = extractor_path.read_text(encoding="utf-8")
    if NDS_EXTRACTOR_INPUT_CHECK_PATCHED in original:
        if original.count(NDS_EXTRACTOR_INPUT_CHECK_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate safe NDS input preflight patch detected.")
        if NDS_EXTRACTOR_INPUT_CHECK_ORIGINAL in original:
            raise RuntimePreparationError("Both original and patched NDS input preflight blocks exist.")
        return extractor_path, original, False

    if original.count(NDS_EXTRACTOR_INPUT_CHECK_ORIGINAL) != 1:
        raise RuntimePreparationError(
            "Expected exactly one known NDS extractor input preflight; refusing uncertain patch."
        )
    updated = original.replace(
        NDS_EXTRACTOR_INPUT_CHECK_ORIGINAL,
        NDS_EXTRACTOR_INPUT_CHECK_PATCHED,
        1,
    )
    if updated.count(NDS_EXTRACTOR_INPUT_CHECK_PATCHED) != 1:
        raise RuntimePreparationError("Safe NDS input preflight was not installed exactly once.")
    return extractor_path, updated, updated != original


def _prepare_sim_audio(source_root: str | Path) -> tuple[Path, str, bool]:
    """Keep the game audio callback alive by falling back to SDL's silent driver."""
    source_path = (
        Path(source_root).expanduser().resolve()
        / "subprojects" / "libntr" / "libraries" / "sim" / "src" / "sim_audio.cpp"
    )
    if not source_path.is_file():
        raise RuntimePreparationError(f"Simulator audio source missing: {source_path}")

    original = source_path.read_text(encoding="utf-8")
    current = original
    if SIM_AUDIO_OPEN_PATCHED in current:
        if current.count(SIM_AUDIO_OPEN_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate SDL audio fallback patch detected.")
        if SIM_AUDIO_OPEN_ORIGINAL in current:
            raise RuntimePreparationError("Both original and patched SDL audio open blocks exist.")
    else:
        if current.count(SIM_AUDIO_OPEN_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected exactly one known SDL audio-open block; refusing an uncertain patch."
            )
        current = current.replace(SIM_AUDIO_OPEN_ORIGINAL, SIM_AUDIO_OPEN_PATCHED, 1)
    return source_path, current, current != original


def _prepare_nvram_file_backing(source_root: str | Path) -> tuple[Path, str, bool]:
    """Prevent missing/corrupt optional local NVRAM backing from crashing the native port."""
    source_path = (
        Path(source_root).expanduser().resolve()
        / "subprojects" / "libntr" / "libraries" / "sim7" / "src" / "spi" / "nvram"
        / "nvram_instruction.c"
    )
    if not source_path.is_file():
        raise RuntimePreparationError(f"Simulator NVRAM source missing: {source_path}")

    original = source_path.read_text(encoding="utf-8")
    current = original
    if NVRAM_FILE_READ_PATCHED in current:
        if current.count(NVRAM_FILE_READ_PATCHED) != 1:
            raise RuntimePreparationError("Duplicate NVRAM backing fallback patch detected.")
        if NVRAM_FILE_READ_ORIGINAL in current:
            raise RuntimePreparationError("Both original and patched NVRAM backing reads exist.")
    else:
        if current.count(NVRAM_FILE_READ_ORIGINAL) != 1:
            raise RuntimePreparationError(
                "Expected exactly one known NVRAM file-backed read block; refusing an uncertain patch."
            )
        current = current.replace(NVRAM_FILE_READ_ORIGINAL, NVRAM_FILE_READ_PATCHED, 1)

    return source_path, current, current != original



def _prepare_project_sim_config(source_root: str | Path) -> tuple[Path, str, bool]:
    """Harden the project-specific INI callback and configuration persistence."""
    source_path = Path(source_root).expanduser().resolve() / "src" / "port" / "sim_config_prj.c"
    if not source_path.is_file():
        raise RuntimePreparationError(f"Project simulator config source missing: {source_path}")

    original = source_path.read_text(encoding="utf-8")
    current = original

    patches = (
        (
            PROJECT_SIM_CONFIG_HANDLER_ORIGINAL,
            PROJECT_SIM_CONFIG_HANDLER_PATCHED,
            "project INI callback return contract",
        ),
        (
            PROJECT_SIM_CONFIG_PARSE_ORIGINAL,
            PROJECT_SIM_CONFIG_PARSE_PATCHED,
            "project INI parse-result handling",
        ),
        (
            PROJECT_SIM_CONFIG_INIT_FAILURE_ORIGINAL,
            PROJECT_SIM_CONFIG_INIT_FAILURE_PATCHED,
            "project configuration defaults after parse failure",
        ),
        (
            PROJECT_SIM_CONFIG_SAVE_OPEN_ORIGINAL,
            PROJECT_SIM_CONFIG_SAVE_OPEN_PATCHED,
            "project configuration fopen guard",
        ),
        (
            PROJECT_SIM_CONFIG_CLOSE_ORIGINAL,
            PROJECT_SIM_CONFIG_CLOSE_PATCHED,
            "project configuration close check",
        ),
    )
    for upstream, patched, label in patches:
        patched_count = current.count(patched)
        upstream_count = current.count(upstream)
        if patched_count == 1:
            # The fopen guard intentionally retains the original fopen line.
            expected_overlap = 1 if patched.startswith(upstream) else 0
            if upstream_count != expected_overlap:
                raise RuntimePreparationError(
                    f"Conflicting upstream and patched markers for {label}; refusing an uncertain patch."
                )
            continue
        if patched_count != 0 or upstream_count != 1:
            raise RuntimePreparationError(
                f"Expected exactly one recognized upstream marker for {label}; refusing an uncertain patch."
            )
        current = current.replace(upstream, patched, 1)

    return source_path, current, current != original



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

    current, _ = _prepare_shader_log_query(current)
    current, _ = _prepare_renderer_startup(current)
    current, _ = _prepare_rom_preflight(current)

    # Validate every source file before writing any of them.
    config_path = path.parent / "config" / "sim_config.c"
    config_updated, config_changed = _prepare_sim_config(config_path)
    project_config_path, project_config_updated, project_config_changed = _prepare_project_sim_config(source_root)
    fs_path, fs_updated, fs_changed = _prepare_fs_missing_resource_fallback(source_root)
    extractor_path, extractor_updated, extractor_changed = _prepare_sim_rom_extractor(source_root)
    nds_extractor_path, nds_extractor_updated, nds_extractor_changed = _prepare_nds_extractor(source_root)
    backup_path, backup_updated, backup_changed = _prepare_backup_save_path(source_root)
    card_path, card_updated, card_changed = _prepare_card_backup_identification(source_root)
    audio_path, audio_updated, audio_changed = _prepare_sim_audio(source_root)
    nvram_path, nvram_updated, nvram_changed = _prepare_nvram_file_backing(source_root)
    metroskrew_path, metroskrew_updated, metroskrew_changed = _prepare_metroskrew_downloader(source_root)

    changed = (
        current != original or config_changed or project_config_changed or fs_changed or extractor_changed or nds_extractor_changed
        or backup_changed or card_changed or audio_changed or nvram_changed or metroskrew_changed
    )
    if current != original:
        path.write_text(current, encoding="utf-8")
    if config_changed:
        config_path.write_text(config_updated, encoding="utf-8")
    if project_config_changed:
        project_config_path.write_text(project_config_updated, encoding="utf-8")
    if fs_changed:
        fs_path.write_text(fs_updated, encoding="utf-8")
    if extractor_changed:
        extractor_path.write_text(extractor_updated, encoding="utf-8")
    if nds_extractor_changed:
        nds_extractor_path.write_text(nds_extractor_updated, encoding="utf-8")
    if backup_changed:
        backup_path.write_text(backup_updated, encoding="utf-8")
    if card_changed:
        card_path.write_text(card_updated, encoding="utf-8")
    if audio_changed:
        audio_path.write_text(audio_updated, encoding="utf-8")
    if nvram_changed:
        nvram_path.write_text(nvram_updated, encoding="utf-8")
    if metroskrew_changed:
        # This helper is executed by Bash under MSYS2 on Windows. Preserve LF
        # endings so Python's Windows newline translation cannot append CR bytes.
        with metroskrew_path.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(metroskrew_updated)
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
