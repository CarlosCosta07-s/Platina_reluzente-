import tempfile
import unittest
from pathlib import Path
from scripts.prepare_eidos_launcher_protocol import MARKER, prepare_eidos_launcher_protocol

class EidosLauncherProtocolTests(unittest.TestCase):
    def make_source(self, root: Path, body: str) -> Path:
        platform_dir = root / "engine" / "platform"
        platform_dir.mkdir(parents=True)
        source = platform_dir / "platform.c"
        source.write_text("#include <SDL3/SDL.h>\n#include <stdio.h>\n" + body, encoding="utf-8")
        return source

    def test_protocol_is_emitted_after_the_presenter_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_source(Path(tmp), "void present(EidosPlatform *p) {\n    p->presented = 1;\n    render(p);\n}\n")
            self.assertTrue(prepare_eidos_launcher_protocol(Path(tmp)))
            text = source.read_text(encoding="utf-8")
            render_at = text.index("    render(p);")
            marker_at = text.index(MARKER)
            first_frame_at = text.index('[Platina-Progress] window-ready')
            heartbeat_at = text.index('[Platina-Progress] heartbeat frame=%llu')
            self.assertLess(render_at, marker_at)
            self.assertLess(marker_at, first_frame_at)
            self.assertLess(first_frame_at, heartbeat_at)
            self.assertIn("SDL_GetTicks()", text)
            self.assertIn("launcher_frame_number++", text)
            self.assertIn("fflush(stderr)", text)

    def test_patch_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_source(Path(tmp), "void present(EidosPlatform *p) {\n    p->presented = 1;\n    render(p);\n}\n")
            self.assertTrue(prepare_eidos_launcher_protocol(Path(tmp)))
            first = source.read_text(encoding="utf-8")
            self.assertFalse(prepare_eidos_launcher_protocol(Path(tmp)))
            self.assertEqual(source.read_text(encoding="utf-8"), first)
            self.assertEqual(first.count(MARKER), 1)

    def test_patch_fails_closed_when_handoff_is_missing_or_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_source(Path(tmp), "void present(void) { }\n")
            with self.assertRaisesRegex(RuntimeError, "exactly one"):
                prepare_eidos_launcher_protocol(Path(tmp))
            self.assertEqual(source.read_text(encoding="utf-8"), "#include <SDL3/SDL.h>\n#include <stdio.h>\nvoid present(void) { }\n")
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_source(Path(tmp), "void a(EidosPlatform *p) {\n    p->presented = 1;\n    render(p);\n}\nvoid b(EidosPlatform *p) {\n    p->presented = 1;\n    render(p);\n}\n")
            with self.assertRaisesRegex(RuntimeError, "exactly one"):
                prepare_eidos_launcher_protocol(Path(tmp))
            self.assertNotIn(MARKER, source.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
