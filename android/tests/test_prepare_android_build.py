from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from android.scripts.prepare_android_build import patch_libntr, patch_root, patch_sdk_project

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

    def test_libntr_patches_platform_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "meson.options").write_text(
                "option('build_target', type: 'combo', choices: ['arm', 'win64', 'linux', 'nx'], value: 'arm')\n",
                encoding="utf-8")
            (root / "meson.build").write_text(
                "project('libntr', 'c', 'cpp', 'nasm')\n"
                "build_target = get_option('build_target')\n"
                "if (build_target == 'nx')\n    nitrosdk_args += [\n        '-DSDK_PORT'\n    ]\nendif\n",
                encoding="utf-8")
            (root / "libraries/sim").mkdir(parents=True)
            (root / "libraries/sim/meson.build").write_text(
                "libsim_includes = include_directories('include')\n"
                "sdl2_lib = library('SDL2')\nenet_lib = library('enet')\n"
                "if(build_target == 'linux' or build_target == 'win64')\n"
                "sdl2_lib = meson.get_compiler('c').find_library('SDL2')\nendif\n"
                "sdl2_dep = declare_dependency(dependencies: [sdl2_lib])\n"
                "if(build_target == 'linux' or build_target == 'win64')\n"
                "enet_lib = meson.get_compiler('c').find_library('enet')\nendif\n"
                "enet_dep = declare_dependency(dependencies: [enet_lib])\n"
                "libsim_dependencies = [sdl2_dep, enet_dep]\n"
                "libsim = library('sim', pic: build_target == 'nx')\n",
                encoding="utf-8")
            (root / "libraries/sim/src").mkdir(parents=True)
            (root / "libraries/sim/src/sim_main.cpp").write_text(
                "#define SDL_MAIN_HANDLED\nint main() { return 0; }\n", encoding="utf-8")
            patch_libntr(root)
            sim = (root / "libraries/sim/meson.build").read_text(encoding="utf-8")
            self.assertIn("android_sdl2_libdir", sim)
            self.assertIn("android_enet_libdir", sim)
            self.assertIn("GLESv3", sim)
            self.assertIn("or build_target == 'android'", sim)
            libntr_meson = (root / "meson.build").read_text(encoding="utf-8")
            self.assertIn("SDK_BUILD_ANDROID", libntr_meson)
            self.assertNotIn("project('libntr', 'c', 'cpp', 'nasm'", libntr_meson)
            self.assertIn("add_languages('nasm', required: true)", libntr_meson)

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
