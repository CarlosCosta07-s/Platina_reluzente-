from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from android.scripts.prepare_android_build import android_patch_copy_paths, patch_libntr, patch_ppwlobby_pic, patch_root, patch_sdk_project

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
    def test_copyback_includes_nested_libntr_meson_files_patched_for_pic(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            card = staged / "subprojects" / "libntr" / "libraries" / "card" / "meson.build"
            nested = staged / "subprojects" / "libntr" / "libraries" / "camera" / "src" / "meson.build"
            card.parent.mkdir(parents=True)
            nested.parent.mkdir(parents=True)
            card.write_text("pic: build_target == 'nx' or build_target == 'android'\\n", encoding="utf-8")
            nested.write_text("pic: build_target == 'nx' or build_target == 'android'\\n", encoding="utf-8")

            paths = android_patch_copy_paths(staged, {})

            self.assertIn("subprojects/libntr/libraries/card/meson.build", paths)
            self.assertIn("subprojects/libntr/include/nitro/types.h", paths)
            self.assertIn("subprojects/libntr/include/nitro/mb/mb_fake_child.h", paths)
            self.assertIn("subprojects/libntr/libraries/card/include/card_rom.h", paths)
            self.assertIn("subprojects/libntr/libraries/camera/src/meson.build", paths)
            sdk_fnd = staged / "subprojects" / "libntrsystem" / "libraries" / "fnd" / "meson.build"
            sdk_fnd.parent.mkdir(parents=True)
            sdk_fnd.write_text("pic: build_target == 'android',\n", encoding="utf-8")
            paths = android_patch_copy_paths(staged, {"libntrsystem": ("nitrosystem_args", False)})
            self.assertIn("subprojects/libntrsystem/libraries/fnd/meson.build", paths)
            self.assertEqual(len(paths), len(set(paths)))

    def test_root_adds_android_shared_target_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "meson.options").write_text(
                "option('build_target', type: 'combo', choices: ['arm', 'win64', 'linux', 'nx'], value: 'arm')\n",
                encoding="utf-8")
            (root / "meson.build").write_text(ROOT, encoding="utf-8")
            changes = patch_root(root)
            second = patch_root(root)
            result = (root / "meson.build").read_text(encoding="utf-8")
            self.assertIn("main = shared_library('main'", result)
            self.assertIn("aarch64-linux-android24-clang", result)
            self.assertIn("native: false", result)
            self.assertTrue(changes)
            self.assertEqual([], second)

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
                "libcard = library('card', pic: build_target == 'nx', sources: [])\\n",
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
                "#define SDL_MAIN_HANDLED\nint main() { return 0; }\n", encoding="utf-8")
            patch_libntr(root)
            sim = (root / "libraries/sim/meson.build").read_text(encoding="utf-8")
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
            types_header = (root / "include/nitro/types.h").read_text(encoding="utf-8")
            self.assertIn("SDK_BUILD_NX) || defined(SDK_BUILD_ANDROID)", types_header)
            self.assertIn("typedef unsigned int u32;", types_header)
            self.assertIn("typedef signed int s32;", types_header)
            mb_header = (root / "include/nitro/mb/mb_fake_child.h").read_text(encoding="utf-8")
            self.assertIn("#ifdef SDK_BUILD_ANDROID", mb_header)
            self.assertIn("#define MB_FAKE_WORK_SIZE       (0x7000)", mb_header)
            self.assertIn("#define MB_FAKE_WORK_SIZE       (0x5f20)", mb_header)
            rom_header = (root / "libraries/card/include/card_rom.h").read_text(encoding="utf-8")
            self.assertIn("#ifdef SDK_BUILD_ANDROID", rom_header)
            self.assertIn("cache_buf[CARD_ROM_PAGE_SIZE] ATTRIBUTE_ALIGN(32)", rom_header)
            include_arg = "add_project_arguments('-I' + join_paths(meson.current_source_dir(), 'libraries/sim/android_include')"
            self.assertIn(include_arg, libntr_meson)
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

    def test_dwc_uses_cross_compiler_on_android(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "meson.options").write_text(
                "option('build_target', type: 'combo', choices: ['arm', 'win64', 'linux', 'nx'], value: 'arm')\n",
                encoding="utf-8")
            (root / "meson.build").write_text(
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
