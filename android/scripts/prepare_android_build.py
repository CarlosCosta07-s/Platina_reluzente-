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

    # libvct and other sibling subprojects include nitro.h, whose Android
    # branch includes SDL2/SDL_thread.h. Arguments added inside libntr do not
    # reach sibling subprojects, so publish this staged include path at the
    # parent project level as well.
    sdl_include_block = (
        "if (build_target == 'android')\n"
        "    add_project_arguments('-I' + join_paths(meson.current_source_dir(), 'subprojects/libntr/libraries/sim/android_include'), language: ['c', 'cpp'])\n"
        "endif"
    )
    if sdl_include_block not in text:
        if text.count(target_block) != 1:
            raise PatchError("parent Meson: cannot locate Android target block to expose SDL2 headers")
        text = text.replace(target_block, target_block + sdl_include_block + "\n\n", 1)
        changes.append("parent Meson: expose staged SDL2 headers to sibling targets")

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



def patch_libvct(root: Path) -> list[str]:
    """Expose staged SDL2 headers to libvct's independent Meson subproject."""
    path = root / "meson.build"
    if not path.is_file():
        raise PatchError(f"libvct Meson source is missing: {path}")

    original = path.read_text(encoding="utf-8")
    marker = "build_target = get_option('build_target')\n"
    include_block = (
        "if (build_target == 'android')\n"
        "    add_project_arguments('-I' + (meson.current_source_dir() / '../libntr/libraries/sim/android_include'), language: ['c', 'cpp'])\n"
        "endif"
    )

    if include_block in original:
        if original.count(include_block) != 1:
            raise PatchError("libvct: duplicated Android SDL include-path patch")
        return []
    if original.count(marker) != 1:
        raise PatchError("libvct: expected exactly one build_target declaration")

    updated = original.replace(marker, marker + "\n" + include_block + "\n", 1)
    path.write_text(updated, encoding="utf-8")
    return ["libvct: expose staged SDL2 headers to Android compilation"]


def patch_android_ppwlobby_c_args(root: Path) -> list[str]:
    """Separate C99 flags for PPW lobby C sources from C++ flags."""
    root_path = root / "lib" / "ppwlobby" / "meson.build"
    ilobby_path = root / "lib" / "ppwlobby" / "libraries" / "ilobby" / "meson.build"
    lobby_path = root / "lib" / "ppwlobby" / "libraries" / "ppwlobby" / "meson.build"
    paths = (root_path, ilobby_path, lobby_path)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise PatchError("PPW lobby Meson sources missing: " + ", ".join(missing))

    old_root_block = (
        "if(build_target == 'arm')\n"
        "    ppwlobby_c_args = [\n"
        "        '-wrap:sdk', '2.0/sp2p3',\n"
        "        '-nothumb'\n"
        "    ]\n"
        "else\n"
        "    ppwlobby_c_args = [\n"
        "        '-fpermissive',\n"
        "        '-std=c++03'\n"
        "    ]\n"
        "endif"
    )
    android_root_block = (
        "if(build_target == 'arm')\n"
        "    ppwlobby_c_args = [\n"
        "        '-wrap:sdk', '2.0/sp2p3',\n"
        "        '-nothumb'\n"
        "    ]\n"
        "    ppwlobby_cpp_args = ppwlobby_c_args\n"
        "elif(build_target == 'android')\n"
        "    # These are C sources; C++ flags make Clang reject the Android build.\n"
        "    ppwlobby_c_args = ['-std=c99']\n"
        "    ppwlobby_cpp_args = ['-fpermissive', '-std=c++03']\n"
        "else\n"
        "    ppwlobby_c_args = [\n"
        "        '-fpermissive',\n"
        "        '-std=c++03'\n"
        "    ]\n"
        "    ppwlobby_cpp_args = ppwlobby_c_args\n"
        "endif"
    )

    staged: dict[Path, str] = {}
    original = root_path.read_text(encoding="utf-8")
    if android_root_block in original:
        if original.count(android_root_block) != 1:
            raise PatchError("PPW lobby C flags: duplicated Android branch")
    else:
        if original.count(old_root_block) != 1:
            raise PatchError("PPW lobby C flags: expected exactly one non-ARM fallback block")
        original = original.replace(old_root_block, android_root_block, 1)
        staged[root_path] = original

    cpp_arg_patches = (
        (ilobby_path, "cpp_args: cpp_args + ppwlobby_c_args,", "cpp_args: cpp_args + ppwlobby_cpp_args,"),
        (lobby_path, "cpp_args: [cpp_args, ppwlobby_c_args],", "cpp_args: [cpp_args, ppwlobby_cpp_args],"),
    )
    for path, old, new in cpp_arg_patches:
        original = path.read_text(encoding="utf-8")
        if new in original:
            if original.count(new) != 1:
                raise PatchError(f"PPW lobby C++ flags: duplicated patched marker in {path}")
            continue
        if original.count(old) != 1:
            raise PatchError(f"PPW lobby C++ flags: expected exactly one C++ argument marker in {path}")
        staged[path] = original.replace(old, new, 1)

    for path, updated in staged.items():
        path.write_text(updated, encoding="utf-8")

    changes = []
    if root_path in staged:
        changes.append("parent PPW lobby: use C99 flags for Android C sources")
    if ilobby_path in staged or lobby_path in staged:
        changes.append("parent PPW lobby: keep C++03 flags on C++ sources only")
    return changes



