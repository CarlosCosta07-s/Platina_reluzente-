#!/usr/bin/env python3
"""Prepare the pinned libntr renderer sources for Android OpenGL ES 3.2.

This changes only the temporary upstream checkout passed to the command. It is
not a complete Android game build and does not claim gameplay compatibility.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

LIBNTR_COMMIT = "1555d911ac80c0190ac1c321f99f1323de8b3c09"
SHADERS = {
    "g2_vertex.glsl": "vert",
    "g2_fragment.glsl": "frag",
    "g3_vertex.glsl": "vert",
    "g3_fragment.glsl": "frag",
}
GLAD_BLOCK = (
    "#ifdef SDK_BUILD_NX\n"
    "#include <glad/glad.h>\n"
    "#else\n"
    "#include <simulator/glad/glad.h>\n"
    "#endif"
)
GLES_BLOCK = (
    "#if defined(SDK_BUILD_ANDROID)\n"
    "#include <GLES3/gl32.h>\n"
    "#elif defined(SDK_BUILD_NX)\n"
    "#include <glad/glad.h>\n"
    "#else\n"
    "#include <simulator/glad/glad.h>\n"
    "#endif\n"
    "#if defined(SDK_BUILD_ANDROID) && !defined(GLAPIENTRY)\n"
    "#define GLAPIENTRY GL_APIENTRY\n"
    "#endif"
)
DESKTOP_CONTEXT = (
    "  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 4);\n"
    "  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 2);\n"
    "  SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);"
)
PORTABLE_CONTEXT = (
    "#ifdef SDK_BUILD_ANDROID\n"
    "  // Request GLES, not a desktop OpenGL core profile.\n"
    "  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);\n"
    "  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 2);\n"
    "  SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES);\n"
    "#else\n"
    "  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 4);\n"
    "  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 2);\n"
    "  SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);\n"
    "#endif"
)
SHADER_PROLOGUE = (
    "#version 320 es\n"
    "precision highp float;\n"
    "precision highp int;\n"
    "precision highp sampler2D;"
)
BORDER_HELPER = """
#ifdef SDK_BUILD_ANDROID
#include <SDL2/SDL_video.h>
#include <stdio.h>
#ifndef GL_CLAMP_TO_BORDER_EXT
#define GL_CLAMP_TO_BORDER_EXT 0x812D
#endif
static GLenum SIM_GetBorderClampMode() {
    if (SDL_GL_ExtensionSupported("GL_EXT_texture_border_clamp")) {
        return GL_CLAMP_TO_BORDER_EXT;
    }
    // GLES core lacks border clamp; this fallback may change texture-edge pixels.
    static bool warningPrinted = false;
    if (!warningPrinted) {
        fprintf(stderr, "Android GLES: border-clamp extension absent; using CLAMP_TO_EDGE fallback.\\n");
        warningPrinted = true;
    }
    return GL_CLAMP_TO_EDGE;
}
#else
#define SIM_GetBorderClampMode() GL_CLAMP_TO_BORDER
#endif

