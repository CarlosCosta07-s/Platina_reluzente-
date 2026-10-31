#!/usr/bin/env python3
"""Compare pinned Desktop GL 4.2 and GLES 3.0 G3 shader output on Mesa/EGL.

This is a host-only synthetic renderer test. It uses no ROM/game data and does
not configure or build Android/iOS application targets.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WIDTH = 64
HEIGHT = 64
BYTES_PER_SCENE = WIDTH * HEIGHT * 4
SCENE_NAMES = (
    "untextured_vertex_color",
    "texture_times_vertex_color",
    "texture_only",
    "alpha_discard",
    "fogged_texture",
    "transparent_border_s",
    "transparent_border_t",
    "transparent_border_st",
    "repeat_s_t",
    "mirror_s_t",
)
# Mesa GL and GLES can differ by a least-significant-bit rounding step on
# interpolants. Keep the allowance small and report every divergent pixel.
MAX_CHANNEL_DELTA = 2
MAX_DIVERGENT_PIXELS_PER_SCENE = 8


def extract_cpp_raw_shader(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    match = re.fullmatch(r'R""\((.*)\)""\s*', source, flags=re.DOTALL)
    if match is None:
        raise RuntimeError(f"Expected C++ raw-string GLSL source at {path}")
    return match.group(1)


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(command)}"
        )


def compile_probe(
    compiler: str,
    source: Path,
    output: Path,
    *,
    gles: bool,
) -> None:
    command = [
        compiler,
        "-std=c++17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror=return-type",
    ]
    if gles:
        command.append("-DPLATINA_USE_GLES3")
        libraries = ["-lEGL", "-lGLESv2"]
    else:
        command.append("-DGL_GLEXT_PROTOTYPES")
        libraries = ["-lEGL", "-lGL"]
    command += [str(source), "-o", str(output), *libraries]
    run(command)


def compare_scene(desktop: bytes, gles: bytes) -> tuple[int, int, float]:
    if len(desktop) != BYTES_PER_SCENE or len(gles) != BYTES_PER_SCENE:
        raise RuntimeError(
            f"Expected {BYTES_PER_SCENE} RGBA bytes per scene, got "
            f"Desktop={len(desktop)}, GLES={len(gles)}"
        )

    max_delta = 0
    divergent_pixels = 0
    total_delta = 0
    for offset in range(0, BYTES_PER_SCENE, 4):
        pixel_delta = 0
        for channel in range(4):
            delta = abs(desktop[offset + channel] - gles[offset + channel])
            total_delta += delta
            max_delta = max(max_delta, delta)
            pixel_delta = max(pixel_delta, delta)
        if pixel_delta != 0:
            divergent_pixels += 1
    mean_channel_delta = total_delta / BYTES_PER_SCENE
    return max_delta, divergent_pixels, mean_channel_delta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "libntr_root",
        type=Path,
        help="Checkout of the pinned libntr revision after source-only mobile patching",
    )
    parser.add_argument(
        "--probe-source",
        type=Path,
        default=Path(__file__).resolve().parent / "cpp" / "renderer_g3_pixel_probe.cpp",
    )
    parser.add_argument("--max-channel-delta", type=int, default=MAX_CHANNEL_DELTA)
    parser.add_argument(
        "--max-divergent-pixels",
        type=int,
        default=MAX_DIVERGENT_PIXELS_PER_SCENE,
    )
    args = parser.parse_args()

    if args.max_channel_delta < 0 or args.max_divergent_pixels < 0:
        parser.error("pixel tolerances must be non-negative")

    root = args.libntr_root.resolve()
    shader_root = root / "libraries" / "sim" / "src" / "shaders"
    desktop_vertex = shader_root / "g3_vertex.glsl"
    desktop_fragment = shader_root / "g3_fragment.glsl"
    mobile_vertex = shader_root / "gles300" / "g3_vertex.glsl"
    mobile_fragment = shader_root / "gles300" / "g3_fragment.glsl"

    for required in (desktop_vertex, desktop_fragment, mobile_vertex, mobile_fragment, args.probe_source):
        if not required.is_file() or required.is_symlink():
            raise RuntimeError(f"Missing or unsafe pixel-comparison source: {required}")

    compiler = shutil.which("c++") or shutil.which("g++")
    if compiler is None:
        raise RuntimeError("A host C++ compiler (c++/g++) is required.")
    if shutil.which("pkg-config") is None:
        raise RuntimeError("pkg-config is required to inspect host EGL/GL dependencies.")

    with tempfile.TemporaryDirectory(prefix="platina-g3-pixel-") as directory:
        temp = Path(directory)
        desktop_vert = temp / "desktop_g3.vert"
        desktop_frag = temp / "desktop_g3.frag"
        mobile_vert = temp / "mobile_g3.vert"
        mobile_frag = temp / "mobile_g3.frag"

        desktop_vert.write_text(extract_cpp_raw_shader(desktop_vertex), encoding="utf-8")
        desktop_frag.write_text(extract_cpp_raw_shader(desktop_fragment), encoding="utf-8")
        # The patched native source contains C++ raw-string wrappers for these
        # files because sim_shaders.cpp includes them as source literals.
        mobile_vert.write_text(extract_cpp_raw_shader(mobile_vertex), encoding="utf-8")
        mobile_frag.write_text(extract_cpp_raw_shader(mobile_fragment), encoding="utf-8")

        desktop_binary = temp / "desktop-g3-pixel-probe"
        gles_binary = temp / "gles-g3-pixel-probe"
        desktop_output = temp / "desktop.rgba"
        gles_output = temp / "gles.rgba"

        compile_probe(compiler, args.probe_source.resolve(), desktop_binary, gles=False)
        compile_probe(compiler, args.probe_source.resolve(), gles_binary, gles=True)

        base_env = os.environ.copy()
        base_env["EGL_PLATFORM"] = "surfaceless"
        base_env["LIBGL_ALWAYS_SOFTWARE"] = "1"
        base_env["MESA_LOADER_DRIVER_OVERRIDE"] = "llvmpipe"

        # Do not let Mesa silently select its newest API version. Exercise the
        # minimum renderer contracts requested by the port: Desktop 4.2 Core
        # and OpenGL ES 3.0. The probe prints the actual GL_VERSION each time.
        desktop_env = base_env.copy()
        desktop_env["MESA_GL_VERSION_OVERRIDE"] = "4.2"
        desktop_env.pop("MESA_GLES_VERSION_OVERRIDE", None)

        gles_env = base_env.copy()
        gles_env["MESA_GLES_VERSION_OVERRIDE"] = "3.0"
        gles_env.pop("MESA_GL_VERSION_OVERRIDE", None)

        print("Rendering pinned Desktop GL 4.2 Core scenes on Mesa/EGL...", flush=True)
        run([str(desktop_binary), str(desktop_vert), str(desktop_frag), str(desktop_output)], env=desktop_env)

        print("Rendering GLES 3.0 scenes on Mesa/EGL...", flush=True)
        run([str(gles_binary), str(mobile_vert), str(mobile_frag), str(gles_output)], env=gles_env)

        desktop_bytes = desktop_output.read_bytes()
        gles_bytes = gles_output.read_bytes()
        expected_size = BYTES_PER_SCENE * len(SCENE_NAMES)
        if len(desktop_bytes) != expected_size or len(gles_bytes) != expected_size:
            raise RuntimeError(
                f"Unexpected output size: Desktop={len(desktop_bytes)}, GLES={len(gles_bytes)}, "
                f"expected={expected_size}"
            )

        failed = False
        print(
            "G3 synthetic pixel comparison "
            f"(max channel delta <= {args.max_channel_delta}, "
            f"divergent pixels <= {args.max_divergent_pixels} per scene)"
        )
        for index, name in enumerate(SCENE_NAMES):
            start = index * BYTES_PER_SCENE
            end = start + BYTES_PER_SCENE
            max_delta, divergent_pixels, mean_delta = compare_scene(
                desktop_bytes[start:end],
                gles_bytes[start:end],
            )
            passed = (
                max_delta <= args.max_channel_delta
                and divergent_pixels <= args.max_divergent_pixels
            )
            status = "PASS" if passed else "FAIL"
            print(
                f"{status} {name}: max_delta={max_delta}, "
                f"divergent_pixels={divergent_pixels}, "
                f"mean_channel_delta={mean_delta:.6f}"
            )
            failed = failed or not passed

        if failed:
            raise RuntimeError(
                "G3 Desktop/GLES synthetic pixel comparison exceeded the documented tolerance."
            )

    print(
        "G3 host synthetic pixel comparison passed. This does not prove device-driver "
        "parity and does not build an Android/iOS application.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"G3 host pixel comparison failed: {error}", file=sys.stderr)
        raise SystemExit(1)
