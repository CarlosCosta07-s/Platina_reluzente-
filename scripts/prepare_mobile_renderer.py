#!/usr/bin/env python3
"""Prepare a pinned libntr checkout for the source-only GLES 3.0 renderer.

This step only edits source files in an already-fetched libntr wrap. It does not
configure Meson, invoke a compiler, build Android/iOS targets, or package apps.
Every source replacement is anchored to an exact upstream block and is planned
before any write. Re-running the preparer is idempotent.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

MOBILE_GUARD = "#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)"

GLAD_INCLUDE_BLOCK = """#ifdef SDK_BUILD_NX
#include <glad/glad.h>
#else
#include <simulator/glad/glad.h>
#endif"""

SIM_MAIN_GL_INCLUDE_PATCH = """#include <simulator/sim_gl.h>
#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)
#include <simulator/sim_gles3_compat.h>
#endif"""

HEADER_GL_INCLUDE_PATCH = "#include <simulator/sim_gl.h>"

TEXTURE_GL_INCLUDE_ORIGINAL = '#include "simulator/glad/glad.h"'
TEXTURE_GL_INCLUDE_PATCHED = "#include <simulator/sim_gl.h>"

G3_DRAW_INCLUDE_ORIGINAL = "#include <simulator/g3_draw.h>"
G3_DRAW_INCLUDE_PATCHED = """#include <simulator/g3_draw.h>
#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)
#include <simulator/sim_gles3_compat.h>
#endif"""

SIM_GL_ATTRIBUTES_ORIGINAL = """  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 4);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 2);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);"""
SIM_GL_ATTRIBUTES_PATCHED = """#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 0);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES);
#else
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 4);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 2);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
#endif"""

GLAD_LOADER_ORIGINAL = "  gladLoadGLLoader(SDL_GL_GetProcAddress);"
GLAD_LOADER_PATCHED = """#if !defined(SDK_BUILD_ANDROID) && !defined(SDK_BUILD_IOS)
  gladLoadGLLoader(SDL_GL_GetProcAddress);
#endif"""

DEBUG_OUTPUT_ORIGINAL = """  glEnable(GL_DEBUG_OUTPUT);
  glDebugMessageCallback(MessageCallback, 0);"""
DEBUG_OUTPUT_PATCHED = """#if !defined(SDK_BUILD_ANDROID) && !defined(SDK_BUILD_IOS)
  glEnable(GL_DEBUG_OUTPUT);
  glDebugMessageCallback(MessageCallback, 0);
#endif"""

GLAD_SOURCE_ORIGINAL = "libsim_srcs += files('glad.c')"
GLAD_SOURCE_PATCHED = """if build_target != 'android' and build_target != 'ios'
libsim_srcs += files('glad.c')
endif"""

MOBILE_MESON_DEFINES = """if build_target == 'android'
    libsim_args += ['-DSDK_BUILD_ANDROID', '-DIMGUI_IMPL_OPENGL_ES3']
elif build_target == 'ios'
    libsim_args += ['-DSDK_BUILD_IOS', '-DIMGUI_IMPL_OPENGL_ES3']
endif"""

G3_BORDER_WRAP_ORIGINAL = r'''		if(s_texImageParam.repeatS) {
			if(s_texImageParam.flipS)
			{
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_MIRRORED_REPEAT);
			} else {
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
			}
		} else {
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER);
		}

		if(s_texImageParam.repeatT) {
			if(s_texImageParam.flipT)
			{
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_MIRRORED_REPEAT);
			} else {
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
			}
		} else {
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER);
		}'''
G3_BORDER_WRAP_PATCHED = r'''#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)
		const GLint clampToBorderS = s_texImageParam.repeatS ? 0 : 1;
		const GLint clampToBorderT = s_texImageParam.repeatT ? 0 : 1;
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S,
		                s_texImageParam.repeatS
		                    ? (s_texImageParam.flipS ? GL_MIRRORED_REPEAT : GL_REPEAT)
		                    : GL_CLAMP_TO_EDGE);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T,
		                s_texImageParam.repeatT
		                    ? (s_texImageParam.flipT ? GL_MIRRORED_REPEAT : GL_REPEAT)
		                    : GL_CLAMP_TO_EDGE);
		glProgramUniform1i(g3shaderProgramID,
		                   glGetUniformLocation(g3shaderProgramID, "clampToBorderS"),
		                   clampToBorderS);
		glProgramUniform1i(g3shaderProgramID,
		                   glGetUniformLocation(g3shaderProgramID, "clampToBorderT"),
		                   clampToBorderT);
#else
		if(s_texImageParam.repeatS) {
			if(s_texImageParam.flipS)
			{
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_MIRRORED_REPEAT);
			} else {
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
			}
		} else {
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER);
		}

		if(s_texImageParam.repeatT) {
			if(s_texImageParam.flipT)
			{
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_MIRRORED_REPEAT);
			} else {
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
			}
		} else {
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER);
		}
#endif'''

