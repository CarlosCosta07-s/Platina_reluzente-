from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from audit_android_graphics import (  # noqa: E402
    GraphicsAuditError,
    audit_android_graphics,
    render_markdown,
)


class AndroidGraphicsAuditTests(unittest.TestCase):
    def _create_source_tree(self, root: Path) -> Path:
        native_root = root / "native"
        libntr = native_root / "subprojects" / "libntr"
        source = libntr / "libraries" / "sim" / "src"
        shaders = source / "shaders"
        include = libntr / "libraries" / "sim" / "include"
        shaders.mkdir(parents=True)
        include.mkdir(parents=True)
        (source / "sim_main.cpp").write_text(
            "SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 4);\n"
            "SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 2);\n"
            "SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);\n"
            "glDebugMessageCallback(callback, 0);\n",
            encoding="utf-8",
        )
        (source / "g3_draw.cpp").write_text(
            "glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER);\n"
            "glProgramUniform1i(program, location, 0);\n",
            encoding="utf-8",
        )
        (shaders / "g3_vertex.glsl").write_text(
            "#version 420 core\nvoid main() {}\n",
            encoding="utf-8",
        )
        return native_root

    def test_reports_desktop_context_shader_and_api_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._create_source_tree(Path(tmp))
            report = audit_android_graphics(root)
            self.assertEqual(report["files_scanned"], 3)
            self.assertEqual(
                report["context_request"],
                {"major": 4, "minor": 2, "profile_core": True},
            )
            self.assertEqual(report["shader_versions"], {"420 core": 1})
            findings = report["api_findings"]
            self.assertTrue(findings["border-clamp texture mode"])
            self.assertTrue(findings["program-uniform direct state calls"])
            self.assertTrue(findings["GL debug output callback"])

    def test_markdown_report_is_explicit_about_limitations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_android_graphics(self._create_source_tree(Path(tmp)))
            markdown = render_markdown(report)
            self.assertIn("OpenGL 4.2 core profile", markdown)
            self.assertIn("GLSL 420 core", markdown)
            self.assertIn("not proof of Android compatibility", markdown)

    def test_missing_libntr_source_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(GraphicsAuditError, "libntr source is missing"):
                audit_android_graphics(Path(tmp) / "missing")


if __name__ == "__main__":
    unittest.main()
