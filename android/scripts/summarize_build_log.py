#!/usr/bin/env python3
"""Surface the first real errors of a huge verbose native build log.

The Android cross-build runs ``meson compile --verbose``, which produces tens
of thousands of lines. When it fails, GitHub only annotates "exit code 1", so
the actual compiler/linker error is buried. This helper scans the saved log and
prints a handful of GitHub Actions ``::error`` annotations (which are readable
from the Checks API as well as the run page). It never fails the job itself.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# "FAILED:" marks the first failing ninja edge; the others are the diagnostics
# produced by Clang, lld, Meson and the assembler.
ERROR_RE = re.compile(
    r"(\bFAILED:|\berror:|\bfatal error:|\bERROR:|undefined (?:reference|symbol)|"
    r"ninja: build stopped|\bld\.lld: error)"
)
MAX_ANNOTATIONS = 10  # GitHub shows at most 10 annotations per step.
MAX_LINE = 400


def escape_workflow_data(text: str) -> str:
    """Escape annotation message data as GitHub Actions expects."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def find_errors(lines: list[str], limit: int = MAX_ANNOTATIONS) -> list[tuple[int, str]]:
    """Return up to ``limit`` distinct (line_number, text) error lines, in log order."""
    found: list[tuple[int, str]] = []
    seen: set[str] = set()
    for number, raw in enumerate(lines, 1):
        text = ANSI_RE.sub("", raw).strip()
        if not text or not ERROR_RE.search(text):
            continue
        text = text[:MAX_LINE]
        if text in seen:
            continue
        seen.add(text)
        found.append((number, text))
        if len(found) >= limit:
            break
    return found


def render_annotations(errors: list[tuple[int, str]]) -> list[str]:
    return [
        f"::error title=Native build error (log line {number})::{escape_workflow_data(text)}"
        for number, text in errors
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="saved verbose build log")
    args = parser.parse_args(argv)

    if not args.log.is_file():
        print(f"No build log found at {args.log}; nothing to summarize.")
        return 0
    lines = args.log.read_text(encoding="utf-8", errors="replace").splitlines()
    errors = find_errors(lines)
    if not errors:
        print(f"No recognizable error lines in {args.log} ({len(lines)} lines).")
        return 0
    for annotation in render_annotations(errors):
        print(annotation)
    return 0


if __name__ == "__main__":
    sys.exit(main())
