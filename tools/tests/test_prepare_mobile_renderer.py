from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts import prepare_mobile_renderer as mobile


class MobileRendererPreparationTests(unittest.TestCase):
    def make_fixture(self, root: Path, assets: Path) -> Path:
        libntr = root / "libntr"
        sim_src = libntr / "libraries" / "sim" / "src"
        sim_src.mkdir(parents=True)
        include = libntr / "include" / "simulator"
        include.mkdir(parents=True)

        (sim_src / "sim_main.cpp").write_text(
            "\n".join(
                (
                    mobile.GLAD_INCLUDE_BLOCK,
                    "#include <SDL2/SDL.h>",
                    mobile.MESSAGE_CALLBACK_ORIGINAL,
                    "void *SIM_RenderInit(void *arg) {",
                    mobile.SIM_GL_ATTRIBUTES_ORIGINAL,
                    "  context = SDL_GL_CreateContext(window);",
                    mobile.GLAD_LOADER_ORIGINAL,
                    "  glClear(GL_COLOR_BUFFER_BIT);",
                    mobile.DEBUG_OUTPUT_ORIGINAL,
                    "  return nullptr;",
                    "}",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (include / "g3_draw.h").write_text(
            mobile.GLAD_INCLUDE_BLOCK + "\n#include <nitro/types.h>\n",
            encoding="utf-8",
        )
        (sim_src / "sim_g3_Texture.cpp").write_text(
            '#include "simulator/sim_g3_Texture.hpp"\n'
            + mobile.TEXTURE_GL_INCLUDE_ORIGINAL
            + "\n",
            encoding="utf-8",
        )
        (sim_src / "g3_draw.cpp").write_text(
            mobile.G3_DRAW_INCLUDE_ORIGINAL
            + "\n"
            + mobile.G3_BORDER_WRAP_ORIGINAL
            + "\n"
            + mobile.DEFERRED_TEXTURE_BLOCK_ORIGINAL
            + "\n",
            encoding="utf-8",
        )
        shader_includes = "\n".join(original for original, _ in mobile.SHADER_INCLUDE_BLOCKS)
        (sim_src / "sim_shaders.cpp").write_text(shader_includes + "\n", encoding="utf-8")
        (sim_src / "meson.build").write_text(
            mobile.GLAD_SOURCE_GUARD + "\n",
            encoding="utf-8",
        )
        (libntr / "libraries" / "sim" / "meson.build").write_text(
            "libsim_args = [ ]\n",
            encoding="utf-8",
        )

        assets.mkdir(parents=True)
        for name in mobile.ASSET_NAMES:
            (assets / name).write_text(f"// fixture asset: {name}\n", encoding="utf-8")
        return libntr

    def test_patcher_adds_gles_source_and_keeps_desktop_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            libntr = self.make_fixture(root, assets)

            self.assertTrue(mobile.prepare_mobile_renderer(libntr, assets))

            main = (libntr / "libraries/sim/src/sim_main.cpp").read_text(encoding="utf-8")
            self.assertIn("#include <simulator/sim_gl.h>", main)
            self.assertIn("#include <simulator/sim_gles3_compat.h>", main)
            self.assertIn("SDL_GL_CONTEXT_PROFILE_ES", main)
            self.assertIn("SDL_GL_CONTEXT_PROFILE_CORE", main)
            self.assertIn("#if !defined(SDK_BUILD_ANDROID) && !defined(SDK_BUILD_IOS)", main)
            callback_start = main.index("void GLAPIENTRY MessageCallback")
            callback_guard_start = main.rfind(
                "#if !defined(SDK_BUILD_ANDROID) && !defined(SDK_BUILD_IOS)",
                0,
                callback_start,
            )
            callback_guard_end = main.index("#endif", callback_start)
            self.assertGreaterEqual(callback_guard_start, 0)
            self.assertGreater(callback_guard_end, callback_start)
            self.assertIn("gladLoadGLLoader(SDL_GL_GetProcAddress);", main)
            self.assertIn("glDebugMessageCallback(MessageCallback, 0);", main)

            header = (libntr / "include/simulator/g3_draw.h").read_text(encoding="utf-8")
            self.assertIn("#include <simulator/sim_gl.h>", header)
            self.assertNotIn("simulator/glad/glad.h", header)

            texture = (libntr / "libraries/sim/src/sim_g3_Texture.cpp").read_text(encoding="utf-8")
            self.assertIn("#include <simulator/sim_gl.h>", texture)
            self.assertNotIn("simulator/glad/glad.h", texture)

            draw = (libntr / "libraries/sim/src/g3_draw.cpp").read_text(encoding="utf-8")
            self.assertIn("#include <simulator/sim_gles3_compat.h>", draw)
            self.assertIn('"clampToBorderS"', draw)
            self.assertIn('"clampToBorderT"', draw)
            self.assertIn("GL_CLAMP_TO_EDGE", draw)
            self.assertIn("GL_CLAMP_TO_BORDER", draw)
            self.assertIn("// Match the pinned Desktop deferred path", draw)

            shaders = (libntr / "libraries/sim/src/sim_shaders.cpp").read_text(encoding="utf-8")
            self.assertIn('shaders/gles300/g2_fragment.glsl', shaders)
            self.assertIn('shaders/g2_fragment.glsl', shaders)

            source_meson = (libntr / "libraries/sim/src/meson.build").read_text(encoding="utf-8")
            self.assertEqual(source_meson, mobile.GLAD_SOURCE_GUARD + "\n")
            parent_meson = (libntr / "libraries/sim/meson.build").read_text(encoding="utf-8")
            self.assertIn("if build_target == 'android'", parent_meson)
            self.assertIn("elif build_target == 'ios'", parent_meson)
            self.assertIn("-DSDK_BUILD_ANDROID", parent_meson)
            self.assertIn("-DSDK_BUILD_IOS", parent_meson)
            self.assertIn("-DIMGUI_IMPL_OPENGL_ES3", parent_meson)

            for name in mobile.ASSET_NAMES:
                destination = (
                    libntr / "include/simulator" / name
                    if name.endswith((".h", ".hpp"))
                    else libntr / "libraries/sim/src/shaders/gles300" / name
                )
                self.assertTrue(destination.is_file())
                if name.endswith(".glsl"):
                    installed_shader = destination.read_text(encoding="utf-8")
                    self.assertTrue(installed_shader.startswith('R""(\\n'))
                    self.assertTrue(installed_shader.endswith('\\n)""\\n'))

    def test_patcher_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            libntr = self.make_fixture(root, assets)
            self.assertTrue(mobile.prepare_mobile_renderer(libntr, assets))
            self.assertFalse(mobile.prepare_mobile_renderer(libntr, assets))

    def test_unknown_upstream_marker_fails_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            libntr = self.make_fixture(root, assets)
            main = libntr / "libraries/sim/src/sim_main.cpp"
            original_main = main.read_text(encoding="utf-8")
            draw = libntr / "libraries/sim/src/g3_draw.cpp"
            draw.write_text("unknown G3 renderer implementation\n", encoding="utf-8")
            original_draw = draw.read_text(encoding="utf-8")

            with self.assertRaises(mobile.MobileRendererPreparationError):
                mobile.prepare_mobile_renderer(libntr, assets)

            self.assertEqual(main.read_text(encoding="utf-8"), original_main)
            self.assertEqual(draw.read_text(encoding="utf-8"), original_draw)
            self.assertFalse((libntr / "include/simulator/sim_gl.h").exists())
            self.assertFalse((libntr / "libraries/sim/src/shaders/gles300").exists())

    def test_symlinked_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            libntr = self.make_fixture(root, assets)
            target = libntr / "libraries/sim/src/sim_main.cpp"
            backup = libntr / "libraries/sim/src/sim_main.real.cpp"
            target.rename(backup)
            target.symlink_to(backup)

            with self.assertRaises(mobile.MobileRendererPreparationError):
                mobile.prepare_mobile_renderer(libntr, assets)


if __name__ == "__main__":
    unittest.main()
