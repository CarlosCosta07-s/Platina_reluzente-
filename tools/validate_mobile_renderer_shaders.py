#!/usr/bin/env python3
"""Compile and link only the source GLSL ES 3.00 shaders on a desktop host.

This tool never configures an Android/iOS target and never creates an app package.
It requires glslangValidator to be installed by the host environment.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHADERS = ROOT / "mobile" / "renderer" / "gles300"
PROGRAMS = {
    "G2": ("g2_vertex.glsl", "g2_fragment.glsl"),
    "G3": ("g3_vertex.glsl", "g3_fragment.glsl"),
}


def main() -> int:
    validator = shutil.which("glslangValidator")
    if validator is None:
        print(
            "glslangValidator is required for host-only GLSL validation; "
            "install the glslang-tools package.",
            file=sys.stderr,
        )
        return 2

    for program_name, (vertex_name, fragment_name) in PROGRAMS.items():
        vertex_source = SHADERS / vertex_name
        fragment_source = SHADERS / fragment_name
        if not vertex_source.is_file() or not fragment_source.is_file():
            print(f"{program_name}: shader source is missing.", file=sys.stderr)
            return 2

    with tempfile.TemporaryDirectory(prefix="platina-gles300-") as temporary:
        temp = Path(temporary)
        for program_name, (vertex_name, fragment_name) in PROGRAMS.items():
            vertex_path = temp / f"{program_name.lower()}.vert"
            fragment_path = temp / f"{program_name.lower()}.frag"
            shutil.copyfile(SHADERS / vertex_name, vertex_path)
            shutil.copyfile(SHADERS / fragment_name, fragment_path)

            for stage, shader_path in (("vert", vertex_path), ("frag", fragment_path)):
                print(f"Validating {program_name} {stage} shader...", flush=True)
                result = subprocess.run(
                    [validator, "-S", stage, str(shader_path)],
                    check=False,
                    text=True,
                    capture_output=True,
                )
                if result.stdout:
                    print(result.stdout, end="")
                if result.stderr:
                    print(result.stderr, end="", file=sys.stderr)
                if result.returncode != 0:
                    print(
                        f"{program_name} {stage} shader validation failed.",
                        file=sys.stderr,
                    )
                    return result.returncode

            print(f"Linking {program_name} GLES 3.00 program...", flush=True)
            result = subprocess.run(
                [validator, "-l", str(vertex_path), str(fragment_path)],
                check=False,
                text=True,
                capture_output=True,
            )
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            if result.returncode != 0:
                print(f"{program_name} GLES 3.00 program link failed.", file=sys.stderr)
                return result.returncode

    print(
        "Host-only GLSL ES 3.00 compile/link checks passed. "
        "No Android or iOS application target was built.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