def patch_android_ppwlobby_map_allocators(root: Path) -> list[str]:
    """Use libc++-conforming allocator value types for PPW lobby std::map aliases.

    The upstream decompilation passes pair<Key, Value> to std::map, but
    std::map::value_type is pair<const Key, Value>. libc++ rejects the mismatch
    at compile time, so adjust only the isolated Android build source tree.
    """
    replacements: dict[str, tuple[tuple[str, str], ...]] = {
        "lib/ppwlobby/include/ilobby/class_ov66_02243B64_sub1.h": (
            (
                "PPW_Allocator<std::pair<u32, UnkClass_ov66_02243B64_Sub1_Sub1> >",
                "PPW_Allocator<std::pair<const u32, UnkClass_ov66_02243B64_Sub1_Sub1> >",
            ),
        ),
        "lib/ppwlobby/include/ilobby/dwci_lobbydata.h": (
            (
                "PPW_Allocator<std::pair<s32, PPWString> >",
                "PPW_Allocator<std::pair<const s32, PPWString> >",
            ),
            (
                "PPW_Allocator<std::pair<PPWString, UnkClass_ov66_02243B64_SubStruct0> >",
                "PPW_Allocator<std::pair<const PPWString, UnkClass_ov66_02243B64_SubStruct0> >",
            ),
        ),
    }

    staged: dict[Path, str] = {}
    for relative, pairs in replacements.items():
        path = root / relative
        if not path.is_file():
            raise PatchError(f"PPW lobby map allocator header missing: {path}")
        original = path.read_text(encoding="utf-8")
        updated = original
        for old, new in pairs:
            if new in updated:
                if updated.count(new) != 1 or old in updated:
                    raise PatchError(f"PPW lobby map allocator patch is ambiguous in {path}")
                continue
            if updated.count(old) != 1:
                raise PatchError(f"PPW lobby map allocator marker missing or duplicated in {path}: {old}")
            updated = updated.replace(old, new, 1)
        if updated != original:
            staged[path] = updated

    # Validate every expected marker before writing either header.
    for path, updated in staged.items():
        path.write_text(updated, encoding="utf-8")
    return [
        "PPW lobby: use libc++-compatible std::map allocator value types in "
        + path.relative_to(root).as_posix()
        for path in sorted(staged)
    ]

