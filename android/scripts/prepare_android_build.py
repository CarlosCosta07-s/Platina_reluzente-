#!/usr/bin/env python3
"""Prepare the pinned decompilation and libntr for an Android NDK cross-build."""
from __future__ import annotations

import argparse
import json
import re
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



def patch_android_copy_script(root: Path) -> list[str]:
    """Allow the upstream copy script to stage assets without running linuxdeploy."""
    script = root / "tools" / "scripts" / "copy_pc_files.sh"
    if not script.is_file():
        if (root / "tools" / "scripts").is_dir():
            raise PatchError("Android runtime staging requires tools/scripts/copy_pc_files.sh")
        return []
    text = script.read_text(encoding="utf-8")
    guard = 'if [[ -f "$BUILDDIR/.android-target" ]]; then'
    if guard in text:
        return []
    marker = 'if [[ "$4" == "-nx" ]]; then'
    if text.count(marker) != 1:
        raise PatchError("copy_pc_files.sh: expected exactly one host packaging branch")
    android_guard = (
        guard + "\n"
        '    echo "Android runtime assets staged; skipping host executable packaging."\n'
        "    exit 0\n"
        "fi\n\n"
    )
    script.write_text(text.replace(marker, android_guard + marker, 1), encoding="utf-8")
    return ["parent copy script: skip host packaging for Android runtime-data target"]



def stage_android_copy_script(root: Path, staged: Path) -> None:
    """Copy the host asset-packaging script into the isolated Android patch tree."""
    relative = Path("tools/scripts/copy_pc_files.sh")
    source = root / relative
    if not source.is_file():
        raise PatchError("Android runtime staging requires tools/scripts/copy_pc_files.sh")
    target = staged / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


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
        android_block, native_replacements = re.subn(
            r"\bnative\s*:\s*true\b", "native: false", android_block, count=1
        )
        if native_replacements != 1:
            raise PatchError("parent Meson: Linux target lacks one native: true setting")
        android_block, install_replacements = re.subn(
            r"(native\s*:\s*false)\s*\)", r"\1,\n    install: false\n)",
            android_block, count=1
        )
        if install_replacements != 1:
            raise PatchError("parent Meson: unable to disable installation for Android shared library")
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
    changes.extend(patch_android_copy_script(root))
    return changes



def patch_ppwlobby_pic(root: Path) -> list[str]:
    """Enable PIC for PPW lobby static libraries when they enter Android libmain.so."""
    lobby_root = root / "lib" / "ppwlobby"
    if not lobby_root.is_dir():
        raise PatchError("parent PPW lobby source directory is missing")
    old = "pic: (build_target == 'nx'),"
    new = "pic: (build_target == 'nx' or build_target == 'android'),"
    changes: list[str] = []
    for path in sorted(lobby_root.rglob("meson.build")):
        text = path.read_text(encoding="utf-8")
        if new in text:
            continue
        count = text.count(old)
        if count == 0:
            continue
        updated = text.replace(old, new)
        path.write_text(updated, encoding="utf-8")
        changes.append(
            "parent PPW lobby: enable Android PIC in " + path.relative_to(root).as_posix()
        )
    if not changes and not any(
        new in path.read_text(encoding="utf-8")
        for path in lobby_root.rglob("meson.build")
    ):
        raise PatchError("parent PPW lobby: no PIC-enabled library marker was found")
    return changes

