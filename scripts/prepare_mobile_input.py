#!/usr/bin/env python3
"""Apply the reviewed SDL touch-router patch to the exact pinned libntr source."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


PINNED_LIBNTR_REVISION = "1555d911ac80c0190ac1c321f99f1323de8b3c09"
SOURCE_RELATIVE_PATH = Path("libraries/sim/src/sim_main.cpp")
HEADER_RELATIVE_PATH = Path("libraries/sim/src/touch_input_router.hpp")
OVERLAY_HEADER_RELATIVE_PATH = Path("libraries/sim/src/virtual_touch_controls.hpp")
PATCH_RELATIVE_PATH = Path(
    "mobile/input/patches/libntr-1555d911-touch-router.patch"
)
HEADER_SOURCE_RELATIVE_PATH = Path("mobile/input/touch_input_router.hpp")
OVERLAY_HEADER_SOURCE_RELATIVE_PATH = Path("mobile/input/virtual_touch_controls.hpp")
PATCH_MARKER = "PLATINA_MOBILE_TOUCH_INPUT_ROUTER_V1"


class MobileInputPreparationError(RuntimeError):
    pass


def run_git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise MobileInputPreparationError(
            f"git {' '.join(arguments)} failed: {detail}"
        )
    return result.stdout.strip()


def read_regular_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise MobileInputPreparationError(f"Missing or unsafe source file: {path}")
    return path.read_bytes()


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def prepare_mobile_input(libntr_root: str | Path) -> bool:
    root = Path(libntr_root).expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        raise MobileInputPreparationError(
            f"libntr root must be a real directory: {root}"
        )

    revision = run_git(root, "rev-parse", "HEAD")
    if revision != PINNED_LIBNTR_REVISION:
        raise MobileInputPreparationError(
            "Refusing to patch an unreviewed libntr revision: "
            f"expected {PINNED_LIBNTR_REVISION}, got {revision}"
        )

    repository_root = Path(__file__).resolve().parents[1]
    source_path = root / SOURCE_RELATIVE_PATH
    installed_header = root / HEADER_RELATIVE_PATH
    header_source = repository_root / HEADER_SOURCE_RELATIVE_PATH
    overlay_header_source = repository_root / OVERLAY_HEADER_SOURCE_RELATIVE_PATH
    patch_path = repository_root / PATCH_RELATIVE_PATH

    source_bytes = read_regular_file(source_path)
    header_bytes = read_regular_file(header_source)
    overlay_header_bytes = read_regular_file(overlay_header_source)
    read_regular_file(patch_path)
    source_text = source_bytes.decode("utf-8")

    if PATCH_MARKER in source_text:
        if '#include "touch_input_router.hpp"' not in source_text:
            raise MobileInputPreparationError(
                "The touch patch marker exists but its include is missing."
            )
        if not installed_header.is_file() or installed_header.is_symlink():
            raise MobileInputPreparationError(
                "The touch patch is applied but the router header is missing."
            )
        if installed_header.read_bytes() != header_bytes:
            raise MobileInputPreparationError(
                "The installed router header differs from the reviewed source header."
            )
        installed_overlay_header = root / OVERLAY_HEADER_RELATIVE_PATH
        if not installed_overlay_header.is_file() or installed_overlay_header.is_symlink():
            raise MobileInputPreparationError(
                "The overlay patch is applied but its virtual-control header is missing."
            )
        if installed_overlay_header.read_bytes() != overlay_header_bytes:
            raise MobileInputPreparationError(
                "The installed virtual-control header differs from the reviewed source header."
            )
        run_git(root, "diff", "--check")
        print("Mobile SDL touch input patch is already applied.")
        return False

    installed_overlay_header = root / OVERLAY_HEADER_RELATIVE_PATH
    if installed_header.exists() or installed_header.is_symlink():
        if installed_header.is_symlink() or installed_header.read_bytes() != header_bytes:
            raise MobileInputPreparationError(
                "A different touch_input_router.hpp already exists in the libntr checkout."
            )
    if installed_overlay_header.exists() or installed_overlay_header.is_symlink():
        if installed_overlay_header.is_symlink() or installed_overlay_header.read_bytes() != overlay_header_bytes:
            raise MobileInputPreparationError(
                "A different virtual_touch_controls.hpp already exists in the libntr checkout."
            )

    # The exact source revision, patch context, and header are validated before
    # writing any file. This also allows the renderer patch to run first.
    check = subprocess.run(
        ["git", "-C", str(root), "apply", "--check", "--whitespace=error", str(patch_path)],
        check=False,
        text=True,
        capture_output=True,
    )
    if check.returncode != 0:
        raise MobileInputPreparationError(
            "The SDL input patch no longer matches the reviewed libntr source: "
            + (check.stderr.strip() or check.stdout.strip())
        )

    created_headers: list[Path] = []
    try:
        for destination, contents in (
            (installed_header, header_bytes),
            (installed_overlay_header, overlay_header_bytes),
        ):
            if not destination.exists():
                atomic_write(destination, contents)
                created_headers.append(destination)

        run_git(root, "apply", "--whitespace=error", str(patch_path))
        patched_source = read_regular_file(source_path).decode("utf-8")
        if PATCH_MARKER not in patched_source:
            raise MobileInputPreparationError(
                "Patch command completed but the source marker was not installed."
            )
        if installed_header.read_bytes() != header_bytes:
            raise MobileInputPreparationError(
                "The installed router header failed content verification."
            )
        if installed_overlay_header.read_bytes() != overlay_header_bytes:
            raise MobileInputPreparationError(
                "The installed virtual-control header failed content verification."
            )
        run_git(root, "diff", "--check")
    except Exception:
        for created in reversed(created_headers):
            if created.exists():
                created.unlink()
        raise

    print(
        "Mobile SDL touch input patch applied to pinned libntr "
        f"{PINNED_LIBNTR_REVISION}."
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "libntr_root",
        help="Path to the exact pinned libntr checkout.",
    )
    args = parser.parse_args()

    try:
        prepare_mobile_input(args.libntr_root)
    except (OSError, UnicodeError, MobileInputPreparationError) as error:
        print(f"Mobile input preparation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
