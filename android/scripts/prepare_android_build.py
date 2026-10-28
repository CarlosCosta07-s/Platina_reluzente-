#!/usr/bin/env python3
"""Prepare the pinned decompilation and libntr for an Android NDK cross-build."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PARENT_SHA = "35067868f64f23d25d17ac3e536cfdd9a7f40523"
LIBNTR_SHA = "1555d911ac80c0190ac1c321f99f1323de8b3c09"
OLD_CHOICE = "choices: ['arm', 'win64', 'linux', 'nx']"
NEW_CHOICE = "choices: ['arm', 'win64', 'linux', 'nx', 'android']"


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if new in text:
        if text.count(new) != 1:
            raise PatchError(f"{label}: duplicate patched marker")
        return text, False
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly one original marker")
    return text.replace(old, new, 1), True


def check_pin(root: Path, expected: str, label: str) -> None:
    if (root / ".git").exists():
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=False)
        if r.returncode == 0 and r.stdout.strip() != expected:
            raise PatchError(f"{label} revision mismatch: {r.stdout.strip()}")


def add_target_option(path: Path) -> bool:
    text, changed = replace_once(path.read_text(encoding="utf-8"),
                                 OLD_CHOICE, NEW_CHOICE, str(path))
    path.write_text(text, encoding="utf-8")
    return changed


def patch_root(root: Path) -> list[str]:
    changes = []
    if add_target_option(root / "meson.options"):
        changes.append("parent Meson: add android target")

    path = root / "meson.build"
    text = path.read_text(encoding="utf-8")

    # NASM/Yasm only supports desktop architectures here. Android uses the NDK
    # integrated assembler for the preprocessed trainer AI source instead.
    text, changed = replace_once(
        text, "project('pokeplatinum', ['c', 'cpp', 'nasm'],",
        "project('pokeplatinum', ['c', 'cpp'],", "Android optional NASM language")
    if changed:
        changes.append("parent Meson: make NASM desktop-only")
    target_line = "build_target = get_option('build_target')\n\n"
    target_block = (
        target_line + "if (build_target != 'android')\n"
        "    add_languages('nasm', required: true)\n"
        "endif\n\n"
    )
    text, changed = replace_once(text, target_line, target_block, "Android conditional NASM detection")
    if changed:
        changes.append("parent Meson: skip unsupported NASM detection on Android")

    asm_start = "else\ntrainer_ai_ss = custom_target("
    asm_new = """elif (build_target == 'android')
