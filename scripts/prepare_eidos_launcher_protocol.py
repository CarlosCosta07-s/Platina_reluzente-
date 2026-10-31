#!/usr/bin/env python3
"""Prepare pinned Eidos source for the unified launcher's first-frame protocol.

The first-frame signal is emitted only after the presenter returns from
SDL_RenderPresent/SDL_GL_SwapWindow. This is source patching, not a game build.
"""
from __future__ import annotations
import argparse
from pathlib import Path

MARKER = "PLATINA_LAUNCH_PROTOCOL_V1"
ANCHOR = "    p->presented = 1;\n    render(p);\n"
PATCHED_BLOCK = """    p->presented = 1;
    render(p);
    /* PLATINA_LAUNCH_PROTOCOL_V1: signal only after a frame was presented. */
    {
        static int launcher_first_frame_reported;
        static Uint64 launcher_last_heartbeat_ms;
        static Uint64 launcher_frame_number;
        const Uint64 launcher_now_ms = SDL_GetTicks();

        launcher_frame_number++;
        if (!launcher_first_frame_reported) {
            launcher_first_frame_reported = 1;
            launcher_last_heartbeat_ms = launcher_now_ms;
            fprintf(stderr, "[Platina-Progress] window-ready\\n");
            fflush(stderr);
        } else if (launcher_now_ms - launcher_last_heartbeat_ms >= 5000) {
            launcher_last_heartbeat_ms = launcher_now_ms;
            fprintf(stderr, "[Platina-Progress] heartbeat frame=%llu\\n",
                    (unsigned long long)launcher_frame_number);
            fflush(stderr);
        }
    }
"""

def prepare_eidos_launcher_protocol(source_dir: str | Path) -> bool:
    """Apply the protocol and return True only when the source changed."""
    root = Path(source_dir).resolve()
    source_file = root / "engine" / "platform" / "platform.c"
    if not source_file.is_file() or source_file.is_symlink():
        raise FileNotFoundError(f"Eidos platform source is missing or unsafe: {source_file}")
    text = source_file.read_text(encoding="utf-8")
    if MARKER in text:
        if text.count(MARKER) != 1:
            raise RuntimeError("Eidos launcher protocol marker appears more than once.")
        if text.count("[Platina-Progress] window-ready") != 1:
            raise RuntimeError("Existing Eidos launcher protocol is incomplete.")
        if text.count("[Platina-Progress] heartbeat frame=%llu") != 1:
            raise RuntimeError("Existing Eidos heartbeat protocol is incomplete.")
        return False
    if text.count(ANCHOR) != 1:
        raise RuntimeError("Expected exactly one Eidos presenter handoff anchor; refusing an ambiguous patch.")
    if "#include <SDL3/SDL.h>" not in text or "#include <stdio.h>" not in text:
        raise RuntimeError("Eidos presenter source lacks SDL3/stdio declarations required by the protocol.")
    patched = text.replace(ANCHOR, PATCHED_BLOCK, 1)
    if patched.count(MARKER) != 1:
        raise RuntimeError("Failed to apply the Eidos launcher protocol exactly once.")
    source_file.write_text(patched, encoding="utf-8", newline="\n")
    return True

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, help="Root of the pinned Eidos source checkout.")
    args = parser.parse_args()
    changed = prepare_eidos_launcher_protocol(args.source_dir)
    print("Eidos launcher protocol " + ("prepared." if changed else "already present; unchanged."))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