def patch_sdk_project(root: Path, name: str, args_name: str, dwc: bool = False) -> list[str]:
    changes = []
    if add_target_option(root / "meson.options"):
        changes.append(name + ": add android target")
    path = root / "meson.build"
    text = path.read_text(encoding="utf-8")
    if dwc:
        for arg in ("c_args", "nitrodwc_args"):
            new_pattern = re.compile(
                r"(?m)^if\s*\(\s*build_target\s*==\s*'arm'\s+or\s+build_target\s*==\s*'android'\s*\)\s*\n"
                r"([ \t]*add_project_arguments\(\s*" + re.escape(arg) + r"\s*,)"
            )
            if not new_pattern.search(text):
                old_pattern = re.compile(
                    r"(?m)^if\s*\(\s*build_target\s*==\s*'arm'\s*\)\s*\n"
                    r"([ \t]*add_project_arguments\(\s*" + re.escape(arg) + r"\s*,)"
                )
                text, count = old_pattern.subn(
                    "if (build_target == 'arm' or build_target == 'android')\n\\1",
                    text, count=1
                )
                if count != 1:
                    raise PatchError(name + ": ARM cross-compiler block missing for " + arg)
                changes.append(name + ": use cross compiler for Android (" + arg + ")")
    marker = re.compile(
        r"(?m)^if\s*\(\s*build_target\s*==\s*'android'\s*\)\s*\n"
        r"[ \t]*" + re.escape(args_name) + r"\s*\+=\s*\["
    )
    if not marker.search(text):
        linux_block = re.compile(
            r"(?ms)^if\s*\(\s*build_target\s*==\s*'linux'\s*\)\s*\n"
            r"[ \t]*" + re.escape(args_name) + r"\s*\+=\s*\[.*?^\s*endif\b"
        )
        match = linux_block.search(text)
        if not match:
            raise PatchError(name + ": Linux SDK flag block missing")
        addition = (
            "\n\nif (build_target == 'android')\n    " + args_name + " += [\n"
            "        '-DSDK_PORT', '-DSDK_AARCH64', '-DSDK_BUILD_ANDROID',\n"
            "        '-DSDK_64BIT', '-D_NITRO',\n"
            "    ]\nendif"
        )
        text = text[:match.end()] + addition + text[match.end():]
        changes.append(name + ": add Android AArch64 SDK flags")
    # All NitroSDK subprojects include the shared thread header which references
    # SDL2/SDL_thread.h. Provide the staged SDL headers to each subproject;
    # the simulator-only include path does not propagate across Meson projects.
    include_marker = "add_project_arguments('-I' + (meson.current_source_dir() / '../libntr/libraries/sim/android_include'), language: ['c', 'cpp'])"
    if include_marker not in text:
        # Meson requires add_project_arguments() before any build target in
        # the subproject. Place the platform include directly after the
        # build_target option, not at EOF after static libraries are declared.
        target_line = "build_target = get_option('build_target')\n"
        if text.count(target_line) != 1:
            raise PatchError(name + ": build_target declaration missing/duplicated")
        android_block = (
            target_line
            + "\nif (build_target == 'android')\n"
            + "    " + include_marker + "\n"
            + "endif\n"
        )
        text = text.replace(target_line, android_block, 1)
        changes.append(name + ": expose shared SDL2 headers before Android targets")

    path.write_text(text, encoding="utf-8")

    # Other NitroSDK subprojects contain their own static libraries. They are
    # linked into libmain.so too, so their PIC policy must follow Android as
    # well, not just the libntr subproject.
    library_root = root / "libraries"
    if library_root.is_dir():
        pic_predicates = (
            (
                "pic: build_target == 'nx',",
                "pic: build_target == 'nx' or build_target == 'android',",
            ),
            (
                "pic: (build_target == 'nx'),",
                "pic: (build_target == 'nx' or build_target == 'android'),",
            ),
        )
        for meson_path in sorted(library_root.rglob("meson.build")):
            original = meson_path.read_text(encoding="utf-8")
            updated = original
            for old, new in pic_predicates:
                updated = updated.replace(old, new)
            updated = re.sub(
                r"(?m)^([ \t]*)pic:[ \t]*false,[ \t]*$",
                r"\1pic: build_target == 'android',",
                updated,
            )
            if updated != original:
                meson_path.write_text(updated, encoding="utf-8")
                changes.append(
                    name + ": enable Android PIC in " + meson_path.relative_to(root).as_posix()
                )
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
    old_project = "project('libntr', 'c', 'cpp', 'nasm',\n    default_options:"
    new_project = "project('libntr', 'c', 'cpp',\n    default_options:"
    if old_project in text:
        if text.count(old_project) != 1:
            raise PatchError("libntr: duplicate NASM project declarations")
        text = text.replace(old_project, new_project, 1)
        changed = True
    elif new_project in text:
        changed = False
    else:
        raise PatchError("libntr: expected exact Meson project declaration")
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
    # SDL headers are needed by the common NitroSDK PCH, so add their
    # include directory before any build target is declared in this subproject.
    android_include_marker = (
        "if (build_target == 'android')\n"
        "    add_project_arguments('-I' + join_paths(meson.current_source_dir(), 'libraries/sim/android_include'), language: ['c', 'cpp'])\n"
        "endif\n"
    )
    if "add_project_arguments('-I' + join_paths(meson.current_source_dir(), 'libraries/sim/android_include')" not in text:
        text, changed = replace_once(
            text,
            "build_target = get_option('build_target')\n",
            "build_target = get_option('build_target')\n" + android_include_marker,
            "libntr Android SDL2/ENet headers",
        )
        if changed:
            changes.append("libntr: expose staged SDL2/ENet headers before target declarations")

    # NitroSDK's public typedefs must remain fixed-width on LP64 hosts.
    # Upstream classifies u32/s32 by Linux/NX, which makes unsigned long
    # 64-bit on Android AArch64. Add Android to the 32-bit typedef branches,
    # matching the original DS SDK ABI without changing desktop behavior.
    types_path = root / "include" / "nitro" / "types.h"
    types_text = types_path.read_text(encoding="utf-8")
    fixed_width_pairs = (
        (
            "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX)\ntypedef unsigned int u32;",
            "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX) || defined(SDK_BUILD_ANDROID)\ntypedef unsigned int u32;",
            "Android u32 width",
        ),
        (
            "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX)\ntypedef signed int s32;",
            "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX) || defined(SDK_BUILD_ANDROID)\ntypedef signed int s32;",
            "Android s32 width",
        ),
    )
    for old_type, new_type, label in fixed_width_pairs:
        types_text, type_changed = replace_once(types_text, old_type, new_type, label)
        if type_changed:
            changes.append("libntr: preserve 32-bit " + label)
    types_path.write_text(types_text, encoding="utf-8")

    rom_header_path = root / "libraries" / "card" / "include" / "card_rom.h"
    rom_header = rom_header_path.read_text(encoding="utf-8")
    rom_header, rom_changed = replace_once(
        rom_header,
        "\tu8 cache_buf[CARD_ROM_PAGE_SIZE];",
        "#ifdef SDK_BUILD_ANDROID\n"
        "\tu8 cache_buf[CARD_ROM_PAGE_SIZE] ATTRIBUTE_ALIGN(32);\n"
        "#else\n"
        "\tu8 cache_buf[CARD_ROM_PAGE_SIZE];\n"
        "#endif",
        "Android ROM cache buffer alignment",
    )
    if rom_changed:
        changes.append("libntr: preserve 32-byte CARDRomStat buffer alignment on Android")
    rom_header_path.write_text(rom_header, encoding="utf-8")

    # On Android, host-side callback/function pointers are 64-bit, so the
    # legacy DS-era fixed workspace bound can be smaller than MBFakeWork.
    # Keep the original bound on desktop and raise only the Android allocator
    # contract; MB_FakeGetWorkSize() continues to return the exact sizeof.
    fake_child_header_path = root / "include" / "nitro" / "mb" / "mb_fake_child.h"
    fake_child_header = fake_child_header_path.read_text(encoding="utf-8")
    fake_child_header, fake_child_changed = replace_once(
        fake_child_header,
        "#define MB_FAKE_WORK_SIZE       (0x5f20)",
        "#ifdef SDK_BUILD_ANDROID\n"
        "#define MB_FAKE_WORK_SIZE       (0x7000)\n"
        "#else\n"
        "#define MB_FAKE_WORK_SIZE       (0x5f20)\n"
        "#endif",
        "Android MB fake-work buffer size",
    )
    if fake_child_changed:
        changes.append("libntr: enlarge fake multiplayer workspace only for Android")
    fake_child_header_path.write_text(fake_child_header, encoding="utf-8")

    # WMArm9Buf's padding formula assumes 32-bit pointers. Recalculate the
    # Android-only padding from native pointer/callback sizes so the host
    # structure still fits the fixed WM work-buffer reservation.
    wm_header_path = root / "include" / "nitro" / "wm" / "common" / "wm.h"
    wm_header = wm_header_path.read_text(encoding="utf-8")
    old_wm_reserved = (
        "\tu8 reserved1[WM_ARM9WM_BUF_SIZE -\n"
        "\t             (20 + 4 + 4 * WM_NUM_OF_CALLBACK + 4 + (4 + 4) * WM_NUM_OF_PORT + 6)];"
    )
    new_wm_reserved = (
        "#ifdef SDK_BUILD_ANDROID\n"
        "\tu8 reserved1[WM_ARM9WM_BUF_SIZE -\n"
        "\t    (5 * sizeof(void *) + 2 * sizeof(u16) +\n"
        "\t     ((sizeof(WMCallbackFunc) - ((5 * sizeof(void *) + 2 * sizeof(u16)) % sizeof(WMCallbackFunc))) % sizeof(WMCallbackFunc)) +\n"
        "\t     sizeof(WMCallbackFunc) * WM_NUM_OF_CALLBACK + sizeof(WMCallbackFunc) +\n"
        "\t     (sizeof(WMCallbackFunc) + sizeof(void *)) * WM_NUM_OF_PORT + sizeof(u32) + sizeof(u16))];\n"
        "#else\n"
        "\tu8 reserved1[WM_ARM9WM_BUF_SIZE -\n"
        "\t             (20 + 4 + 4 * WM_NUM_OF_CALLBACK + 4 + (4 + 4) * WM_NUM_OF_PORT + 6)];\n"
        "#endif"
    )
    wm_header, wm_changed = replace_once(
        wm_header, old_wm_reserved, new_wm_reserved, "Android WMArm9Buf pointer-aware layout"
    )
    if wm_changed:
        changes.append("libntr: calculate WMArm9Buf reservation for Android 64-bit pointers")
    wm_header_path.write_text(wm_header, encoding="utf-8")

    path.write_text(text, encoding="utf-8")

    sim_path = root / "libraries/sim/meson.build"
    sim = sim_path.read_text(encoding="utf-8")
    placeholder_libraries = "sdl2_lib = library('SDL2')\nenet_lib = library('enet')\n"
    guarded_libraries = (
        "if (build_target == 'arm')\n"
        "    sdl2_lib = library('SDL2')\n"
        "    enet_lib = library('enet')\n"
        "endif\n"
    )
    if guarded_libraries not in sim:
        sim, changed = replace_once(
            sim, placeholder_libraries, guarded_libraries,
            "libntr simulator empty SDL2/ENet placeholders"
        )
        if changed:
            changes.append("libntr simulator: create empty SDL2/ENet placeholders only for ARM target")
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

    # Select the Android host-machine compiler for libraries produced by the NDK.
    android_library_replacements = (
        (
            "sdl2_lib = meson.get_compiler('c').find_library('SDL2', dirs: get_option('android_sdl2_libdir'))",
            "sdl2_lib = declare_dependency(link_args: ['-L' + get_option('android_sdl2_libdir'), '-lSDL2'])",
            "SDL2 Android link dependency",
        ),
        (
            "sdl2_lib = meson.get_compiler('c', native: false).find_library('SDL2', dirs: get_option('android_sdl2_libdir'))",
            "sdl2_lib = declare_dependency(link_args: ['-L' + get_option('android_sdl2_libdir'), '-lSDL2'])",
            "SDL2 Android link dependency",
        ),
        (
            "enet_lib = meson.get_compiler('c').find_library('enet', dirs: get_option('android_enet_libdir'))",
            "enet_lib = declare_dependency(link_args: ['-L' + get_option('android_enet_libdir'), '-lenet'])",
            "ENet Android link dependency",
        ),
        (
            "enet_lib = meson.get_compiler('c', native: false).find_library('enet', dirs: get_option('android_enet_libdir'))",
            "enet_lib = declare_dependency(link_args: ['-L' + get_option('android_enet_libdir'), '-lenet'])",
            "ENet Android link dependency",
        ),
    )
    for old, new, label in android_library_replacements:
        if old in sim:
            sim, changed = replace_once(sim, old, new, label)
            if changed:
                changes.append("libntr simulator: link " + label)
        elif new not in sim:
            raise PatchError(label + ": expected Android link-dependency marker missing")

    if "libsim_android_includes" not in sim:
        marker = "libsim_dependencies = [sdl2_dep, enet_dep]"
        replacement = (
            marker + "\n\nlibsim_android_includes = []\n\nif(build_target == 'android')\n"
            "    libsim_android_includes += [include_directories('android_include')]\n"
            "    foreach system_library : ['android', 'log', 'EGL', 'GLESv3']\n"
            "        libsim_dependencies += meson.get_compiler('c').find_library(system_library)\n"
            "    endforeach\nendif"
        )
        sim, changed = replace_once(sim, marker, replacement, "libntr Android platform libraries")
        if changed:
            changes.append("libntr simulator: link GLES and Android platform libraries")
    old_system_lookups = (
        "meson.get_compiler('c').find_library(system_library)",
        "meson.get_compiler('c', native: false).find_library(system_library)",
    )
    new_system_lookup = "declare_dependency(link_args: ['-l' + system_library])"
    for old_system_lookup in old_system_lookups:
        if old_system_lookup in sim:
            sim, changed = replace_once(
                sim, old_system_lookup, new_system_lookup, "Android system library lookup"
            )
            if changed:
                changes.append("libntr simulator: link Android system libraries by linker flag")
            break
    else:
        if new_system_lookup not in sim:
            raise PatchError("Android system library lookup: expected target-library lookup marker missing")
    new_include_marker = "include_directories: [nitrosdk_includes, libsim_includes] + libsim_android_includes,"
    if new_include_marker not in sim:
        sim, changed = replace_once(
            sim,
            "include_directories: [nitrosdk_includes, libsim_includes],",
            new_include_marker,
            "libntr Android include paths"
        )
        if changed:
            changes.append("libntr simulator: append Android-specific include paths")
    sim_path.write_text(sim, encoding="utf-8")

    # The Android target links the NitroSDK libraries into one shared object.
    # Upstream normally enables PIC only for NX; broaden only that exact
    # platform predicate while leaving all desktop/handheld targets unchanged.
    pic_predicates = (
        (
            "pic: build_target == 'nx',",
            "pic: build_target == 'nx' or build_target == 'android',",
        ),
        (
            "pic: (build_target == 'nx'),",
            "pic: (build_target == 'nx' or build_target == 'android'),",
        ),
    )
    for meson_path in sorted((root / "libraries").rglob("meson.build")):
        content = meson_path.read_text(encoding="utf-8")
        updated = content
        for old, new in pic_predicates:
            updated = updated.replace(old, new)
        # Some NitroSDK Meson targets hardcode PIC off instead of using the
        # platform predicate. Enable PIC only for Android in those targets;
        # leave ARM/desktop/NX behavior otherwise unchanged.
        updated = re.sub(
            r"(?m)^([ \t]*)pic:[ \t]*false,[ \t]*$",
            r"\1pic: build_target == 'android',",
            updated,
        )
        if updated != content:
            meson_path.write_text(updated, encoding="utf-8")
            changes.append(
                "libntr: enable Android PIC in " + meson_path.relative_to(root).as_posix()
            )

    main_path = root / "libraries/sim/src/sim_main.cpp"
    main, changed = replace_once(
        main_path.read_text(encoding="utf-8"), "#define SDL_MAIN_HANDLED",
        "#ifndef SDK_BUILD_ANDROID\n#define SDL_MAIN_HANDLED\n#endif", "SDL_main entrypoint")
    if changed:
        changes.append("libntr simulator: allow SDLActivity SDL_main entrypoint")
    main_path.write_text(main, encoding="utf-8")

    # Clang used by the Android NDK rejects arithmetic on void*. Preserve
    # the byte-offset semantics by converting VRAM bases to u8* first.
    # The ARM64 NDK Clang compiler rejects arithmetic on void*. Preserve
    # byte addressing for the command-list decoder and extended palette banks.
    command_processor_path = root / "libraries/sim/src/sim_g3_CommandProcessor.cpp"
    command_processor = command_processor_path.read_text(encoding="utf-8")
    command_processor_replacements = (
        (
            "paramPtr = (void *)cmdBlockPtr + 4;",
            "paramPtr = (u8 *)cmdBlockPtr + 4;",
            "Android command-list header pointer offset",
        ),
        (
            "paramPtr += paramSize;",
            "paramPtr = (u8 *)paramPtr + paramSize;",
            "Android command-list parameter offset",
        ),
    )
    for old, new, label in command_processor_replacements:
        command_processor, cmd_changed = replace_once(command_processor, old, new, label)
        if cmd_changed:
            changes.append("libntr simulator: fix " + label + " for Clang")
    command_processor_path.write_text(command_processor, encoding="utf-8")

    g2_path = root / "libraries/sim/src/sim_g2.cpp"
    g2_text = g2_path.read_text(encoding="utf-8")
    old_palette_expr = "(u16 *)(getBgExtPlttVramBank(isSub) +"
    new_palette_expr = "(u16 *)((u8 *)getBgExtPlttVramBank(isSub) +"
    old_palette_count = g2_text.count(old_palette_expr)
    new_palette_count = g2_text.count(new_palette_expr)
    if old_palette_count == 4:
        g2_text = g2_text.replace(old_palette_expr, new_palette_expr)
        changes.append("libntr simulator: use byte pointers for Android extended-palette VRAM offsets")
    elif old_palette_count == 0 and new_palette_count == 4:
        pass
    else:
        raise PatchError("Android extended-palette pointer patch expected four expressions")
    g2_path.write_text(g2_text, encoding="utf-8")

    draw_path = root / "libraries/sim/src/g3_draw.cpp"
    draw = draw_path.read_text(encoding="utf-8")
    draw_replacements = (
        (
            "(u8*)(getTextureVramBank() + s_texImageParam.textureOffset)",
            "((u8*)getTextureVramBank() + s_texImageParam.textureOffset)",
            "Android texture VRAM offset",
        ),
        (
            "(u8*)(getTexPlttVramBank() + s_texPlttBase)",
            "((u8*)getTexPlttVramBank() + s_texPlttBase)",
            "Android texture palette VRAM offset",
        ),
    )
    for old, new, label in draw_replacements:
        draw, draw_changed = replace_once(draw, old, new, label)
        if draw_changed:
            changes.append("libntr simulator: fix " + label + " for Clang")
    draw_path.write_text(draw, encoding="utf-8")
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
                root / "tools/scripts/copy_pc_files.sh",
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
        # The Android PIC patcher also updates static-library targets outside
        # the top-level Meson file; stage the project-owned lobby directory.
        shutil.copytree(root / "lib" / "ppwlobby", staged / "lib" / "ppwlobby")
        stage_android_copy_script(root, staged)
        changes = patch_root(staged)
        changes.extend(patch_ppwlobby_pic(staged))
        changes.extend(patch_libntr(staged / "subprojects/libntr"))
        for name, (arg_name, dwc) in sdk_projects.items():
            changes.extend(patch_sdk_project(staged / "subprojects" / name, name, arg_name, dwc))
        stage_headers(staged / "subprojects/libntr", sdl, enet)

        rels = android_patch_copy_paths(staged, sdk_projects)
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