"""


class AndroidGraphicsPatchError(RuntimeError):
    pass


def replace_exact(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    # Check the replacement first because some reviewed replacement blocks retain
    # the desktop-only text inside an Android/desktop conditional.
    if new in text:
        if text.count(new) != 1:
            raise AndroidGraphicsPatchError(f"{label}: expected one patched marker.")
        return text, False
    if old in text:
        if text.count(old) != 1:
            raise AndroidGraphicsPatchError(f"{label}: expected one original marker; no files written.")
        return text.replace(old, new, 1), True
    raise AndroidGraphicsPatchError(f"{label}: upstream marker not found; no files written.")


def prepare_android_graphics(source_root: str | Path, shader_output: str | Path | None = None) -> dict[str, object]:
    root = Path(source_root).expanduser().resolve()
    required = [
        root / "libraries/sim/src/sim_main.cpp",
        root / "libraries/sim/src/g3_draw.cpp",
        root / "include/simulator/g3_draw.h",
        root / "libraries/sim/meson.build",
        *(root / "libraries/sim/src/shaders" / name for name in SHADERS),
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise AndroidGraphicsPatchError("Missing expected source files: " + ", ".join(missing))

    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0 and result.stdout.strip() != LIBNTR_COMMIT:
            raise AndroidGraphicsPatchError(
                "Unexpected libntr revision: " + result.stdout.strip()
            )

    staged: dict[Path, str] = {}
    changes: list[str] = []

    for relative in ("libraries/sim/src/sim_main.cpp", "include/simulator/g3_draw.h"):
        path = root / relative
        updated, changed = replace_exact(path.read_text(encoding="utf-8"), GLAD_BLOCK, GLES_BLOCK, relative)
        staged[path] = updated
        if changed:
            changes.append(relative + ": select GLES 3.2 headers on Android")

    main_path = root / "libraries/sim/src/sim_main.cpp"
    main, changed = replace_exact(staged[main_path], DESKTOP_CONTEXT, PORTABLE_CONTEXT, "SDL GL context")
    if changed:
        changes.append("sim_main.cpp: request OpenGL ES 3.2 on Android only")
    loader = "  gladLoadGLLoader(SDL_GL_GetProcAddress);"
    main, changed = replace_exact(main, loader, "#ifndef SDK_BUILD_ANDROID\n" + loader + "\n#endif", "desktop GL loader")
    if changed:
        changes.append("sim_main.cpp: skip desktop GL loader on Android")
    staged[main_path] = main

    draw_path = root / "libraries/sim/src/g3_draw.cpp"
    draw = draw_path.read_text(encoding="utf-8")
    draw, changed = replace_exact(draw, "#define G3_DRAW_MAX_ITEMS 1000", BORDER_HELPER + "#define G3_DRAW_MAX_ITEMS 1000", "border-clamp helper")
    if changed:
        changes.append("g3_draw.cpp: add extension-aware border-clamp handling")
    for axis in ("S", "T"):
        original = "glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_" + axis + ", GL_CLAMP_TO_BORDER);"
        replacement = "glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_" + axis + ", SIM_GetBorderClampMode());"
        draw, changed = replace_exact(draw, original, replacement, "border clamp " + axis)
        if changed:
            changes.append("g3_draw.cpp: route " + axis + " border clamp through capability check")
    staged[draw_path] = draw

    meson_path = root / "libraries/sim/meson.build"
    meson, changed = replace_exact(
        meson_path.read_text(encoding="utf-8"),
        "libsim_args = [ ]",
        "libsim_args = [ ]\n\nif(build_target == 'android')\n"
        "    # Choose Dear ImGui's GLES3 renderer for the Android simulator.\n"
        "    libsim_args += ['-DIMGUI_IMPL_OPENGL_ES3']\n"
        "endif",
        "Dear ImGui GLES renderer selector",
    )
    if changed:
        changes.append("libraries/sim/meson.build: select Dear ImGui GLES3 renderer")
    staged[meson_path] = meson

    shaders: dict[str, str] = {}
    for name in SHADERS:
        path = root / "libraries/sim/src/shaders" / name
        original = path.read_text(encoding="utf-8")
        if "#version 420 core" in original:
            if original.count("#version 420 core") != 1:
                raise AndroidGraphicsPatchError(name + ": unexpected number of GLSL declarations.")
            updated = original.replace("#version 420 core", SHADER_PROLOGUE, 1)
            changes.append(name + ": convert GLSL 4.20 core to GLSL ES 3.20")
        elif SHADER_PROLOGUE in original:
            updated = original
        else:
            raise AndroidGraphicsPatchError(name + ": unsupported shader source; no files written.")
        staged[path] = updated
        shaders[name] = updated

    # All source markers are checked before any source file is rewritten.
    for path, content in staged.items():
        path.write_text(content, encoding="utf-8")

    if shader_output is not None:
        output = Path(shader_output).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        for name, text in shaders.items():
            lines = text.splitlines()
            if lines and lines[0].strip() == 'R""(':
                lines = lines[1:]
            if lines and lines[-1].strip() == ')""':
                lines = lines[:-1]
            dest = output / (name.replace(".glsl", "." + SHADERS[name]))
            dest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "libntr_commit_expected": LIBNTR_COMMIT,
        "source_root": str(root),
        "changes": changes,
        "shader_count": len(SHADERS),
        "status": "GLES 3.2 source/shader preparation only; game Android target not yet configured",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--shader-output")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = prepare_android_graphics(args.source_root, args.shader_output)
    except (OSError, AndroidGraphicsPatchError) as exc:
        print("Android graphics preparation failed: " + str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Android GLES preparation: " + str(report["status"]))
        for item in report["changes"]:
            print("- " + item)
        print("Shader sources exported: " + str(report["shader_count"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
