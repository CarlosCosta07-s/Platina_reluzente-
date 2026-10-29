from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from android.scripts.prepare_android_build import check_pin, PatchError, android_patch_copy_paths, patch_android_copy_script, patch_android_dwc_auth_headers, patch_android_wifi_socket_headers, patch_libntr, patch_libvct, patch_android_ppwlobby_c_args, patch_android_ppwlobby_map_allocators, patch_android_ppwlobby_stdlib_compat, patch_android_sim_config_path, patch_android_trainer_ai_asm_macro_case, patch_ppwlobby_pic, patch_root, patch_sdk_g3d_inline_linkage, patch_sdk_project, stage_android_copy_script, stage_headers

ROOT = """project('pokeplatinum', ['c', 'cpp', 'nasm'],
    version: '1.0')
build_target = get_option('build_target')

else
trainer_ai_ss = custom_target(
    'trainer_ai_script.ss', output: 'trainer_ai_script.ss',
    input: files('src/battle/trainer_ai/script.s'), command: ['gcc'],
    depfile: '@BASENAME@.d', capture: true, feed: true
)
endif
if (build_target == 'linux')
main = executable('main', sources: [game.c], dependencies: [libntr_dep],
    link_with: [game_lib], native: true)
endif
if (build_target == 'win64')
message('windows')
endif
if(build_target == 'nx')
    pokeplatinum_args += '-fPIC'
endif
"""


