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
            self.assertIn("SIM_GetBorderClampMode()", draw)
            self.assertIn("#version 320 es", shader)
            self.assertIn("precision highp sampler2D;", shader)
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
            first = (root / "libraries/sim/src/sim_main.cpp").read_text(encoding="utf-8")
            prepare_android_graphics(root)
            self.assertEqual(first, (root / "libraries/sim/src/sim_main.cpp").read_text(encoding="utf-8"))

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
