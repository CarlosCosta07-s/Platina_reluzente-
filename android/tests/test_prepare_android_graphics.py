from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from android.scripts.prepare_android_graphics import AndroidGraphicsPatchError, prepare_android_graphics

GLAD = (
    "#ifdef SDK_BUILD_NX\n"
    "#include <glad/glad.h>\n"
    "#else\n"
    "#include <simulator/glad/glad.h>\n"
    "#endif"
)
CONTEXT = (
    "  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 4);\n"
    "  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 2);\n"
    "  SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);"
)
SHADER = 'R""(\n#version 420 core\nvoid main() { gl_Position = vec4(0.0); }\n)""\n'


class PrepareAndroidGraphicsTests(unittest.TestCase):
    def make_source(self, root: Path) -> None:
        (root / "libraries/sim/src/shaders").mkdir(parents=True)
        (root / "include/simulator").mkdir(parents=True)
        (root / "libraries/sim/src/sim_main.cpp").write_text(
            GLAD + "\n" + CONTEXT + "\n  gladLoadGLLoader(SDL_GL_GetProcAddress);\n",
            encoding="utf-8",
        )
        (root / "include/simulator/g3_draw.h").write_text(GLAD + "\n", encoding="utf-8")
        (root / "libraries/sim/src/g3_handler.cpp").write_text(GLAD + "\n#include <nitro/gx/g3.h>\n", encoding="utf-8")
        (root / "libraries/sim/src/sim_g2.cpp").write_text(GLAD + "\n", encoding="utf-8")
        (root / "libraries/sim/src/sim_g3_Texture.cpp").write_text(
            '#include "simulator/sim_g3_Texture.hpp"\n#include "simulator/glad/glad.h"\n',
            encoding="utf-8",
        )
        (root / "include/simulator/g3_handler.h").write_text(GLAD + "\n", encoding="utf-8")
        (root / "libraries/sim/src/g3_draw.cpp").write_text(
            '#include <stdio.h>\n#define G3_DRAW_MAX_ITEMS 1000\n'
            'glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER);\n'
            'glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER);\n',
            encoding="utf-8",
        )
        (root / "libraries/sim/meson.build").write_text("libsim_args = [ ]\n", encoding="utf-8")
        for name in ("g2_vertex.glsl", "g2_fragment.glsl", "g3_vertex.glsl", "g3_fragment.glsl"):
            (root / "libraries/sim/src/shaders" / name).write_text(SHADER, encoding="utf-8")

    def test_patches_context_shaders_and_border_clamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "upstream"
            root.mkdir()
            self.make_source(root)
            output = Path(tmp) / "shader-output"
            report = prepare_android_graphics(root, output)
            main = (root / "libraries/sim/src/sim_main.cpp").read_text(encoding="utf-8")
            draw = (root / "libraries/sim/src/g3_draw.cpp").read_text(encoding="utf-8")
            shader = (root / "libraries/sim/src/shaders/g3_fragment.glsl").read_text(encoding="utf-8")
            self.assertIn("SDL_GL_CONTEXT_PROFILE_ES", main)
            self.assertIn("GLES3/gl32.h", main)
            self.assertIn("#ifndef SDK_BUILD_ANDROID", main)
            self.assertIn("OpenGL function loader initialization failed.", main)
            self.assertIn("SDL_GL_DeleteContext(context);", main)
            handler = (root / "include/simulator/g3_handler.h").read_text(encoding="utf-8")
            self.assertIn("GLES3/gl32.h", handler)
            handler_cpp = (root / "libraries/sim/src/g3_handler.cpp").read_text(encoding="utf-8")
            self.assertIn("GLES3/gl32.h", handler_cpp)
            sim_g2 = (root / "libraries/sim/src/sim_g2.cpp").read_text(encoding="utf-8")
            self.assertIn("GLES3/gl32.h", sim_g2)
            self.assertLess(sim_g2.index("#if defined(SDK_BUILD_ANDROID)"), sim_g2.index("#elif defined(SDK_BUILD_NX)"))
            texture_cpp = (root / "libraries/sim/src/sim_g3_Texture.cpp").read_text(encoding="utf-8")
            self.assertIn("GLES3/gl32.h", texture_cpp)
            self.assertLess(texture_cpp.index("#if defined(SDK_BUILD_ANDROID)"), texture_cpp.index("#elif defined(SDK_BUILD_NX)"))
            self.assertLess(handler_cpp.index("#if defined(SDK_BUILD_ANDROID)"), handler_cpp.index("#include <GLES3/gl32.h>"))
            self.assertLess(handler_cpp.index("#include <GLES3/gl32.h>"), handler_cpp.index("#elif defined(SDK_BUILD_NX)"))
            self.assertLess(handler.index("#if defined(SDK_BUILD_ANDROID)"), handler.index("#include <GLES3/gl32.h>"))
            self.assertLess(handler.index("#include <GLES3/gl32.h>"), handler.index("#elif defined(SDK_BUILD_NX)"))
            self.assertIn("SIM_GetBorderClampMode()", draw)
            self.assertIn(r'fallback.\n");', draw)
            self.assertEqual(1, draw.count("GL_TEXTURE_WRAP_S, SIM_GetBorderClampMode()"))
            self.assertEqual(1, draw.count("GL_TEXTURE_WRAP_T, SIM_GetBorderClampMode()"))
            self.assertNotIn("GL_CLAMP_TO_BORDER);", draw)
            self.assertIn("#version 320 es", shader)
            self.assertIn("precision highp sampler2D;", shader)
            meson = (root / "libraries/sim/meson.build").read_text(encoding="utf-8")
            meson_lines = meson.splitlines()
            self.assertIn("if(build_target == 'android')", meson_lines)
            self.assertIn("    libsim_args += ['-DIMGUI_IMPL_OPENGL_ES3']", meson_lines)
            self.assertIn("endif", meson_lines)
            self.assertNotIn("\\n", meson)
            self.assertEqual(4, report["shader_count"])
            self.assertEqual(4, len(list(output.iterdir())))
            exported = (output / "g3_fragment.frag").read_text(encoding="utf-8")
            self.assertNotIn('R""(', exported)
            self.assertNotIn(')""', exported)

    def test_patch_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "upstream"
            root.mkdir()
            self.make_source(root)
            prepare_android_graphics(root)
            first = {
                relative: (root / relative).read_text(encoding="utf-8")
                for relative in (
                    "libraries/sim/src/sim_main.cpp",
                    "libraries/sim/src/sim_g2.cpp",
                    "libraries/sim/src/sim_g3_Texture.cpp",
                    "libraries/sim/src/g3_handler.cpp",
                    "include/simulator/g3_draw.h",
                    "include/simulator/g3_handler.h",
                    "libraries/sim/src/g3_draw.cpp",
                    "libraries/sim/meson.build",
                )
            }
            prepare_android_graphics(root)
            self.assertEqual(
                first,
                {
                    relative: (root / relative).read_text(encoding="utf-8")
                    for relative in first
                },
            )

    def test_unknown_source_is_rejected_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "upstream"
            root.mkdir()
            self.make_source(root)
            main = root / "libraries/sim/src/sim_main.cpp"
            main.write_text("unknown revision", encoding="utf-8")
            with self.assertRaises(AndroidGraphicsPatchError):
                prepare_android_graphics(root)
            self.assertEqual("unknown revision", main.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