class AndroidMesonPatchTests(unittest.TestCase):
    def test_stage_headers_copies_required_sdl_layouts_and_enet_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "libntr"
            sdl = Path(tmp) / "SDL"
            enet = Path(tmp) / "enet"
            sdl_include = sdl / "include"
            enet_include = enet / "include" / "enet"
            sdl_include.mkdir(parents=True)
            enet_include.mkdir(parents=True)
            for name in (
                "SDL.h", "SDL_config.h", "SDL_main.h", "SDL_revision.h",
                "SDL_stdinc.h", "SDL_system.h", "SDL_thread.h", "SDL_version.h",
            ):
                (sdl_include / name).write_text("/* fixture */\n", encoding="utf-8")
            (enet_include / "enet.h").write_text("/* fixture */\n", encoding="utf-8")

            stage_headers(root, sdl, enet)

            staged = root / "libraries" / "sim" / "android_include"
            self.assertTrue((staged / "SDL_thread.h").is_file())
            self.assertTrue((staged / "SDL2" / "SDL_thread.h").is_file())
            self.assertTrue((staged / "SDL_system.h").is_file())
            self.assertTrue((staged / "enet" / "enet.h").is_file())

    def test_stage_headers_rejects_missing_required_sdl_header_early(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "libntr"
            sdl = Path(tmp) / "SDL"
            enet = Path(tmp) / "enet"
            sdl_include = sdl / "include"
            enet_include = enet / "include" / "enet"
            sdl_include.mkdir(parents=True)
            enet_include.mkdir(parents=True)
            for name in (
                "SDL.h", "SDL_config.h", "SDL_main.h", "SDL_revision.h",
                "SDL_stdinc.h", "SDL_system.h", "SDL_version.h",
            ):
                (sdl_include / name).write_text("/* fixture */\n", encoding="utf-8")
            (enet_include / "enet.h").write_text("/* fixture */\n", encoding="utf-8")

            with self.assertRaisesRegex(PatchError, "SDL_thread.h"):
                stage_headers(root, sdl, enet)
            self.assertFalse((root / "libraries" / "sim" / "android_include").exists())

    def test_revision_pin_fails_when_git_checkout_cannot_be_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            result = SimpleNamespace(
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository",
            )
            with patch("android.scripts.prepare_android_build.subprocess.run", return_value=result):
                with self.assertRaisesRegex(PatchError, "revision could not be verified"):
                    check_pin(root, "a" * 40, "libvct")

    def test_revision_pin_rejects_a_different_git_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            actual = "b" * 40
            result = SimpleNamespace(returncode=0, stdout=actual + "\n", stderr="")
            with patch("android.scripts.prepare_android_build.subprocess.run", return_value=result):
                with self.assertRaisesRegex(PatchError, "revision mismatch"):
                    check_pin(root, "a" * 40, "libvct")

    def test_stages_android_copy_script_before_patching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "upstream"
            staged = Path(tmp) / "staged"
            source = root / "tools" / "scripts" / "copy_pc_files.sh"
            source.parent.mkdir(parents=True)
            staged.mkdir(parents=True)
            content = 'cp "$BUILDDIR/main" "$OUTPUTDIR/main"\nif [[ "$4" == "-nx" ]]; then\n  echo switch packaging\nfi\n'
            source.write_text(content, encoding="utf-8")

            stage_android_copy_script(root, staged)

            staged_script = staged / "tools" / "scripts" / "copy_pc_files.sh"
            self.assertEqual(content, staged_script.read_text(encoding="utf-8"))
            changes = patch_android_copy_script(staged)
            self.assertEqual(1, len(changes))
            self.assertIn('if [[ -f "$BUILDDIR/.android-target" ]]; then',
                          staged_script.read_text(encoding="utf-8"))

    def test_copy_script_skips_host_packaging_only_after_staging_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "tools" / "scripts" / "copy_pc_files.sh"
            script.parent.mkdir(parents=True)
            script.write_text(
                'cp "$BUILDDIR/main" "$OUTPUTDIR/main"\n'
                'if [[ "$4" == "-nx" ]]; then\n'
                '  echo switch packaging\n'
                'else\n'
                '  echo desktop packaging\n'
                'fi\n',
                encoding="utf-8",
            )
            changes = patch_android_copy_script(root)
            result = script.read_text(encoding="utf-8")
            guard = 'if [[ -f "$BUILDDIR/.android-target" ]]; then'
            self.assertEqual(1, len(changes))
            self.assertIn(guard, result)
            self.assertLess(result.index('cp "$BUILDDIR/main"'), result.index(guard))
            self.assertLess(result.index(guard), result.index('if [[ "$4" == "-nx" ]]'))
            self.assertEqual([], patch_android_copy_script(root))

    def test_android_sim_config_survives_runtime_asset_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "libraries" / "sim" / "src" / "config" / "sim_config.c"
            config.parent.mkdir(parents=True)
            config.write_text(
                '#define SIM_CONFIG_FILE_PATH "./sim_config.ini"\n',
                encoding="utf-8",
            )

            changes = patch_android_sim_config_path(root)

            result = config.read_text(encoding="utf-8")
            self.assertEqual(
                ["libntr simulator: persist Android config beside the replaceable runtime assets"],
                changes,
            )
            self.assertIn(
                '#if defined(SDK_BUILD_ANDROID)\n'
                '#define SIM_CONFIG_FILE_PATH "../sim_config.ini"\n'
                '#else\n'
                '#define SIM_CONFIG_FILE_PATH "./sim_config.ini"\n'
                '#endif',
                result,
            )
            self.assertEqual([], patch_android_sim_config_path(root))


    def test_libvct_receives_android_sdl_include_path_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meson = root / "meson.build"
            meson.write_text(
                "project('libvct', 'c')\n"
                "build_target = get_option('build_target')\n"
                "nitrosdk_dep = dependency('NitroSDK')\n",
                encoding="utf-8",
            )

            changes = patch_libvct(root)
            result = meson.read_text(encoding="utf-8")
            marker = "add_project_arguments('-I' + (meson.current_source_dir() / '../libntr/libraries/sim/android_include')"
            self.assertEqual(
                ["libvct: expose staged SDL2 headers to Android compilation"],
                changes,
            )
            self.assertIn("if (build_target == 'android')", result)
            self.assertIn(marker, result)
            self.assertIn("language: 'c')", result)
            self.assertNotIn("language: ['c', 'cpp']", result)
            self.assertLess(result.index(marker), result.index("nitrosdk_dep = dependency"))
            self.assertEqual([], patch_libvct(root))
            self.assertEqual(1, result.count("android_include"))


    def test_copyback_includes_nested_libntr_meson_files_patched_for_pic(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            card = staged / "subprojects" / "libntr" / "libraries" / "card" / "meson.build"
            nested = staged / "subprojects" / "libntr" / "libraries" / "camera" / "src" / "meson.build"
            ppwlobby = staged / "lib" / "ppwlobby" / "meson.build"
            card.parent.mkdir(parents=True)
            nested.parent.mkdir(parents=True)
            ppwlobby.parent.mkdir(parents=True)
            card.write_text("pic: build_target == 'nx' or build_target == 'android'\n", encoding="utf-8")
            nested.write_text("pic: build_target == 'nx' or build_target == 'android'\n", encoding="utf-8")
            ppwlobby.write_text("fixture\n", encoding="utf-8")

            paths = android_patch_copy_paths(staged, {})

            self.assertIn("subprojects/libntr/libraries/card/meson.build", paths)
            self.assertIn("lib/ppwlobby/meson.build", paths)
            self.assertIn("asm/macros/aicmd.inc", paths)
            self.assertIn("lib/ppwlobby/include/ilobby/class_ov66_02243B64_sub1.h", paths)
            self.assertIn("lib/ppwlobby/include/ilobby/dwci_lobbydata.h", paths)
            self.assertIn("lib/ppwlobby/include/ilobby/dwci_lobbybase.h", paths)
            self.assertIn("lib/ppwlobby/libraries/ilobby/src/dwci_lobby.cpp", paths)
            self.assertIn("lib/ppwlobby/libraries/ppwlobby/src/ppw_lobby.cpp", paths)
            self.assertIn("subprojects/libvct/meson.build", paths)
            self.assertIn("subprojects/libntr/libraries/sim/src/config/sim_config.c", paths)
            self.assertIn("subprojects/libntr/libraries/sim/src/sim_g3_CommandProcessor.cpp", paths)
            self.assertIn("subprojects/libntr/libraries/sim/src/sim_g2.cpp", paths)
            self.assertIn("subprojects/libntr/include/nitro/types.h", paths)
            self.assertIn("subprojects/libntr/include/nitro/os/common/thread.h", paths)
            self.assertIn("subprojects/libntr/include/nitro/mb/mb_fake_child.h", paths)
            self.assertIn("subprojects/libntr/include/nitro/wm/common/wm.h", paths)
            self.assertIn("subprojects/libntr/libraries/card/include/card_rom.h", paths)
            self.assertIn("subprojects/libntr/libraries/camera/src/meson.build", paths)
            sdk_fnd = staged / "subprojects" / "libntrsystem" / "libraries" / "fnd" / "meson.build"
            sdk_fnd.parent.mkdir(parents=True)
            sdk_fnd.write_text("pic: build_target == 'android',\n", encoding="utf-8")
            paths = android_patch_copy_paths(staged, {
                "libntrsystem": ("nitrosystem_args", False),
                "libntrwifi": ("nitrowifi_args", False),
            })
            self.assertIn("subprojects/libntrsystem/libraries/fnd/meson.build", paths)
            self.assertEqual(len(paths), len(set(paths)))

    def test_android_trainer_ai_macro_case_is_compatible_with_clang_assembler(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            macro_file = root / "asm" / "macros" / "aicmd.inc"
            macro_file.parent.mkdir(parents=True)
            original = (
                ".macro IfLoadedinTable table:req, jump:req\\n"
                ".endm\\n"
                ".macro IfLoadedNotinTable table:req, jump:req\\n"
                ".endm\\n"
            )
            macro_file.write_text(original, encoding="utf-8")

            changes = patch_android_trainer_ai_asm_macro_case(root)
            patched = macro_file.read_text(encoding="utf-8")
            self.assertEqual(
                ["Android assembler: match trainer AI macro names to case-sensitive Clang"],
                changes,
            )
            self.assertIn(".macro IfLoadedInTable table:req, jump:req", patched)
            self.assertIn(".macro IfLoadedNotInTable table:req, jump:req", patched)
            self.assertNotIn(".macro IfLoadedinTable table:req, jump:req", patched)
            self.assertNotIn(".macro IfLoadedNotinTable table:req, jump:req", patched)
            self.assertEqual([], patch_android_trainer_ai_asm_macro_case(root))

    def test_android_trainer_ai_macro_patch_rejects_partial_source_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            macro_file = root / "asm" / "macros" / "aicmd.inc"
            macro_file.parent.mkdir(parents=True)
            original = ".macro IfLoadedinTable table:req, jump:req\\n.endm\\n"
            macro_file.write_text(original, encoding="utf-8")

            with self.assertRaisesRegex(PatchError, "expected exactly one declaration"):
                patch_android_trainer_ai_asm_macro_case(root)
            self.assertEqual(original, macro_file.read_text(encoding="utf-8"))

    def test_root_adds_android_shared_target_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "meson.options").write_text(
                "option('build_target', type: 'combo', choices: ['arm', 'win64', 'linux', 'nx'], value: 'arm')\n",
                encoding="utf-8")
            (root / "meson.build").write_text(ROOT, encoding="utf-8")
            macro_include = root / "asm" / "macros" / "aicmd.inc"
            macro_include.parent.mkdir(parents=True)
            macro_include.write_text(
                ".macro IfLoadedinTable table:req, jump:req\\n.endm\\n"
                ".macro IfLoadedNotinTable table:req, jump:req\\n.endm\\n",
                encoding="utf-8",
            )
            changes = patch_root(root)
            second = patch_root(root)
            result = (root / "meson.build").read_text(encoding="utf-8")
            self.assertIn("main = shared_library('main'", result)
            self.assertIn("aarch64-linux-android24-clang", result)
            self.assertIn("native: false", result)
            self.assertIn(
                "add_project_arguments('-I' + join_paths(meson.current_source_dir(), 'subprojects/libntr/libraries/sim/android_include'), language: ['c', 'cpp'])",
                result,
            )
            self.assertTrue(changes)
            self.assertEqual([], second)

    def test_android_ppwlobby_uses_separate_c_and_cpp_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meson = root / "lib" / "ppwlobby" / "meson.build"
            ilobby = root / "lib" / "ppwlobby" / "libraries" / "ilobby" / "meson.build"
            lobby = root / "lib" / "ppwlobby" / "libraries" / "ppwlobby" / "meson.build"
            for path in (meson, ilobby, lobby):
                path.parent.mkdir(parents=True, exist_ok=True)

            meson.write_text(
                """ppwlobby_c_args = []

if(build_target == 'arm')
    ppwlobby_c_args = [
        '-wrap:sdk', '2.0/sp2p3',
        '-nothumb'
    ]
else
    ppwlobby_c_args = [
        '-fpermissive',
        '-std=c++03'
    ]
endif
""",
                encoding="utf-8",
            )
            ilobby.write_text(
                "lib = static_library('ilobby',\n"
                "    c_args: ppwlobby_c_args,\n"
                "    cpp_args: cpp_args + ppwlobby_c_args,\n"
                ")\n",
                encoding="utf-8",
            )
            lobby.write_text(
                "lib = static_library('lobby',\n"
                "    c_args: ppwlobby_c_args,\n"
                "    cpp_args: [cpp_args, ppwlobby_c_args],\n"
                ")\n",
                encoding="utf-8",
            )

            changes = patch_android_ppwlobby_c_args(root)
            result = meson.read_text(encoding="utf-8")
            ilobby_result = ilobby.read_text(encoding="utf-8")
            lobby_result = lobby.read_text(encoding="utf-8")

            self.assertEqual(
                [
                    "parent PPW lobby: use C99 flags for Android C sources",
                    "parent PPW lobby: keep C++03 flags on C++ sources only",
                ],
                changes,
            )
            self.assertIn("ppwlobby_c_args = ['-std=c99']", result)
            self.assertIn("ppwlobby_cpp_args = ['-fpermissive', '-std=c++03']", result)
            self.assertIn("'-std=c++03'", result)  # Existing desktop C++ configuration remains intact.
            self.assertIn("cpp_args: cpp_args + ppwlobby_cpp_args,", ilobby_result)
            self.assertIn("cpp_args: [cpp_args, ppwlobby_cpp_args],", lobby_result)
            self.assertEqual([], patch_android_ppwlobby_c_args(root))


    def test_android_ppwlobby_map_allocators_match_libcxx_value_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            include = root / "lib" / "ppwlobby" / "include" / "ilobby"
            include.mkdir(parents=True)
            first = include / "class_ov66_02243B64_sub1.h"
            second = include / "dwci_lobbydata.h"
            first.write_text(
                "PPW_Allocator<std::pair<u32, UnkClass_ov66_02243B64_Sub1_Sub1> >\n",
                encoding="utf-8",
            )
            second.write_text(
                "PPW_Allocator<std::pair<s32, PPWString> >\n"
                "PPW_Allocator<std::pair<PPWString, UnkClass_ov66_02243B64_SubStruct0> >\n",
                encoding="utf-8",
            )

            changes = patch_android_ppwlobby_map_allocators(root)

            self.assertEqual(2, len(changes))
            first_text = first.read_text(encoding="utf-8")
            second_text = second.read_text(encoding="utf-8")
            self.assertIn(
                "PPW_Allocator<std::pair<const u32, UnkClass_ov66_02243B64_Sub1_Sub1> >",
                first_text,
            )
            self.assertIn("PPW_Allocator<std::pair<const s32, PPWString> >", second_text)
            self.assertIn(
                "PPW_Allocator<std::pair<const PPWString, UnkClass_ov66_02243B64_SubStruct0> >",
                second_text,
            )
            self.assertEqual([], patch_android_ppwlobby_map_allocators(root))


    def test_android_ppwlobby_allocator_and_callback_handles_support_arm64(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "lib" / "ppwlobby" / "include" / "ilobby" / "dwci_lobbybase.h"
            ilobby = root / "lib" / "ppwlobby" / "libraries" / "ilobby" / "src" / "dwci_lobby.cpp"
            lobby = root / "lib" / "ppwlobby" / "libraries" / "ppwlobby" / "src" / "ppw_lobby.cpp"
            for path in (base, ilobby, lobby):
                path.parent.mkdir(parents=True, exist_ok=True)

            base.write_text(
                "#include <limits>\n"
                "template <class T> class PPW_Allocator { };\n"
                "#endif // ILOBBY_LOBBYBASE_H\n",
                encoding="utf-8",
            )
            ilobby.write_text(
                "(u32)param6\n" * 6
                + "(u32)param4\n" * 4
                + "(u32)param7\n" * 2,
                encoding="utf-8",
            )
            lobby.write_text("(PPW_LOBBY_CHANNEL_KIND)(u32)param3\n" * 3, encoding="utf-8")

            changes = patch_android_ppwlobby_stdlib_compat(root)

            base_text = base.read_text(encoding="utf-8")
            ilobby_text = ilobby.read_text(encoding="utf-8")
            lobby_text = lobby.read_text(encoding="utf-8")
            self.assertEqual(
                [
                    "PPW lobby: add libc++ allocator equality and ARM64 callback-token helpers",
                    "PPW lobby: decode opaque 32-bit callback IDs through uintptr_t",
                ],
                changes,
            )
            self.assertIn("#include <stdint.h>", base_text)
            self.assertIn(
                "inline bool operator==(const PPW_Allocator<T> &, const PPW_Allocator<U> &) throw()",
                base_text,
            )
            self.assertIn(
                "inline bool operator!=(const PPW_Allocator<T> &, const PPW_Allocator<U> &) throw()",
                base_text,
            )
            self.assertIn(
                "return static_cast<u32>(reinterpret_cast<uintptr_t>(param));",
                base_text,
            )
            self.assertEqual(6, ilobby_text.count("PPW_CallbackParamId(param6)"))
            self.assertEqual(4, ilobby_text.count("PPW_CallbackParamId(param4)"))
            self.assertEqual(2, ilobby_text.count("PPW_CallbackParamId(param7)"))
            self.assertEqual(3, lobby_text.count("(PPW_LOBBY_CHANNEL_KIND)PPW_CallbackParamId(param3)"))
            self.assertNotIn("(u32)param6", ilobby_text)
            self.assertNotIn("(u32)param3", lobby_text)
            self.assertEqual([], patch_android_ppwlobby_stdlib_compat(root))


    def test_android_ppwlobby_flags_reject_partial_cpp_argument_replacements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meson = root / "lib" / "ppwlobby" / "meson.build"
            ilobby = root / "lib" / "ppwlobby" / "libraries" / "ilobby" / "meson.build"
            lobby = root / "lib" / "ppwlobby" / "libraries" / "ppwlobby" / "meson.build"
            for path in (meson, ilobby, lobby):
                path.parent.mkdir(parents=True, exist_ok=True)

            meson.write_text(
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
                "endif\n",
                encoding="utf-8",
            )
            original_meson = meson.read_text(encoding="utf-8")
            partial_ilobby = (
                "lib = static_library('ilobby',\n"
                "    cpp_args: cpp_args + ppwlobby_cpp_args,\n"
                "    cpp_args: cpp_args + ppwlobby_c_args,\n"
                ")\n"
            )
            ilobby.write_text(partial_ilobby, encoding="utf-8")
            lobby.write_text(
                "lib = static_library('lobby',\n"
                "    cpp_args: [cpp_args, ppwlobby_c_args],\n"
                ")\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(PatchError, "partial or duplicated patch markers"):
                patch_android_ppwlobby_c_args(root)

            self.assertEqual(partial_ilobby, ilobby.read_text(encoding="utf-8"))
            self.assertEqual(original_meson, meson.read_text(encoding="utf-8"))
            self.assertIn("cpp_args: [cpp_args, ppwlobby_c_args]", lobby.read_text(encoding="utf-8"))

    def test_ppwlobby_static_libraries_enable_android_pic_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            enc = root / "lib" / "ppwlobby" / "libraries" / "enc"
            enc.mkdir(parents=True)
            (enc / "meson.build").write_text(
                "libdwcenc = static_library('dwcenc',\n"
                "    pic: (build_target == 'nx'),\n"
                ")\n",
                encoding="utf-8",
            )
            first = patch_ppwlobby_pic(root)
            result = (enc / "meson.build").read_text(encoding="utf-8")
            self.assertIn("pic: (build_target == 'nx' or build_target == 'android')", result)
            self.assertEqual(1, len(first))
            self.assertEqual([], patch_ppwlobby_pic(root))

    def test_libntr_patches_platform_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "meson.options").write_text(
                "option('build_target', type: 'combo', choices: ['arm', 'win64', 'linux', 'nx'], value: 'arm')\n",
                encoding="utf-8")
            (root / "meson.build").write_text(
                """project('libntr', 'c', 'cpp', 'nasm',
    default_options: { 'default_library': 'static', 'prefer_static': false },
    meson_version: '>=1.3.0', version: '4.2.30001')
build_target = get_option('build_target')
if (build_target == 'nx')
    nitrosdk_args += [
        '-DSDK_PORT'
    ]
endif
""",
                encoding="utf-8")
            types_dir = root / "include" / "nitro"
            types_dir.mkdir(parents=True)
            thread_dir = types_dir / "os" / "common"
            thread_dir.mkdir(parents=True)
            thread_path = thread_dir / "thread.h"
            thread_path.write_text(
                "#ifdef SDK_PORT\n#include <SDL2/SDL_thread.h>\n#endif\n",
                encoding="utf-8",
            )
            (types_dir / "types.h").write_text(
                "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX)\n"
                "typedef unsigned int u32;\n#else\ntypedef unsigned long u32;\n#endif\n"
                "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX)\n"
                "typedef signed int s32;\n#else\ntypedef signed long s32;\n#endif\n",
                encoding="utf-8",
            )
            mb_dir = root / "include" / "nitro" / "mb"
            mb_dir.mkdir(parents=True)
            (mb_dir / "mb_fake_child.h").write_text(
                "#define MB_FAKE_WORK_SIZE       (0x5f20)\n",
                encoding="utf-8",
            )
            wm_dir = root / "include" / "nitro" / "wm" / "common"
            wm_dir.mkdir(parents=True)
            (wm_dir / "wm.h").write_text(
                "\tu8 reserved1[WM_ARM9WM_BUF_SIZE -\n"
                "\t             (20 + 4 + 4 * WM_NUM_OF_CALLBACK + 4 + (4 + 4) * WM_NUM_OF_PORT + 6)];",
                encoding="utf-8",
            )
            (root / "libraries/sim").mkdir(parents=True)
            (root / "libraries/sim/meson.build").write_text(
                """libsim_includes = include_directories('include')
sdl2_lib = library('SDL2')
enet_lib = library('enet')
if(build_target == 'linux' or build_target == 'win64')
sdl2_lib = meson.get_compiler('c').find_library('SDL2')
endif
sdl2_dep = declare_dependency(dependencies: [sdl2_lib])
if(build_target == 'linux' or build_target == 'win64')
enet_lib = meson.get_compiler('c').find_library('enet')
endif
enet_dep = declare_dependency(dependencies: [enet_lib])
libsim_dependencies = [sdl2_dep, enet_dep]
libsim = library('sim',
    include_directories: [nitrosdk_includes, libsim_includes],
    pic: build_target == 'nx',
    dependencies: []
)
""",
                encoding="utf-8")
            (root / "libraries/card").mkdir(parents=True)
            (root / "libraries/card/meson.build").write_text(
                "libcard = library('card', pic: build_target == 'nx', sources: [])\n",
                encoding="utf-8",
            )
            card_include = root / "libraries/card/include"
            card_include.mkdir(parents=True)
            (card_include / "card_rom.h").write_text(
                "typedef struct CARDRomStat {\n"
                "\tu32 dummy[5];\n"
                "\tu8 cache_buf[CARD_ROM_PAGE_SIZE];\n"
                "} CARDRomStat;\n",
                encoding="utf-8",
            )
            (root / "libraries/os").mkdir(parents=True)
            (root / "libraries/os/meson.build").write_text(
                "libos = library('os',\n    pic: false,\n    sources: [])\n",
                encoding="utf-8",
            )
            (root / "libraries/sim/src").mkdir(parents=True)
            (root / "libraries/sim/src/sim_main.cpp").write_text(
                "#define SDL_MAIN_HANDLED\n"
                "#include <SDL2/SDL_events.h>\n"
                "#include <string>\n#include <stdio.h>\n#include <stdlib.h>\n"
                "int main(int argc, char **argv) {\n"
                "  // TODO: This broke the linux AppImage build\n"
                "  //chdir(SDL_GetBasePath());\n"
                "  FILE *romFile;\n"
                "  romFile = fopen(\"header.bin\", \"r\");\n"
                "  return 0;\n}\n", encoding="utf-8")
            (root / "libraries/sim/src/sim_g3_CommandProcessor.cpp").write_text(
                "paramPtr = (void *)cmdBlockPtr + 4;\nparamPtr += paramSize;\n", encoding="utf-8")
            (root / "libraries/sim/src/sim_g2.cpp").write_text(
                "a = (u16 *)(getBgExtPlttVramBank(isSub) + n);\n"
                "b = (u16 *)(getBgExtPlttVramBank(isSub) + n);\n"
                "c = (u16 *)(getBgExtPlttVramBank(isSub) + n);\n"
                "d = (u16 *)(getBgExtPlttVramBank(isSub) + n);\n", encoding="utf-8")
            (root / "libraries/sim/src/g3_draw.cpp").write_text(
                "u8 * vramTex = (u8*)(getTextureVramBank() + s_texImageParam.textureOffset);\n"
                "u8 * vramPltt = (u8*)(getTexPlttVramBank() + s_texPlttBase);\n",
                encoding="utf-8")
            # The desktop workflow may already have converted the header.bin
            # reader to PLATINA_IMPORTED_ROM before Android prepares sources.
            with tempfile.TemporaryDirectory() as desktop_tmp:
                desktop_root = Path(desktop_tmp)
                shutil.copytree(root, desktop_root, dirs_exist_ok=True)
                desktop_main_path = desktop_root / "libraries/sim/src/sim_main.cpp"
                desktop_main = desktop_main_path.read_text(encoding="utf-8")
                old_rom_line = '  romFile = fopen("header.bin", "r");'
                desktop_rom_block = (
                    '  const char *importedRomPath = getenv("PLATINA_IMPORTED_ROM");\n'
                    "  if (importedRomPath != NULL && importedRomPath[0] != 0) {\n"
                    '    romFile = fopen(importedRomPath, "rb");\n'
                    "  }\n"
                    "  if (romFile == NULL) {\n"
                    '    romFile = fopen("header.bin", "rb");\n'
                    "  }"
                )
                self.assertEqual(1, desktop_main.count(old_rom_line))
                desktop_main_path.write_text(
                    desktop_main.replace(old_rom_line, desktop_rom_block, 1),
                    encoding="utf-8",
                )
                patch_libntr(desktop_root)
                patched_desktop = desktop_main_path.read_text(encoding="utf-8")
                self.assertIn("SDL_AndroidGetInternalStoragePath", patched_desktop)
                self.assertIn("roms/current.nds", patched_desktop)
                self.assertEqual(1, patched_desktop.count("std::string androidRomPath;"))
                patch_libntr(desktop_root)
                self.assertEqual(
                    1,
                    desktop_main_path.read_text(encoding="utf-8").count("std::string androidRomPath;"),
                )

            changes = patch_libntr(root)
            command_processor = (root / "libraries/sim/src/sim_g3_CommandProcessor.cpp").read_text(encoding="utf-8")
            self.assertIn("paramPtr = (u8 *)cmdBlockPtr + 4;", command_processor)
            self.assertIn("paramPtr = (u8 *)paramPtr + paramSize;", command_processor)
            self.assertNotIn("paramPtr += paramSize;", command_processor)
            g2_text = (root / "libraries/sim/src/sim_g2.cpp").read_text(encoding="utf-8")
            self.assertEqual(g2_text.count("(u8 *)getBgExtPlttVramBank(isSub) +"), 4)
            second_changes = patch_libntr(root)
            self.assertEqual([], [change for change in second_changes if "pointer offset" in change or "extended-palette" in change or "runtime directory" in change or "imported ROM" in change or "internal-storage API" in change])
            sim = (root / "libraries/sim/meson.build").read_text(encoding="utf-8")
            draw = (root / "libraries/sim/src/g3_draw.cpp").read_text(encoding="utf-8")
            self.assertIn("((u8*)getTextureVramBank() + s_texImageParam.textureOffset)", draw)
            self.assertIn("((u8*)getTexPlttVramBank() + s_texPlttBase)", draw)
            self.assertNotIn("getTextureVramBank() + s_texImageParam.textureOffset", draw.replace("((u8*)getTextureVramBank() + s_texImageParam.textureOffset)", ""))
            self.assertIn("android_sdl2_libdir", sim)
            self.assertIn("android_enet_libdir", sim)
            self.assertIn("sdl2_lib = declare_dependency(link_args: ['-L' + get_option('android_sdl2_libdir'), '-lSDL2'])", sim)
            self.assertIn("enet_lib = declare_dependency(link_args: ['-L' + get_option('android_enet_libdir'), '-lenet'])", sim)
            self.assertIn("declare_dependency(link_args: ['-l' + system_library])", sim)
            self.assertIn("GLESv3", sim)
            self.assertIn("or build_target == 'android'", sim)
            card = (root / "libraries/card/meson.build").read_text(encoding="utf-8")
            self.assertIn("pic: build_target == 'nx' or build_target == 'android'", card)
            os_library = (root / "libraries/os/meson.build").read_text(encoding="utf-8")
            self.assertIn("pic: build_target == 'android',", os_library)
            libntr_meson = (root / "meson.build").read_text(encoding="utf-8")
            self.assertIn("SDK_BUILD_ANDROID", libntr_meson)
            sim_main = (root / "libraries/sim/src/sim_main.cpp").read_text(encoding="utf-8")
            self.assertIn("SDL_AndroidGetInternalStoragePath", sim_main)
            self.assertIn("chdir(runtimePath.c_str())", sim_main)
            self.assertIn("*runtimeStoragePath == '\\0'", sim_main)
            self.assertIn('fprintf(stderr, "Android internal storage path is unavailable\\n");', sim_main)
            self.assertIn("PLATINA_IMPORTED_ROM", sim_main)
            self.assertIn("roms/current.nds", sim_main)
            self.assertIn('fopen((importedRomPath != NULL && importedRomPath[0] != 0)', sim_main)
            types_header = (root / "include/nitro/types.h").read_text(encoding="utf-8")
            self.assertIn("SDK_BUILD_NX) || defined(SDK_BUILD_ANDROID)", types_header)
            self.assertIn("typedef unsigned int u32;", types_header)
            self.assertIn("typedef signed int s32;", types_header)
            mb_header = (root / "include/nitro/mb/mb_fake_child.h").read_text(encoding="utf-8")
            self.assertIn("#ifdef SDK_BUILD_ANDROID", mb_header)
            self.assertIn("#define MB_FAKE_WORK_SIZE       (0x7000)", mb_header)
            self.assertIn("#define MB_FAKE_WORK_SIZE       (0x5f20)", mb_header)
            wm_header = (root / "include/nitro/wm/common/wm.h").read_text(encoding="utf-8")
            self.assertIn("#ifdef SDK_BUILD_ANDROID", wm_header)
            self.assertIn("sizeof(WMCallbackFunc) * WM_NUM_OF_CALLBACK", wm_header)
            self.assertIn("(20 + 4 + 4 * WM_NUM_OF_CALLBACK + 4 + (4 + 4) * WM_NUM_OF_PORT + 6)", wm_header)
            rom_header = (root / "libraries/card/include/card_rom.h").read_text(encoding="utf-8")
            self.assertIn("#ifdef SDK_BUILD_ANDROID", rom_header)
            self.assertIn("cache_buf[CARD_ROM_PAGE_SIZE] ATTRIBUTE_ALIGN(32)", rom_header)
            include_arg = "add_project_arguments('-I' + join_paths(meson.current_source_dir(), 'libraries/sim/android_include')"
            self.assertIn(include_arg, libntr_meson)
            thread_result = thread_path.read_text(encoding="utf-8")
            self.assertIn(
                "#if defined(SDK_BUILD_ANDROID)\n#include <SDL_thread.h>\n#else\n#include <SDL2/SDL_thread.h>\n#endif",
                thread_result,
            )
            self.assertIn("libntr: use directly staged SDL_thread.h on Android", changes)
            self.assertLess(libntr_meson.index(include_arg), libntr_meson.index("if (build_target == 'nx')"))
            self.assertNotIn("project('libntr', 'c', 'cpp', 'nasm'", libntr_meson)
            self.assertIn("add_languages('nasm', required: true)", libntr_meson)

    def test_sdk_project_patches_pic_in_nested_libraries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "meson.options").write_text(
                "option('build_target', type: 'combo', choices: ['arm', 'win64', 'linux', 'nx'], value: 'arm')\n",
                encoding="utf-8",
            )
            (root / "meson.build").write_text(
                "build_target = get_option('build_target')\n"
                "if (build_target == 'linux')\n"
                "nitrosystem_args += [\n '-DSDK_BUILD_LINUX'\n]\nendif\n",
                encoding="utf-8",
            )
            fnd = root / "libraries" / "fnd"
            fnd.mkdir(parents=True)
            fnd_file = fnd / "meson.build"
            fnd_file.write_text(
                "libnnsfnd = library('nnsfnd',\n"
                "    pic: build_target == 'nx',\n"
                "    sources: [])\n",
                encoding="utf-8",
            )

            patch_sdk_project(root, "libntrsystem", "nitrosystem_args")

            result = fnd_file.read_text(encoding="utf-8")
            self.assertIn("pic: build_target == 'nx' or build_target == 'android'", result)
            meson_result = (root / "meson.build").read_text(encoding="utf-8")
            self.assertIn("android_include", meson_result)
            self.assertIn("language: ['c', 'cpp']", meson_result)
            self.assertLess(
                meson_result.index("add_project_arguments('-I'"),
                meson_result.index("nitrosystem_args +="),
            )
            second = patch_sdk_project(root, "libntrsystem", "nitrosystem_args")
            self.assertFalse(any("expose shared SDL2 headers" in item for item in second))
            self.assertEqual(1, meson_result.count("android_include"))


    def test_android_dwc_auth_source_includes_errno_and_wchar_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth = root / "libraries" / "auth" / "src" / "dwc_auth.c"
            cal = root / "libraries" / "auth" / "src" / "dwc_cal.c"
            nastime = root / "libraries" / "auth" / "src" / "dwc_nastime.c"
            netcheck = root / "libraries" / "auth" / "src" / "dwc_netcheck.c"
            for path in (auth, cal, nastime, netcheck):
                path.parent.mkdir(parents=True, exist_ok=True)

            auth.write_text(
                "#include <nitro.h>\n"
                "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX)\n"
                "#include <errno.h>\n#include <wchar.h>\n#endif\n\n"
                "#ifndef SDK_BUILD_ARM\n"
                "void fixture(void) {\n"
                "      sVar1 = wcslen((wchar_t *)param->ingamesn);\n"
                "        sVar1 = wcslen((wchar_t*)param->ingamesn);\n"
                "}\n",
                encoding="utf-8",
            )
            cal.write_text(
                "#include <nitro.h>\n"
                "#ifdef SDK_BUILD_LINUX\n#include <wchar.h>\n#endif\n\n"
                "void DWC_Auth_GetCalInfoFromNVRAM(char *aBuf) {}\n"
                "void fixture(void) {\n"
                "                          sVar1 = wcslen((wchar_t *)(param_2 + 0x7e));\n"
                "}\n",
                encoding="utf-8",
            )
            nastime.write_text(
                "#include <nitro.h>\n"
                "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX)\n"
                "#include <errno.h>\n#include <wchar.h>\n#endif\n",
                encoding="utf-8",
            )
            netcheck.write_text(
                "#include <nitro.h>\n"
                "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX)\n"
                "#include <errno.h>\n#endif\n",
                encoding="utf-8",
            )

            changes = patch_android_dwc_auth_headers(root)
            self.assertEqual(
                [
                    "libntrdwc: use Android errno and 16-bit ingamesn length compatibility",
                    "libntrdwc: use UTF-16 length compatibility for calendar data",
                    "libntrdwc: expose errno and hide wchar.h for Android NAS time",
                    "libntrdwc: include errno for Android network checks",
                ],
                changes,
            )

            auth_text = auth.read_text(encoding="utf-8")
            self.assertIn("#include <errno.h>", auth_text)
            self.assertIn("#if !defined(SDK_BUILD_ANDROID)\n#include <wchar.h>\n#endif", auth_text)
            self.assertEqual(2, auth_text.count("DWCi_Auth_UTF16Length(param->ingamesn)"))
            self.assertIn("sVar1 = wcslen((wchar_t *)param->ingamesn);", auth_text)
            self.assertIn("sVar1 = wcslen((wchar_t*)param->ingamesn);", auth_text)

            cal_text = cal.read_text(encoding="utf-8")
            self.assertIn("#if defined(SDK_BUILD_LINUX) && !defined(SDK_BUILD_ANDROID)", cal_text)
            self.assertIn("DWCi_Auth_UTF16Length((const unsigned short *)(param_2 + 0x7e))", cal_text)
            self.assertIn("sVar1 = wcslen((wchar_t *)(param_2 + 0x7e));", cal_text)

            nastime_text = nastime.read_text(encoding="utf-8")
            self.assertIn("#if !defined(SDK_BUILD_ANDROID)\n#include <wchar.h>\n#endif", nastime_text)
            self.assertIn("#include <errno.h>", nastime_text)

            netcheck_text = netcheck.read_text(encoding="utf-8")
            self.assertIn("#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX) || defined(SDK_BUILD_ANDROID)", netcheck_text)
            self.assertIn("#include <errno.h>", netcheck_text)

            self.assertEqual([], patch_android_dwc_auth_headers(root))


    def test_android_wifi_network_source_includes_posix_socket_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "libraries" / "cps" / "src" / "network.c"
            source.parent.mkdir(parents=True)
            source.write_text(
                "#include <nitro.h>\n"
                "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX)\n"
                "#include <sys/socket.h>\n"
                "#include <netinet/in.h>\n"
                "#include <unistd.h>\n"
                "#endif\n",
                encoding="utf-8",
            )

            self.assertEqual(
                ["libntrwifi: include POSIX socket headers for Android"],
                patch_android_wifi_socket_headers(root),
            )
            updated = source.read_text(encoding="utf-8")
            self.assertIn(
                "#if defined(SDK_BUILD_LINUX) || defined(SDK_BUILD_NX) || defined(SDK_BUILD_ANDROID)",
                updated,
            )
            self.assertIn("#include <sys/socket.h>", updated)
            self.assertIn("#include <netinet/in.h>", updated)
            self.assertIn("#include <unistd.h>", updated)
            self.assertEqual([], patch_android_wifi_socket_headers(root))

    def test_android_g3d_inline_declarations_match_static_sdk_port_definitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            g3d = root / "include" / "nnsys" / "g3d"
            fixtures = {
                "kernel.h": (
                    "#include <nnsys/g3d/config.h>\n"
                    "NNS_G3D_INLINE void NNS_TestKernel(void);\n"
                    "#include <nnsys/g3d/kernel_inline.h>\n"
                ),
                "sbc.h": (
                    "#include <nnsys/g3d/config.h>\n"
                    "#include <nnsys/g3d/kernel.h>\n"
                    "NNS_G3D_INLINE BOOL NNS_TestSbc(void);\n"
                    "#include <nnsys/g3d/sbc_inline.h>\n"
                ),
                "glbstate.h": (
                    "#include <nnsys/g3d/config.h>\n"
                    "NNS_G3D_INLINE void NNS_TestGlbstate(void);\n"
                    "#include <nnsys/g3d/glbstate_inline.h>\n"
                ),
                "binres/res_struct_accessor.h": (
                    "#include <nnsys/g3d/config.h>\n"
                    "NNS_G3D_RES_INLINE int NNS_TestResAccessor(void);\n"
                    "#include <nnsys/g3d/binres/res_struct_accessor_inline.h>\n"
                ),
            }
            for name, content in fixtures.items():
                path = g3d / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            first = patch_sdk_g3d_inline_linkage(root)

            self.assertEqual(4, len(first))
            prototypes = {
                "kernel.h": "NNS_G3D_INLINE void NNS_TestKernel(void);",
                "sbc.h": "NNS_G3D_INLINE BOOL NNS_TestSbc(void);",
                "glbstate.h": "NNS_G3D_INLINE void NNS_TestGlbstate(void);",
                "binres/res_struct_accessor.h": "NNS_G3D_RES_INLINE int NNS_TestResAccessor(void);",
            }
            for name, prototype in prototypes.items():
                content = (g3d / name).read_text(encoding="utf-8")
                self.assertNotIn("NNS_G3D_INLINE_DECL", content)
                lines = content.splitlines()
                index = lines.index(prototype)
                self.assertEqual(["#ifdef SDK_PORT", "static", "#endif"], lines[index - 3:index])

            self.assertEqual([], patch_sdk_g3d_inline_linkage(root))


    def test_android_g3d_inline_headers_are_copied_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            for rel in (
                "subprojects/libntrsystem/include/nnsys/g3d/kernel.h",
                "subprojects/libntrsystem/include/nnsys/g3d/sbc.h",
                "subprojects/libntrsystem/include/nnsys/g3d/glbstate.h",
                "subprojects/libntrsystem/include/nnsys/g3d/binres/res_struct_accessor.h",
                "subprojects/libntrwifi/libraries/cps/src/network.c",
                "subprojects/libntrdwc/libraries/auth/src/dwc_auth.c",
                "subprojects/libntrdwc/libraries/auth/src/dwc_cal.c",
                "subprojects/libntrdwc/libraries/auth/src/dwc_nastime.c",
                "subprojects/libntrdwc/libraries/auth/src/dwc_netcheck.c",
            ):
                target = staged / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture", encoding="utf-8")
            paths = android_patch_copy_paths(staged, {
                "libntrsystem": ("nitrosystem_args", False),
                "libntrwifi": ("nitrowifi_args", False),
                "libntrdwc": ("nitrodwc_args", True),
            })
            self.assertIn("subprojects/libntrsystem/include/nnsys/g3d/kernel.h", paths)
            self.assertIn("subprojects/libntrsystem/include/nnsys/g3d/sbc.h", paths)
            self.assertIn("subprojects/libntrsystem/include/nnsys/g3d/glbstate.h", paths)
            self.assertIn("subprojects/libntrsystem/include/nnsys/g3d/binres/res_struct_accessor.h", paths)
            self.assertIn("subprojects/libntrwifi/libraries/cps/src/network.c", paths)
            self.assertIn("subprojects/libntrdwc/libraries/auth/src/dwc_auth.c", paths)
            self.assertIn("subprojects/libntrdwc/libraries/auth/src/dwc_cal.c", paths)
            self.assertIn("subprojects/libntrdwc/libraries/auth/src/dwc_nastime.c", paths)
            self.assertIn("subprojects/libntrdwc/libraries/auth/src/dwc_netcheck.c", paths)

    def test_dwc_uses_cross_compiler_on_android(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "meson.options").write_text(
                "option('build_target', type: 'combo', choices: ['arm', 'win64', 'linux', 'nx'], value: 'arm')\n",
                encoding="utf-8")
            (root / "meson.build").write_text(
                "build_target = get_option('build_target')\n"
                "if (build_target == 'arm')\nadd_project_arguments(c_args,\n"
                " language: 'c',\n native: false\n)\nelse\nadd_project_arguments(c_args,\n"
                " language: 'c',\n native: true\n)\nendif\n"
                "if (build_target == 'linux')\nnitrodwc_args += [\n '-DSDK_BUILD_LINUX'\n]\nendif\n"
                "if (build_target == 'arm')\nadd_project_arguments(nitrodwc_args,\n"
                " language: 'c',\n native: false\n)\nelse\nadd_project_arguments(nitrodwc_args,\n"
                " language: 'c',\n native: true\n)\nendif\n",
                encoding="utf-8")
            patch_sdk_project(root, "libntrdwc", "nitrodwc_args", dwc=True)
            text = (root / "meson.build").read_text(encoding="utf-8")
            self.assertEqual(2, text.count("build_target == 'arm' or build_target == 'android'"))
            self.assertIn("-DSDK_BUILD_ANDROID", text)


if __name__ == "__main__":
    unittest.main()