DEFERRED_TEXTURE_BLOCK_ORIGINAL = r'''		if(item->textureId != 0){
			glActiveTexture(GL_TEXTURE0);
			glBindTexture(GL_TEXTURE_2D, item->textureId);
			//Enable texture in the shader
			glProgramUniform1i(g3shaderProgramID, glGetUniformLocation(g3shaderProgramID, "useTexture") , 1);
		} else {
			glProgramUniform1i(g3shaderProgramID, glGetUniformLocation(g3shaderProgramID, "useTexture") , 0);
		}'''
DEFERRED_TEXTURE_BLOCK_PATCHED = r'''		if(item->textureId != 0){
			glActiveTexture(GL_TEXTURE0);
			glBindTexture(GL_TEXTURE_2D, item->textureId);
			//Enable texture in the shader
			glProgramUniform1i(g3shaderProgramID, glGetUniformLocation(g3shaderProgramID, "useTexture") , 1);
		} else {
			glProgramUniform1i(g3shaderProgramID, glGetUniformLocation(g3shaderProgramID, "useTexture") , 0);
		}
#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)
		// Match the pinned Desktop deferred path: it always uses repeat/mirror
		// according to flipS/flipT and does not use clamp-to-border.
		glProgramUniform1i(g3shaderProgramID,
		                   glGetUniformLocation(g3shaderProgramID, "clampToBorderS"), 0);
		glProgramUniform1i(g3shaderProgramID,
		                   glGetUniformLocation(g3shaderProgramID, "clampToBorderT"), 0);
#endif'''