def patch_android_ppwlobby_stdlib_compat(root: Path) -> list[str]:
    """Adapt PPW lobby's legacy allocators and opaque callback IDs to libc++/ARM64."""
    base_path = root / "lib" / "ppwlobby" / "include" / "ilobby" / "dwci_lobbybase.h"
    source_patches = {
        root / "lib" / "ppwlobby" / "libraries" / "ilobby" / "src" / "dwci_lobby.cpp": (
            ("(u32)param6", "PPW_CallbackParamId(param6)", 6),
            ("(u32)param4", "PPW_CallbackParamId(param4)", 4),
            ("(u32)param7", "PPW_CallbackParamId(param7)", 2),
        ),
        root / "lib" / "ppwlobby" / "libraries" / "ppwlobby" / "src" / "ppw_lobby.cpp": (
            ("(PPW_LOBBY_CHANNEL_KIND)(u32)param3",
             "(PPW_LOBBY_CHANNEL_KIND)PPW_CallbackParamId(param3)", 3),
        ),
    }
    required = [base_path, *source_patches.keys()]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise PatchError("PPW lobby ARM64 compatibility sources missing: " + ", ".join(missing))

    original_base = base_path.read_text(encoding="utf-8")
    updated_base = original_base
    if "#include <stdint.h>" not in updated_base:
        limits_marker = "#include <limits>\n"
        if updated_base.count(limits_marker) != 1:
            raise PatchError("PPW allocator header: expected exactly one <limits> include")
        updated_base = updated_base.replace(
            limits_marker, limits_marker + "#include <stdint.h>\n", 1
        )

    compat_block = (
        "template <class T, class U>\n"
        "inline bool operator==(const PPW_Allocator<T> &, const PPW_Allocator<U> &) throw()\n"
        "{\n"
        "    // All PPW allocators use the same DWC allocation domain.\n"
        "    return true;\n"
        "}\n\n"
        "template <class T, class U>\n"
        "inline bool operator!=(const PPW_Allocator<T> &, const PPW_Allocator<U> &) throw()\n"
        "{\n"
        "    return false;\n"
        "}\n\n"
        "// Legacy callback APIs carry 32-bit callback IDs in opaque void* values.\n"
        "// Decode the integer-shaped token through uintptr_t so ARM64 Clang accepts it.\n"
        "inline u32 PPW_CallbackParamId(void *param) throw()\n"
        "{\n"
        "    return static_cast<u32>(reinterpret_cast<uintptr_t>(param));\n"
        "}\n\n"
        "#endif // ILOBBY_LOBBYBASE_H"
    )
    if compat_block in updated_base:
        if updated_base.count(compat_block) != 1:
            raise PatchError("PPW allocator header: duplicated Android compatibility helpers")
        if updated_base.count("#include <stdint.h>") != 1:
            raise PatchError("PPW allocator header: duplicated <stdint.h> include")
    else:
        end_marker = "#endif // ILOBBY_LOBBYBASE_H"
        if updated_base.count(end_marker) != 1:
            raise PatchError("PPW allocator header: final include guard marker missing or duplicated")
        updated_base = updated_base.replace(end_marker, compat_block, 1)

    staged: dict[Path, str] = {}
    if updated_base != original_base:
        staged[base_path] = updated_base

    for path, replacements in source_patches.items():
        original = path.read_text(encoding="utf-8")
        updated = original
        for old, new, expected_count in replacements:
            new_count = updated.count(new)
            old_count = updated.count(old)
            if new_count == expected_count and old_count == 0:
                continue
            if old_count != expected_count or new_count != 0:
                raise PatchError(
                    f"PPW callback token patch is ambiguous in {path}: {old!r}; "
                    f"expected {expected_count} originals or {expected_count} replacements"
                )
            updated = updated.replace(old, new)
        if updated != original:
            staged[path] = updated

    # Validate all markers before updating any file in the isolated checkout.
    for path, updated in staged.items():
        path.write_text(updated, encoding="utf-8")

    messages = []
    if base_path in staged:
        messages.append("PPW lobby: add libc++ allocator equality and ARM64 callback-token helpers")
    if any(path in staged for path in source_patches):
        messages.append("PPW lobby: decode opaque 32-bit callback IDs through uintptr_t")
    return messages


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



