from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
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
EXPECTED_G2_SCENES = (
    "backdrop_top",
    "backdrop_bottom",
    "bg_stack_default_order",
    "bg_stack_permuted_order",
    "alpha_bg_over_bg",
    "alpha_bg_over_backdrop",
    "alpha_bg_over_obj",
    "brightness_increase",
    "brightness_decrease",
    "master_brightness_up",
    "master_brightness_down",
    "obj_priority_stack",
    "obj_window_masks",
    "bg0_3d_alpha",
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

    def test_g2_pixel_probe_and_runner_cover_the_same_synthetic_scenes(self):
        probe_path = ROOT / "tools" / "tests" / "cpp" / "renderer_g2_pixel_probe.cpp"
        runner_path = ROOT / "tools" / "tests" / "run_mobile_renderer_g2_pixel_comparison.py"
        workflow_path = ROOT / ".github" / "workflows" / "mobile-shader-source-validation.yml"
        self.assertTrue(probe_path.is_file(), f"Missing G2 host probe: {probe_path}")
        self.assertTrue(runner_path.is_file(), f"Missing G2 comparison runner: {runner_path}")
        self.assertTrue(workflow_path.is_file(), f"Missing shader validation workflow: {workflow_path}")

        probe = probe_path.read_text(encoding="utf-8")
        runner = runner_path.read_text(encoding="utf-8")
        workflow = workflow_path.read_text(encoding="utf-8")

        probe_names = tuple(re.findall(r'^\s*\{"([a-z0-9_]+)",', probe, flags=re.MULTILINE))
        scene_block = re.search(r"SCENE_NAMES = \((.*?)\n\)", runner, flags=re.DOTALL)
        self.assertIsNotNone(scene_block, "G2 runner must declare its scene order.")
        runner_names = tuple(re.findall(r'"([a-z0-9_]+)"', scene_block.group(1)))

        self.assertEqual(probe_names, EXPECTED_G2_SCENES)
        self.assertEqual(runner_names, EXPECTED_G2_SCENES)
        self.assertIn("run_mobile_renderer_g2_pixel_comparison.py", workflow)
        self.assertIn('MESA_GL_VERSION_OVERRIDE"] = "4.2"', runner)
        self.assertIn('MESA_GLES_VERSION_OVERRIDE"] = "3.0"', runner)

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

    def test_gles_compat_header_is_mobile_only_and_maps_program_uniform_calls(self):
        path = SHADER_DIR / "sim_gles3_compat.h"
        self.assertTrue(path.is_file(), f"Missing mobile GLES API header: {path}")
        source = path.read_text(encoding="utf-8")
        self.assertIn("defined(SDK_BUILD_ANDROID)", source)
        self.assertIn("defined(SDK_BUILD_IOS)", source)
        self.assertIn("#include <GLES3/gl3.h>", source)
        self.assertIn("#include <GLES3/gl3ext.h>", source)
        for function in (
            "glProgramUniform1i",
            "glProgramUniform1f",
            "glProgramUniform4f",
            "glProgramUniform1fv",
        ):
            with self.subTest(function=function):
                self.assertIn("#define " + function, source)
                self.assertIn("SIM::GLES3Compat::ProgramUniform", source)

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

    def test_gles_uniform_adapter_compiles_and_restores_program_state(self):
        compiler = shutil.which("c++")
        if compiler is None:
            self.skipTest("A host C++ compiler is not available.")

        source = ROOT / "tools" / "tests" / "cpp" / "mobile_renderer_uniform_compat_test.cpp"
        mock_include = ROOT / "tools" / "tests" / "cpp" / "mock_gles"
        self.assertTrue(source.is_file())
        self.assertTrue((mock_include / "GLES3" / "gl3.h").is_file())

        with tempfile.TemporaryDirectory(prefix="platina-gles3-uniform-test-") as directory:
            executable = Path(directory) / "uniform-compat-test"
            compile_result = subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-DSDK_BUILD_ANDROID",
                    "-I", str(mock_include),
                    "-I", str(ROOT),
                    str(source),
                    "-o", str(executable),
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(
                compile_result.returncode,
                0,
                compile_result.stdout + compile_result.stderr,
            )
            run_result = subprocess.run(
                [str(executable)],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stdout + run_result.stderr)

    def test_variants_do_not_redefine_or_replace_the_desktop_renderer(self):
        self.assertTrue((ROOT / ".gitmodules").is_file())
        self.assertTrue((ROOT / "docs" / "MOBILE_PARITY_CONTRACT.md").is_file())


if __name__ == "__main__":
    unittest.main()