def android_patch_copy_paths(staged: Path, sdk_projects: dict[str, tuple[str, bool]]) -> list[str]:
    """List every Android-patched source file that must be copied back from staging."""
    rels = [
        "meson.options",
        "meson.build",
        "subprojects/libntr/meson.options",
        "subprojects/libntr/meson.build",
        "subprojects/libntr/include/nitro/types.h",
        "subprojects/libntr/include/nitro/mb/mb_fake_child.h",
        "subprojects/libntr/include/nitro/wm/common/wm.h",
        "subprojects/libntr/libraries/card/include/card_rom.h",
        "subprojects/libntr/libraries/sim/src/sim_main.cpp",
        "tools/scripts/copy_pc_files.sh",
        "subprojects/libntr/libraries/sim/src/sim_g3_CommandProcessor.cpp",
        "subprojects/libntr/libraries/sim/src/sim_g2.cpp",
        "subprojects/libntr/libraries/sim/src/g3_draw.cpp",
    ]
    # patch_libntr rewrites PIC predicates across nested library Meson files.
    # Include every one so those edits actually reach the checkout used by Meson.
    rels.extend(
        path.relative_to(staged).as_posix()
        for path in sorted(
            (staged / "subprojects" / "libntr" / "libraries").rglob("meson.build")
        )
    )
    rels.extend(
        path.relative_to(staged).as_posix()
        for path in sorted((staged / "lib" / "ppwlobby").rglob("meson.build"))
    )
    for name in sdk_projects:
        sdk_root = staged / "subprojects" / name
        rels.extend([f"subprojects/{name}/meson.options", f"subprojects/{name}/meson.build"])
        # patch_sdk_project modifies PIC settings in these nested libraries.
        rels.extend(
            path.relative_to(staged).as_posix()
            for path in sorted(sdk_root.rglob("meson.build"))
        )
    # The recursive Meson list can overlap with explicit staging paths.
    return list(dict.fromkeys(rels))


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
