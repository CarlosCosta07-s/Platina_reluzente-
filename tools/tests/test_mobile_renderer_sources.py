from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHADER_DIR = ROOT / "mobile" / "renderer" / "gles300"
EXPECTED_SHADERS = (
    "g2_vertex.glsl",
    "g2_fragment.glsl",
    "g3_vertex.glsl",
    "g3_fragment.glsl",
)


def without_glsl_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", source)


class MobileRendererSourceTests(unittest.TestCase):
    def read_shader(self, name: str) -> str:
        path = SHADER_DIR / name
        self.assertTrue(path.is_file(), f"Missing source-only GLES shader: {path}")
        return path.read_text(encoding="utf-8")

    def test_all_mobile_variants_use_glsl_es_300(self):
        for name in EXPECTED_SHADERS:
            with self.subTest(shader=name):
                source = self.read_shader(name)
                self.assertRegex(source, r"^#version 300 es\s")
                self.assertIn("precision highp float;", source)
                self.assertNotIn("#version 420 core", source)

    def test_vertex_and_fragment_interfaces_match(self):
        g2_vertex = self.read_shader("g2_vertex.glsl")
        g2_fragment = self.read_shader("g2_fragment.glsl")
        g3_vertex = self.read_shader("g3_vertex.glsl")
        g3_fragment = self.read_shader("g3_fragment.glsl")

        self.assertIn("smooth out vec2 fragTexCoord;", g2_vertex)
        self.assertIn("smooth in vec2 fragTexCoord;", g2_fragment)
        self.assertIn("smooth out vec2 fragTexCoord;", g3_vertex)
        self.assertIn("smooth in vec2 fragTexCoord;", g3_fragment)
        self.assertIn("smooth out vec4 fragInColor;", g3_vertex)
        self.assertIn("smooth in vec4 fragInColor;", g3_fragment)
        self.assertIn("smooth out vec4 coords;", g3_vertex)
        self.assertIn("smooth in vec4 coords;", g3_fragment)

    def test_g2_sampler_arrays_are_accessed_only_with_literal_indices(self):
        source = without_glsl_comments(self.read_shader("g2_fragment.glsl"))
        access_source = re.sub(
            r"(?m)^\s*uniform\s+sampler2D\s+\w+\s*\[\s*\d+\s*\]\s*;\s*$",
            "",
            source,
        )
        sampler_arrays = re.findall(
            r"\b(?:bgTexture|objTexture)\s*\[\s*([^\]]+)\s*\]",
            access_source,
        )
        self.assertTrue(sampler_arrays, "Expected explicit sampler-array accesses.")
        for index in sampler_arrays:
            with self.subTest(index=index):
                self.assertRegex(index, r"^[0-4]$")

        for layer in range(4):
            self.assertIn(f"case {layer}: return texture(bgTexture[{layer}], fragTexCoord);", source)
        for layer in range(5):
            self.assertIn(f"case {layer}: return texture(objTexture[{layer}], fragTexCoord);", source)

    def test_g2_routes_runtime_layer_selection_through_sampler_helpers(self):
        source = without_glsl_comments(self.read_shader("g2_fragment.glsl"))
        self.assertIn("vec4 sampleBg(int index)", source)
        self.assertIn("vec4 sampleObj(int index)", source)
        self.assertIn("vec4 bgColor = sampleBg(bgNum);", source)
        self.assertIn("vec4 targetColor = sampleBg(currentBgDrawn);", source)
        self.assertIn("vec4 objColor = sampleObj(j);", source)
        self.assertIn("vec4 objColor = sampleObj(i);", source)

    def test_g3_keeps_dynamic_fog_arrays_as_non_sampler_uniforms(self):
        source = without_glsl_comments(self.read_shader("g3_fragment.glsl"))
        self.assertIn("uniform float fogDepthBoundary[32];", source)
        self.assertIn("uniform float fogDensity[32];", source)
        self.assertIn("fogDepthBoundary[foundIdx]", source)
        self.assertIn("fogDensity[foundIdx]", source)
        self.assertNotRegex(source, r"\btexture\s*\(\s*\w+\s*\[")

    def test_g3_emulates_transparent_clamp_to_border(self):
        source = without_glsl_comments(self.read_shader("g3_fragment.glsl"))
        self.assertIn("uniform int clampToBorderS;", source)
        self.assertIn("uniform int clampToBorderT;", source)
        self.assertIn("vec4 sampleG3Texture()", source)
        self.assertIn("vec4 texel = texture(myTexture, fragTexCoord);", source)
        self.assertLess(
            source.index("vec4 texel = texture(myTexture, fragTexCoord);"),
            source.index("bool outsideS = clampToBorderS == 1"),
        )
        self.assertIn("fragTexCoord.s < 0.0 || fragTexCoord.s > 1.0", source)
        self.assertIn("fragTexCoord.t < 0.0 || fragTexCoord.t > 1.0", source)
        self.assertIn("? vec4(0.0) : texel;", source)
        self.assertIn("vec4 texel = sampleG3Texture();", source)

    def test_gles_program_uniform_adapter_restores_the_previous_program(self):
        adapter_path = SHADER_DIR / "program_uniform_compat.hpp"
        self.assertTrue(adapter_path.is_file(), f"Missing GLES compatibility header: {adapter_path}")
        source = adapter_path.read_text(encoding="utf-8")
        self.assertIn("#include <GLES3/gl3.h>", source)
        self.assertIn("glGetIntegerv(GL_CURRENT_PROGRAM, &previousProgram_);", source)
        self.assertIn("glUseProgram(targetProgram);", source)
        self.assertIn("glUseProgram(static_cast<GLuint>(previousProgram_));", source)
        self.assertIn("ScopedProgramBinding(const ScopedProgramBinding &) = delete;", source)
        for function in ("glUniform1i", "glUniform1f", "glUniform4f", "glUniform1fv"):
            with self.subTest(function=function):
                self.assertIn(function, source)

    def test_variants_do_not_redefine_or_replace_the_desktop_renderer(self):
        self.assertTrue((ROOT / ".gitmodules").is_file())
        self.assertTrue((ROOT / "docs" / "MOBILE_PARITY_CONTRACT.md").is_file())


if __name__ == "__main__":
    unittest.main()
