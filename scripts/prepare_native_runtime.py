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

PATCHED_HEADER_LOAD = r'''  // Prefer the ROM selected in the launcher for the cartridge header.
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


class RuntimePreparationError(RuntimeError):
    pass


def prepare_native_runtime(source_root: str | Path) -> bool:
    """Read the first 0x160 bytes of PLATINA_IMPORTED_ROM with a header.bin fallback."""
    path = (Path(source_root).expanduser().resolve() / "subprojects" / "libntr"
            / "libraries" / "sim" / "src" / "sim_main.cpp")
    if not path.is_file():
        raise RuntimePreparationError(f"Simulator source missing: {path}")

    original = path.read_text(encoding="utf-8")
    patched_count = original.count(PATCHED_HEADER_LOAD)
    if patched_count == 1:
        return False
    if patched_count != 0 or original.count(ORIGINAL_HEADER_LOAD) != 1:
        raise RuntimePreparationError(
            "Expected exactly one upstream header.bin loader in sim_main.cpp; refusing an uncertain patch."
        )

    path.write_text(original.replace(ORIGINAL_HEADER_LOAD, PATCHED_HEADER_LOAD, 1), encoding="utf-8")
    return True


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
