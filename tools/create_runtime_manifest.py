#!/usr/bin/env python3
"""Create a deterministic size manifest for a packaged native game runtime."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


class RuntimeManifestError(RuntimeError):
    """Raised when runtime contents cannot be represented safely."""


def create_runtime_manifest(runtime_dir: str | Path) -> Path:
    root = Path(runtime_dir).expanduser().absolute()
    if root.is_symlink():
        raise RuntimeManifestError(f"Runtime directory must not be a symlink: {root}")
    if not root.is_dir():
        raise RuntimeManifestError(f"Runtime directory does not exist: {root}")

    manifest_path = root / "runtime-manifest.txt"
    entries: list[str] = []
    for item in sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()):
        if item == manifest_path:
            continue
        if item.is_symlink():
            raise RuntimeManifestError(f"Symlinks are not allowed in the runtime: {item.relative_to(root)}")
        if item.is_dir():
            continue
        if not item.is_file():
            raise RuntimeManifestError(f"Unsupported runtime entry: {item.relative_to(root)}")

        relative = item.relative_to(root).as_posix()
        if not relative or any(character in relative for character in ("\t", "\r", "\n", "\0")):
            raise RuntimeManifestError(f"Unsafe runtime path: {relative!r}")
        size = item.stat().st_size
        entries.append(f"{relative}\t{size}")

    if not entries:
        raise RuntimeManifestError(f"Runtime directory contains no files: {root}")

    # Write outside the runtime tree so a crash cannot be mistaken for a game
    # asset by a later manifest generation.
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{root.name}.runtime-manifest.",
        suffix=".tmp",
        dir=root.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(entries) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, manifest_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", required=True, help="Runtime data directory to index.")
    args = parser.parse_args(argv)
    try:
        manifest = create_runtime_manifest(args.runtime_dir)
    except (OSError, RuntimeManifestError) as exc:
        print(f"Runtime manifest generation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"manifest": str(manifest), "status": "created"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