def patch_sdk_g3d_inline_linkage(root: Path) -> list[str]:
    """Give SDK_PORT inline declarations the same internal linkage as their definitions."""
    g3d_root = root / "include" / "nnsys" / "g3d"
    if not g3d_root.is_dir():
        raise PatchError(f"Required G3D header directory is missing: {g3d_root}")

    changes: list[str] = []
    guard = ("#ifdef SDK_PORT", "static", "#endif")
    inline_include_pattern = re.compile(r"(?m)^[ \t]*#include[ \t]*<[^>\n]*_inline\.h>[ \t]*$")
    declaration_pattern = re.compile(
        r"^([ \t]*)(NNS_G3D_INLINE(?:_DECL)?|NNS_G3D_RES_INLINE)(?=[ \t]).*;[ \t]*$"
    )
    legacy_macro_block = (
        "#if defined(SDK_PORT)\n"
        "#define NNS_G3D_INLINE_DECL static NNS_G3D_INLINE\n"
        "#else\n"
        "#define NNS_G3D_INLINE_DECL NNS_G3D_INLINE\n"
        "#endif"
    )
    cleanup_pattern = re.compile(r"(?m)^[ \t]*#undef NNS_G3D_INLINE_DECL[ \t]*\n?")

    for path in sorted(g3d_root.rglob("*.h")):
        original = path.read_text(encoding="utf-8")
        if not inline_include_pattern.search(original):
            continue

        # Normalize headers touched by the first patch revision before applying
        # the complete rule to every declaration/definition pair in this SDK.
        normalized = original
        if legacy_macro_block in normalized:
            normalized = normalized.replace(legacy_macro_block, "", 1)
        normalized = cleanup_pattern.sub("", normalized)
        normalized = normalized.replace("NNS_G3D_INLINE_DECL", "NNS_G3D_INLINE")

        output: list[str] = []
        inserted = 0
        for line in normalized.splitlines(keepends=True):
            body = line.rstrip("\r\n")
            match = declaration_pattern.match(body)
            if match:
                indent = match.group(1)
                prior = [entry.rstrip("\r\n") for entry in output[-3:]]
                expected_guard = [indent + item for item in guard]
                if prior != expected_guard:
                    output.extend(indent + item + "\n" for item in guard)
                    inserted += 1
            output.append(line)

        updated = "".join(output)
        # Only edit declarations before the corresponding inline implementation
        # include. Headers without such prototypes are naturally left untouched.
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changes.append(
                "libntrsystem: align SDK_PORT inline declaration linkage in "
                + path.relative_to(g3d_root).as_posix()
                + f" ({inserted} declarations)"
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

    # Android's SDL headers are staged both as SDL2/SDL_thread.h (for legacy
    # call sites) and as SDL_thread.h (for the shared Nitro thread header).
    # Select the direct include only on Android; desktop behavior is unchanged.
    thread_header_path = root / "include" / "nitro" / "os" / "common" / "thread.h"
    thread_header = thread_header_path.read_text(encoding="utf-8")
    old_sdl_thread_include = "#ifdef SDK_PORT\n#include <SDL2/SDL_thread.h>\n#endif"
    new_sdl_thread_include = (
        "#ifdef SDK_PORT\n"
        "#if defined(SDK_BUILD_ANDROID)\n"
        "#include <SDL_thread.h>\n"
        "#else\n"
        "#include <SDL2/SDL_thread.h>\n"
        "#endif\n"
        "#endif"
    )
    if new_sdl_thread_include not in thread_header:
        thread_header, thread_changed = replace_once(
            thread_header, old_sdl_thread_include, new_sdl_thread_include,
            "libntr Android SDL thread header",
        )
        if thread_changed:
            changes.append("libntr: use directly staged SDL_thread.h on Android")
    thread_header_path.write_text(thread_header, encoding="utf-8")

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

    # On Android the native renderer is started by SDLActivity. Load the
    # runtime from app-private storage, and pass the user's imported ROM
    # path to the same native header reader used by desktop.
    sim_source = main_path.read_text(encoding="utf-8")
    include_old = "#include <SDL2/SDL_events.h>"
    include_new = (
        "#include <SDL2/SDL_events.h>\n"
        "#ifdef SDK_BUILD_ANDROID\n"
        "#include <SDL2/SDL_system.h>\n"
        "#include <unistd.h>\n"
        "#endif"
    )
    sim_source, include_changed = replace_once(
        sim_source, include_old, include_new, "Android SDL internal-storage declarations"
    )
    if include_changed:
        changes.append("libntr simulator: include Android internal-storage API")

    cwd_old = "  // TODO: This broke the linux AppImage build\n  //chdir(SDL_GetBasePath());"
    cwd_new = r"""#ifdef SDK_BUILD_ANDROID
  const char *runtimeStoragePath = SDL_AndroidGetInternalStoragePath();
  if (runtimeStoragePath == NULL || *runtimeStoragePath == '\0') {
    fprintf(stderr, "Android internal storage path is unavailable\n");
    return 1;
  }
  std::string runtimePath = std::string(runtimeStoragePath) + "/pokeplatinum";
  if (chdir(runtimePath.c_str()) != 0) {
    perror("Changing to the game runtime directory");
    return 1;
  }
#else
  // TODO: This broke the linux AppImage build
  //chdir(SDL_GetBasePath());
#endif"""
    sim_source, cwd_changed = replace_once(
        sim_source, cwd_old, cwd_new, "Android runtime working directory"
    )
    if cwd_changed:
        changes.append("libntr simulator: use the extracted runtime directory on Android")

    rom_old = 'romFile = fopen("header.bin", "r");'
    desktop_rom_marker = 'const char *importedRomPath = getenv("PLATINA_IMPORTED_ROM");'
    android_rom_fallback = (
        "#ifdef SDK_BUILD_ANDROID\n"
        "  const char *romStoragePath = SDL_AndroidGetInternalStoragePath();\n"
        "  std::string androidRomPath;\n"
        "  if ((importedRomPath == NULL || importedRomPath[0] == 0) && romStoragePath != NULL) {\n"
        "    androidRomPath = std::string(romStoragePath) + \"/roms/current.nds\";\n"
        "    importedRomPath = androidRomPath.c_str();\n"
        "  }\n"
        "#endif"
    )
    if rom_old in sim_source:
        rom_new = (
            desktop_rom_marker + "\n"
            + android_rom_fallback + "\n"
            + '  romFile = fopen((importedRomPath != NULL && importedRomPath[0] != 0) ? importedRomPath : "header.bin", "rb");'
        )
        sim_source, rom_changed = replace_once(
            sim_source, rom_old, rom_new, "Imported ROM header"
        )
    elif desktop_rom_marker in sim_source:
        # The desktop build preparation may already have installed the same
        # environment-variable handoff. Extend that reader for Android instead
        # of requiring the original header.bin line to still exist.
        if android_rom_fallback in sim_source:
            rom_changed = False
        else:
            sim_source, rom_changed = replace_once(
                sim_source,
                desktop_rom_marker,
                desktop_rom_marker + "\n" + android_rom_fallback,
                "Android fallback for a prepatched desktop ROM reader",
            )
    else:
        raise PatchError(
            "Imported ROM header: neither the original nor desktop-patched ROM reader was found"
        )
    if rom_changed:
        changes.append("libntr simulator: read the imported ROM header on PC and Android")

    main_path.write_text(sim_source, encoding="utf-8")

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



def patch_android_wifi_socket_headers(root: Path) -> list[str]:
    """Expose POSIX socket declarations to the Android target in libntrwifi."""
    path = root / "libraries" / "cps" / "src" / "network.c"
    if not path.is_file():
        raise PatchError(f"Android Wi-Fi port source is missing: {path}")

    original = path.read_text(encoding="utf-8")
    linux_condition = "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX)"
    android_condition = (
        "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX) "
        "|| defined(SDK_BUILD_ANDROID)"
    )
    condition_lines = [line.strip() for line in original.splitlines()]
    if condition_lines.count(android_condition) == 1 and condition_lines.count(linux_condition) == 0:
        return []
    if condition_lines.count(linux_condition) != 1:
        raise PatchError(
            f"{path}: expected exactly one Linux/NX POSIX socket include condition"
        )

    updated = original.replace(linux_condition, android_condition, 1)
    path.write_text(updated, encoding="utf-8")
    return ["libntrwifi: include POSIX socket headers for Android"]


def patch_android_dwc_auth_headers(root: Path) -> list[str]:
    """Patch DWC errno headers and treat the game's text buffers as UTF-16 on Android."""
    auth_root = root / "libraries" / "auth" / "src"
    auth_path = auth_root / "dwc_auth.c"
    cal_path = auth_root / "dwc_cal.c"
    nastime_path = auth_root / "dwc_nastime.c"
    netcheck_path = auth_root / "dwc_netcheck.c"
    paths = (auth_path, cal_path, nastime_path, netcheck_path)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise PatchError("Android DWC sources missing: " + ", ".join(missing))

    helper_block = (
        "#ifdef SDK_BUILD_ANDROID\n"
        "static unsigned long DWCi_Auth_UTF16Length(const unsigned short *text)\n"
        "{\n"
        "    unsigned long length = 0;\n"
        "    if (text != NULL) {\n"
        "        while (text[length] != 0) {\n"
        "            ++length;\n"
        "        }\n"
        "    }\n"
        "    return length;\n"
        "}\n"
        "#endif"
    )
    errno_wchar_original = (
        "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX)\n"
        "#include <errno.h>\n"
        "#include <wchar.h>\n"
        "#endif"
    )
    errno_wchar_android = (
        "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX) || defined(SDK_BUILD_ANDROID)\n"
        "#include <errno.h>\n"
        "#if !defined(SDK_BUILD_ANDROID)\n"
        "#include <wchar.h>\n"
        "#endif\n"
        "#endif"
    )
    changed: list[str] = []

    # dwc_auth.c: errno on Android, but no host wchar_t header; its ingamesn
    # field is an unsigned-short UTF-16 buffer in the DS SDK contract.
    auth = auth_path.read_text(encoding="utf-8")
    if errno_wchar_android not in auth or helper_block not in auth:
        if auth.count(errno_wchar_original) != 1 or errno_wchar_android in auth:
            raise PatchError(f"{auth_path}: expected one recognized DWC errno/wchar include block.")
        auth = auth.replace(errno_wchar_original, errno_wchar_android, 1)
        marker = "#endif\n\n#ifndef SDK_BUILD_ARM"
        if auth.count(marker) != 1:
            raise PatchError(f"{auth_path}: cannot place Android UTF-16 helper safely.")
        auth = auth.replace(marker, "#endif\n\n" + helper_block + "\n\n#ifndef SDK_BUILD_ARM", 1)
        replacements = (
            (
                "      sVar1 = wcslen((wchar_t *)param->ingamesn);",
                "      #ifdef SDK_BUILD_ANDROID\n"
                "      sVar1 = DWCi_Auth_UTF16Length(param->ingamesn);\n"
                "      #else\n"
                "      sVar1 = wcslen((wchar_t *)param->ingamesn);\n"
                "      #endif",
            ),
            (
                "        sVar1 = wcslen((wchar_t*)param->ingamesn);",
                "        #ifdef SDK_BUILD_ANDROID\n"
                "        sVar1 = DWCi_Auth_UTF16Length(param->ingamesn);\n"
                "        #else\n"
                "        sVar1 = wcslen((wchar_t*)param->ingamesn);\n"
                "        #endif",
            ),
        )
        for before, after in replacements:
            if auth.count(before) != 1:
                raise PatchError(f"{auth_path}: expected exactly one ingamesn length call to adapt.")
            auth = auth.replace(before, after, 1)
        if auth.count(helper_block) != 1 or auth.count("DWCi_Auth_UTF16Length(param->ingamesn)") != 2:
            raise PatchError(f"{auth_path}: Android UTF-16 patch validation failed.")
        auth_path.write_text(auth, encoding="utf-8")
        changed.append("libntrdwc: use Android errno and 16-bit ingamesn length compatibility")
    elif auth.count("DWCi_Auth_UTF16Length(param->ingamesn)") != 2:
        raise PatchError(f"{auth_path}: existing Android helper patch is incomplete.")

    # dwc_cal.c: keep wchar.h for desktop Linux only and count the title/NAS
    # data using 16-bit code units in the Android build.
    cal = cal_path.read_text(encoding="utf-8")
    cal_include_original = "#ifdef SDK_BUILD_LINUX\n#include <wchar.h>\n#endif"
    cal_include_android = "#if defined(SDK_BUILD_LINUX) && !defined(SDK_BUILD_ANDROID)\n#include <wchar.h>\n#endif"
    cal_call = "                          sVar1 = wcslen((wchar_t *)(param_2 + 0x7e));"
    cal_android_call = (
        "                          #ifdef SDK_BUILD_ANDROID\n"
        "                          sVar1 = DWCi_Auth_UTF16Length((const unsigned short *)(param_2 + 0x7e));\n"
        "                          #else\n"
        "                          sVar1 = wcslen((wchar_t *)(param_2 + 0x7e));\n"
        "                          #endif"
    )
    if helper_block not in cal or cal_include_android not in cal:
        if cal.count(cal_include_original) != 1 or cal_include_android in cal:
            raise PatchError(f"{cal_path}: expected one recognized Linux wchar.h include block.")
        cal = cal.replace(cal_include_original, cal_include_android + "\n\n" + helper_block, 1)
        if cal.count(cal_call) != 1:
            raise PatchError(f"{cal_path}: expected exactly one calendar UTF-16 length call.")
        cal = cal.replace(cal_call, cal_android_call, 1)
        cal_path.write_text(cal, encoding="utf-8")
        changed.append("libntrdwc: use UTF-16 length compatibility for calendar data")
    elif cal.count("DWCi_Auth_UTF16Length((const unsigned short *)(param_2 + 0x7e))") != 1:
        raise PatchError(f"{cal_path}: existing Android calendar helper patch is incomplete.")

    # dwc_nastime.c uses errno and also includes wchar.h for Linux/NX. Split
    # those includes so Android gets errno without redefining wchar_t.
    nastime = nastime_path.read_text(encoding="utf-8")
    if errno_wchar_android not in nastime:
        if nastime.count(errno_wchar_original) != 1:
            raise PatchError(f"{nastime_path}: expected one recognized errno/wchar include block.")
        nastime = nastime.replace(errno_wchar_original, errno_wchar_android, 1)
        nastime_path.write_text(nastime, encoding="utf-8")
        changed.append("libntrdwc: expose errno and hide wchar.h for Android NAS time")

    # dwc_netcheck.c uses errno but does not need wchar.h.
    netcheck = netcheck_path.read_text(encoding="utf-8")
    netcheck_original = "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX)\n#include <errno.h>\n#endif"
    netcheck_android = "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX) || defined(SDK_BUILD_ANDROID)\n#include <errno.h>\n#endif"
    if netcheck_android not in netcheck:
        if netcheck.count(netcheck_original) != 1:
            raise PatchError(f"{netcheck_path}: expected one recognized errno include block.")
        netcheck = netcheck.replace(netcheck_original, netcheck_android, 1)
        netcheck_path.write_text(netcheck, encoding="utf-8")
        changed.append("libntrdwc: include errno for Android network checks")

    return changed
def stage_headers(root: Path, sdl: Path, enet: Path) -> None:
    sdl_inc, enet_inc = sdl / "include", enet / "include" / "enet"
    if not sdl_inc.is_dir() or not enet_inc.is_dir():
        raise PatchError("SDL2/ENet source headers missing")

    # Catch incomplete SDK checkouts before Meson starts compiling thousands of
    # translation units. These headers are directly required by the Android
    # platform/thread and SDL entrypoint patches.
    required_sdl_headers = ("SDL.h", "SDL_main.h", "SDL_system.h", "SDL_thread.h")
    missing_sdl_headers = [name for name in required_sdl_headers if not (sdl_inc / name).is_file()]
    if missing_sdl_headers:
        raise PatchError("Required SDL2 headers missing: " + ", ".join(missing_sdl_headers))
    if not (enet_inc / "enet.h").is_file():
        raise PatchError("Required ENet header missing: " + str(enet_inc / "enet.h"))

    target = root / "libraries/sim/android_include"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    # Keep both SDL2/SDL_thread.h and SDL_thread.h available to legacy and
    # common Nitro headers that use different include spellings.
    shutil.copytree(sdl_inc, target, dirs_exist_ok=True)
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
    required.append(root / "subprojects" / "libvct" / "meson.build")
    required.append(root / "lib" / "ppwlobby" / "meson.build")
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
        changes.extend(patch_android_ppwlobby_c_args(staged))
        changes.extend(patch_android_ppwlobby_map_allocators(staged))
        changes.extend(patch_android_ppwlobby_stdlib_compat(staged))
        changes.extend(patch_libntr(staged / "subprojects/libntr"))
        changes.extend(patch_libvct(staged / "subprojects/libvct"))
        for name, (arg_name, dwc) in sdk_projects.items():
            sdk_root = staged / "subprojects" / name
            changes.extend(patch_sdk_project(sdk_root, name, arg_name, dwc))
            if name == "libntrsystem":
                changes.extend(patch_sdk_g3d_inline_linkage(sdk_root))
            if name == "libntrwifi":
                changes.extend(patch_android_wifi_socket_headers(sdk_root))
            if name == "libntrdwc":
                changes.extend(patch_android_dwc_auth_headers(sdk_root))
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
        "subprojects/libvct/meson.build",
        "subprojects/libntr/include/nitro/types.h",
        "subprojects/libntr/include/nitro/os/common/thread.h",
        "subprojects/libntr/include/nitro/mb/mb_fake_child.h",
        "subprojects/libntr/include/nitro/wm/common/wm.h",
        "subprojects/libntr/libraries/card/include/card_rom.h",
        "subprojects/libntr/libraries/sim/src/sim_main.cpp",
        "tools/scripts/copy_pc_files.sh",
        "subprojects/libntr/libraries/sim/src/sim_g3_CommandProcessor.cpp",
        "subprojects/libntr/libraries/sim/src/sim_g2.cpp",
        "subprojects/libntr/libraries/sim/src/g3_draw.cpp",
        "lib/ppwlobby/include/ilobby/class_ov66_02243B64_sub1.h",
        "lib/ppwlobby/include/ilobby/dwci_lobbydata.h",
        "lib/ppwlobby/include/ilobby/dwci_lobbybase.h",
        "lib/ppwlobby/libraries/ilobby/src/dwci_lobby.cpp",
        "lib/ppwlobby/libraries/ppwlobby/src/ppw_lobby.cpp",
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
        if name == "libntrsystem":
            # The SDK_PORT inline linkage fix touches every G3D declaration header
            # paired with an *_inline.h implementation, including binres accessors.
            rels.extend(
                path.relative_to(staged).as_posix()
                for path in sorted(
                    (staged / "subprojects/libntrsystem/include/nnsys/g3d").rglob("*.h")
                )
            )
        if name == "libntrwifi":
            rels.append("subprojects/libntrwifi/libraries/cps/src/network.c")
        if name == "libntrdwc":
            rels.extend([
                "subprojects/libntrdwc/libraries/auth/src/dwc_auth.c",
                "subprojects/libntrdwc/libraries/auth/src/dwc_cal.c",
                "subprojects/libntrdwc/libraries/auth/src/dwc_nastime.c",
                "subprojects/libntrdwc/libraries/auth/src/dwc_netcheck.c",
            ])
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