SHADER_INCLUDE_BLOCKS = (
    (
        '#include "shaders/g3_vertex.glsl"',
        """#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)
#include "shaders/gles300/g3_vertex.glsl"
#else
#include "shaders/g3_vertex.glsl"
#endif""",
    ),
    (
        '#include "shaders/g3_fragment.glsl"',
        """#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)
#include "shaders/gles300/g3_fragment.glsl"
#else
#include "shaders/g3_fragment.glsl"
#endif""",
    ),
    (
        '#include "shaders/g2_vertex.glsl"',
        """#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)
#include "shaders/gles300/g2_vertex.glsl"
#else
#include "shaders/g2_vertex.glsl"
#endif""",
    ),
    (
        '#include "shaders/g2_fragment.glsl"',
        """#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)
#include "shaders/gles300/g2_fragment.glsl"
#else
#include "shaders/g2_fragment.glsl"
#endif""",
)

REQUIRED_SOURCE_PATHS = (
    "libraries/sim/src/sim_main.cpp",
    "libraries/sim/src/g3_draw.cpp",
    "libraries/sim/src/sim_g3_Texture.cpp",
    "libraries/sim/src/sim_shaders.cpp",
    "libraries/sim/src/meson.build",
    "include/simulator/g3_draw.h",
)

ASSET_NAMES = (
    "sim_gl.h",
    "sim_gles3_compat.h",
    "program_uniform_compat.hpp",
    "g2_vertex.glsl",
    "g2_fragment.glsl",
    "g3_vertex.glsl",
    "g3_fragment.glsl",
)


class MobileRendererPreparationError(RuntimeError):
    """Raised when the pinned source no longer matches the reviewed patch context."""


def _replace_once(source: str, original: str, patched: str, label: str) -> tuple[str, bool]:
    patched_count = source.count(patched)
    original_count = source.count(original)
    if patched_count == 1:
        if original_count:
            raise MobileRendererPreparationError(
                f"Both original and mobile-patched forms exist for {label}."
            )
        return source, False
    if patched_count > 1 or original_count != 1:
        raise MobileRendererPreparationError(
            f"Expected exactly one original {label} block; found original={original_count}, "
            f"patched={patched_count}."
        )
    return source.replace(original, patched, 1), True


def _replace_include_blocks(source: str, label: str) -> tuple[str, bool]:
    current = source
    changed = False
    for original, patched in SHADER_INCLUDE_BLOCKS:
        current, item_changed = _replace_once(
            current, original, patched, f"{label}: {original}"
        )
        changed = changed or item_changed
    return current, changed


def _read_regular_file(root: Path, relative: str) -> tuple[Path, str]:
    path = root / relative
    try:
        resolved_parent = path.parent.resolve(strict=True)
        if root.resolve() not in (resolved_parent, *resolved_parent.parents):
            raise MobileRendererPreparationError(f"Target parent escapes libntr root: {path}")
        stat = path.lstat()
    except FileNotFoundError as error:
        raise MobileRendererPreparationError(f"Required libntr source is missing: {path}") from error
    if path.is_symlink() or not path.is_file():
        raise MobileRendererPreparationError(f"Target is not a regular source file: {path}")
    return path, path.read_text(encoding="utf-8")


def _prepare_sim_main(source: str) -> tuple[str, bool]:
    current, changed = _replace_once(
        source, GLAD_INCLUDE_BLOCK, SIM_MAIN_GL_INCLUDE_PATCH, "sim_main GL include"
    )
    current, item_changed = _replace_once(
        current, SIM_GL_ATTRIBUTES_ORIGINAL, SIM_GL_ATTRIBUTES_PATCHED,
        "SDL Desktop/OpenGL ES context selection",
    )
    changed = changed or item_changed
    current, item_changed = _replace_once(
        current, GLAD_LOADER_ORIGINAL, GLAD_LOADER_PATCHED, "Desktop GLAD initialization"
    )
    changed = changed or item_changed
    current, item_changed = _replace_once(
        current, DEBUG_OUTPUT_ORIGINAL, DEBUG_OUTPUT_PATCHED, "optional GL debug output"
    )
    changed = changed or item_changed
    return current, changed


def _prepare_g3_header(source: str) -> tuple[str, bool]:
    return _replace_once(source, GLAD_INCLUDE_BLOCK, HEADER_GL_INCLUDE_PATCH, "g3_draw.h GL include")


def _prepare_texture_source(source: str) -> tuple[str, bool]:
    return _replace_once(
        source, TEXTURE_GL_INCLUDE_ORIGINAL, TEXTURE_GL_INCLUDE_PATCHED,
        "sim_g3_Texture.cpp GL include",
    )


def _prepare_shader_source(source: str) -> tuple[str, bool]:
    return _replace_include_blocks(source, "sim_shaders.cpp shader selection")


def _prepare_g3_draw(source: str) -> tuple[str, bool]:
    current, changed = _replace_once(
        source, G3_DRAW_INCLUDE_ORIGINAL, G3_DRAW_INCLUDE_PATCHED, "g3_draw.cpp GLES wrapper include"
    )
    current, item_changed = _replace_once(
        current, G3_BORDER_WRAP_ORIGINAL, G3_BORDER_WRAP_PATCHED,
        "G3 normal-path transparent border emulation",
    )
    changed = changed or item_changed
    current, item_changed = _replace_once(
        current, DEFERRED_TEXTURE_BLOCK_ORIGINAL, DEFERRED_TEXTURE_BLOCK_PATCHED,
        "G3 deferred texture border-state reset",
    )
    return current, changed or item_changed


def _prepare_meson(source: str) -> tuple[str, bool]:
    current, changed = _replace_once(
        source, GLAD_SOURCE_ORIGINAL, GLAD_SOURCE_PATCHED, "Desktop GLAD source selection"
    )
    # The future mobile target names are reserved here; no target is created and
    # no app build is invoked by this preparer.
    mobile_args = current.count(MOBILE_MESON_DEFINES)
    if mobile_args == 0:
        anchor = "libsim_args = [ ]"
        if current.count(anchor) != 1:
            raise MobileRendererPreparationError(
                "Expected exactly one libsim_args declaration before adding mobile-only compile flags."
            )
        current = current.replace(anchor, anchor + "\n\n" + MOBILE_MESON_DEFINES, 1)
        changed = True
    elif mobile_args != 1:
        raise MobileRendererPreparationError("Duplicate mobile-only ImGui/GLES compile flag block.")
    return current, changed


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
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


def prepare_mobile_renderer(
    libntr_root: str | Path,
    assets_root: str | Path | None = None,
) -> bool:
    """Apply exact, idempotent GLES renderer changes to a pinned libntr source tree."""
    root = Path(libntr_root).expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        raise MobileRendererPreparationError(f"libntr root must be a real directory: {root}")
    if assets_root is None:
        assets = Path(__file__).resolve().parents[1] / "mobile" / "renderer" / "gles300"
    else:
        assets = Path(assets_root).expanduser().resolve()
    if not assets.is_dir() or assets.is_symlink():
        raise MobileRendererPreparationError(f"GLES asset directory is missing or unsafe: {assets}")

    # Plan all source changes before writing. Unknown upstream source must fail
    # closed without leaving a partially patched checkout.
    source_paths = {rel: _read_regular_file(root, rel) for rel in REQUIRED_SOURCE_PATHS}
    planned: dict[Path, str] = {}
    changed = False

    transforms = {
        "libraries/sim/src/sim_main.cpp": _prepare_sim_main,
        "libraries/sim/src/g3_draw.cpp": _prepare_g3_draw,
        "libraries/sim/src/sim_g3_Texture.cpp": _prepare_texture_source,
        "libraries/sim/src/sim_shaders.cpp": _prepare_shader_source,
        "libraries/sim/src/meson.build": _prepare_meson,
        "include/simulator/g3_draw.h": _prepare_g3_header,
    }
    for relative, transform in transforms.items():
        path, original = source_paths[relative]
        updated, item_changed = transform(original)
        if item_changed:
            planned[path] = updated
            changed = True

    # Validate and plan source assets. Never overwrite a different pre-existing
    # file in the pinned native checkout.
    assets_to_install = {
        "include/simulator/sim_gl.h": "sim_gl.h",
        "include/simulator/sim_gles3_compat.h": "sim_gles3_compat.h",
        "include/simulator/program_uniform_compat.hpp": "program_uniform_compat.hpp",
        "libraries/sim/src/shaders/gles300/g2_vertex.glsl": "g2_vertex.glsl",
        "libraries/sim/src/shaders/gles300/g2_fragment.glsl": "g2_fragment.glsl",
        "libraries/sim/src/shaders/gles300/g3_vertex.glsl": "g3_vertex.glsl",
        "libraries/sim/src/shaders/gles300/g3_fragment.glsl": "g3_fragment.glsl",
    }
    for destination_relative, asset_name in assets_to_install.items():
        asset_path = assets / asset_name
        if not asset_path.is_file() or asset_path.is_symlink():
            raise MobileRendererPreparationError(f"Required GLES source asset is missing: {asset_path}")
        destination = root / destination_relative
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_file():
                raise MobileRendererPreparationError(f"Unsafe existing GLES destination: {destination}")
            existing = destination.read_text(encoding="utf-8")
            desired = asset_path.read_text(encoding="utf-8")
            if existing != desired:
                raise MobileRendererPreparationError(
                    f"Existing GLES source differs from the reviewed asset; refusing overwrite: {destination}"
                )
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        planned[destination] = asset_path.read_text(encoding="utf-8")
        changed = True

    # Include the GLES compatibility macros only in C++ translation units;
    # headers included by C SDK sources keep the GL boundary C-compatible.
    if planned:
        originals = {path: path.read_text(encoding="utf-8") if path.exists() else None for path in planned}
        written: list[Path] = []
        try:
            for path, content in planned.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(path, content)
                written.append(path)
        except Exception:
            for path in reversed(written):
                previous = originals[path]
                try:
                    if previous is None:
                        path.unlink(missing_ok=True)
                    else:
                        _atomic_write(path, previous)
                except OSError:
                    print(f"Rollback failed for {path}", file=sys.stderr)
            raise
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("libntr_root", help="Path to the fetched/pinned subprojects/libntr directory")
    parser.add_argument(
        "--assets-root",
        help="Optional override for mobile/renderer/gles300 (used by source tests)",
    )
    args = parser.parse_args(argv)
    try:
        changed = prepare_mobile_renderer(args.libntr_root, args.assets_root)
    except (OSError, MobileRendererPreparationError) as error:
        print(f"Mobile renderer source preparation failed: {error}", file=sys.stderr)
        return 2
    print(
        "Mobile GLES renderer source patch applied."
        if changed else
        "Mobile GLES renderer source patch is already applied."
    )
    print("No compiler, NDK, Xcode, or mobile app packaging command was run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