trainer_ai_ss = custom_target(
    'trainer_ai_script.ss',
    output: 'trainer_ai_script.ss',
    input: files('src/battle/trainer_ai/script.s'),
    command: ['gcc', '-D__ASSEMBLER__',
        '-I', meson.global_source_root() / 'asm',
        '-I', meson.global_build_root(),
        '-I', meson.global_source_root() / 'include',
        '-MD', '-MF', '@DEPFILE@', '-E', '-nostdinc', '-'],
    depfile: '@BASENAME@.d',
    capture: true,
    feed: true
)
trainer_ai_o = custom_target(
    'trainer_ai_script.o',
    output: 'trainer_ai_script.o',
    input: trainer_ai_ss,
    command: ['aarch64-linux-android24-clang',
        '-I', meson.global_source_root() / 'asm',
        '-I', meson.global_build_root(),
        '-I', meson.global_source_root() / 'include',
        '-MD', '-MF', '@DEPFILE@', '-c', '-x', 'assembler',
        '-o', '@OUTPUT@', '@INPUT@'],
    depfile: '@BASENAME@.d'
)
else
trainer_ai_ss = custom_target("""
    if "elif (build_target == 'android')\ntrainer_ai_ss = custom_target(" not in text:
        text, changed = replace_once(text, asm_start, asm_new, "trainer AI Android assembler")
        if changed:
            changes.append("parent Meson: cross-assemble trainer AI for AArch64")

    android_main = "if (build_target == 'android')\nmain = shared_library('main',"
    if android_main not in text:
        linux = "if (build_target == 'linux')\nmain = executable('main',"
        start = text.find(linux)
        end = text.find("if (build_target == 'win64')", start)
        if start < 0 or end < 0:
            raise PatchError("parent Meson: Linux executable target boundaries missing")
        block = text[start:end]
        android_block = block.replace(
            "if (build_target == 'linux')\nmain = executable('main',",
            "if (build_target == 'android')\nmain = shared_library('main',", 1)
        android_block = android_block.replace("    native: true", "    native: false", 1)
        android_block = android_block.replace(
            "    native: false\n)",
            "    native: false,\n    install: false\n)", 1)
        if android_block == block or "shared_library('main'" not in android_block:
            raise PatchError("parent Meson: unable to prepare libmain.so target")
        text = text[:start] + android_block + text[start:]
        changes.append("parent Meson: add libmain.so shared-library target")

    old_pic = "if(build_target == 'nx')\n    pokeplatinum_args += '-fPIC'\nendif"
    new_pic = "if(build_target == 'nx' or build_target == 'android')\n    pokeplatinum_args += '-fPIC'\nendif"
    text, changed = replace_once(text, old_pic, new_pic, "parent Android PIC")
    if changed:
        changes.append("parent Meson: enable PIC for Android")
    path.write_text(text, encoding="utf-8")
    return changes


def patch_sdk_project(root: Path, name: str, args_name: str, dwc: bool = False) -> list[str]:
    changes = []
    if add_target_option(root / "meson.options"):
        changes.append(name + ": add android target")
    path = root / "meson.build"
    text = path.read_text(encoding="utf-8")
    if dwc:
        for arg in ("c_args", "nitrodwc_args"):
            old = "if (build_target == 'arm')\nadd_project_arguments(" + arg + ","
            new = "if (build_target == 'arm' or build_target == 'android')\nadd_project_arguments(" + arg + ","
            text, changed = replace_once(text, old, new, name + " cross compiler")
            if changed:
                changes.append(name + ": use cross compiler for Android")
    marker = "if (build_target == 'android')\n    " + args_name + " += ["
    if marker not in text:
        linux = "if (build_target == 'linux')\n    " + args_name + " += ["
        start = text.find(linux)
        end = text.find("\nendif", start)
        if start < 0 or end < 0:
            raise PatchError(name + ": Linux SDK flag block missing")
        end += len("\nendif")
        addition = (
            "\n\nif (build_target == 'android')\n    " + args_name + " += [\n"
            "        '-DSDK_PORT', '-DSDK_AARCH64', '-DSDK_BUILD_ANDROID',\n"
            "        '-DSDK_64BIT', '-D_NITRO',\n"
            "    ]\nendif"
        )
        text = text[:end] + addition + text[end:]
        changes.append(name + ": add Android AArch64 SDK flags")
    path.write_text(text, encoding="utf-8")
    return changes


def patch_libntr(root: Path) -> list[str]:
    changes = []
    opt = root / "meson.options"
    options, changed = replace_once(opt.read_text(encoding="utf-8"), OLD_CHOICE, NEW_CHOICE, "libntr build_target")
    if changed:
        changes.append("libntr: add android target")
    if "option('android_sdl2_libdir'" not in options:
        options += (
            "\noption('android_sdl2_libdir', type: 'string', value: '', description: 'NDK SDL2 library path')\n"
            "option('android_enet_libdir', type: 'string', value: '', description: 'NDK ENet library path')\n"
        )
        changes.append("libntr: add NDK dependency library paths")
    opt.write_text(options, encoding="utf-8")

    path = root / "meson.build"
    text = path.read_text(encoding="utf-8")

    # libntr itself also declares NASM as a required Meson language. As with
    # the parent project, keep it for desktop and skip detection on Android.
    text, changed = replace_once(
        text, "project('libntr', 'c', 'cpp', 'nasm',",
        "project('libntr', 'c', 'cpp',", "libntr optional NASM language")
    if changed:
        changes.append("libntr: make NASM desktop-only")
    libntr_target_line = "build_target = get_option('build_target')\n"
    libntr_target_block = (
        libntr_target_line + "if (build_target != 'android')\n"
        "    add_languages('nasm', required: true)\n"
        "endif\n"
    )
    text, changed = replace_once(text, libntr_target_line, libntr_target_block,
                                 "libntr conditional NASM detection")
    if changed:
        changes.append("libntr: skip unsupported NASM detection on Android")

    if "if (build_target == 'android')\n    nitrosdk_args +=" not in text:
        text, changed = replace_once(
            text, "if (build_target == 'nx')\n    nitrosdk_args += [",
            "if (build_target == 'android')\n    nitrosdk_args += [\n"
            "        '-DSDK_PORT', '-DSDK_AARCH64', '-DSDK_BUILD_ANDROID',\n"
            "        '-DSDK_64BIT', '-D_NITRO',\n"
            "    ]\nendif\n\nif (build_target == 'nx')\n    nitrosdk_args += [",
            "libntr Android SDK flags")
        if changed:
            changes.append("libntr: add Android AArch64 SDK flags")
    path.write_text(text, encoding="utf-8")

    sim_path = root / "libraries/sim/meson.build"
    sim = sim_path.read_text(encoding="utf-8")
    if "dirs: get_option('android_sdl2_libdir')" not in sim:
        marker = "sdl2_lib = meson.get_compiler('c').find_library('SDL2')\n"
        if sim.count(marker) != 1:
            raise PatchError("libntr simulator: SDL2 library marker missing")
        sim = sim.replace(marker, marker + "elif(build_target == 'android')\nsdl2_lib = meson.get_compiler('c').find_library('SDL2', dirs: get_option('android_sdl2_libdir'))\n", 1)
        changes.append("libntr simulator: use NDK SDL2")
    if "dirs: get_option('android_enet_libdir')" not in sim:
        marker = "enet_lib = meson.get_compiler('c').find_library('enet')\n"
        if sim.count(marker) != 1:
            raise PatchError("libntr simulator: ENet library marker missing")
        sim = sim.replace(marker, marker + "elif(build_target == 'android')\nenet_lib = meson.get_compiler('c').find_library('enet', dirs: get_option('android_enet_libdir'))\n", 1)
        changes.append("libntr simulator: use NDK ENet")

    if "include_directories('android_include')" not in sim:
        marker = "libsim_dependencies = [sdl2_dep, enet_dep]"
        replacement = (
            marker + "\n\nif(build_target == 'android')\n"
            "    libsim_includes += include_directories('android_include')\n"
            "    foreach system_library : ['android', 'log', 'EGL', 'GLESv3']\n"
            "        libsim_dependencies += meson.get_compiler('c').find_library(system_library)\n"
            "    endforeach\nendif"
        )
        sim, changed = replace_once(sim, marker, replacement, "libntr Android platform libraries")
        if changed:
            changes.append("libntr simulator: link GLES and Android platform libraries")
    sim = sim.replace("pic: build_target == 'nx',", "pic: build_target == 'nx' or build_target == 'android',", 1)
    sim_path.write_text(sim, encoding="utf-8")

    main_path = root / "libraries/sim/src/sim_main.cpp"
    main, changed = replace_once(
        main_path.read_text(encoding="utf-8"), "#define SDL_MAIN_HANDLED",
        "#ifndef SDK_BUILD_ANDROID\n#define SDL_MAIN_HANDLED\n#endif", "SDL_main entrypoint")
    if changed:
        changes.append("libntr simulator: allow SDLActivity SDL_main entrypoint")
    main_path.write_text(main, encoding="utf-8")
    return changes


def stage_headers(root: Path, sdl: Path, enet: Path) -> None:
    sdl_inc, enet_inc = sdl / "include", enet / "include" / "enet"
    if not sdl_inc.is_dir() or not enet_inc.is_dir():
        raise PatchError("SDL2/ENet source headers missing")
    target = root / "libraries/sim/android_include"
    if target.exists():
        shutil.rmtree(target)
    (target / "SDL2").mkdir(parents=True)
    shutil.copytree(sdl_inc, target / "SDL2", dirs_exist_ok=True)
    shutil.copytree(enet_inc, target / "enet")


def prepare(root_path: str | Path, sdl_path: str | Path, enet_path: str | Path) -> dict[str, object]:
    root, sdl, enet = (Path(p).expanduser().resolve() for p in (root_path, sdl_path, enet_path))
    libntr = root / "subprojects/libntr"
    check_pin(root, PARENT_SHA, "pokeplatinum")
    check_pin(libntr, LIBNTR_SHA, "libntr")
    sdk_projects = {
        "libntrsystem": ("nitrosystem_args", False),
        "libntrwifi": ("nitrowifi_args", False),
        "libntrdwc": ("nitrodwc_args", True),
    }
    required = [root / "meson.options", root / "meson.build",
                libntr / "meson.options", libntr / "meson.build"]
    required.extend(root / "subprojects" / name / "meson.options" for name in sdk_projects)
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise PatchError("Missing Meson source files: " + ", ".join(missing))

    scratch = Path(tempfile.mkdtemp(prefix="android-meson-patch-"))
    staged = scratch / "source"
    try:
        staged.mkdir()
        shutil.copy2(root / "meson.options", staged / "meson.options")
        shutil.copy2(root / "meson.build", staged / "meson.build")
        shutil.copytree(root / "subprojects", staged / "subprojects")
        changes = patch_root(staged)
        changes.extend(patch_libntr(staged / "subprojects/libntr"))
        for name, (arg_name, dwc) in sdk_projects.items():
            changes.extend(patch_sdk_project(staged / "subprojects" / name, name, arg_name, dwc))
        stage_headers(staged / "subprojects/libntr", sdl, enet)

        rels = [
            "meson.options", "meson.build",
            "subprojects/libntr/meson.options", "subprojects/libntr/meson.build",
            "subprojects/libntr/libraries/sim/meson.build",
            "subprojects/libntr/libraries/sim/src/sim_main.cpp",
        ]
        for name in sdk_projects:
            rels += [f"subprojects/{name}/meson.options", f"subprojects/{name}/meson.build"]
        for rel in rels:
            shutil.copy2(staged / rel, root / rel)
        inc_src = staged / "subprojects/libntr/libraries/sim/android_include"
        inc_dst = root / "subprojects/libntr/libraries/sim/android_include"
        if inc_dst.exists():
            shutil.rmtree(inc_dst)
        shutil.copytree(inc_src, inc_dst)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return {
        "pokeplatinum_commit": PARENT_SHA,
        "libntr_commit": LIBNTR_SHA,
        "changes": changes,
        "status": "Android ARM64 Meson target patched; full shared-library compile is the next verification",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--sdl-source", required=True)
    parser.add_argument("--enet-source", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = prepare(args.source_root, args.sdl_source, args.enet_source)
    except (OSError, PatchError) as exc:
        print("Android build preparation failed: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else
          "\n".join(["Android build preparation: " + str(report["status"]),
                    *["- " + str(x) for x in report["changes"]]]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
