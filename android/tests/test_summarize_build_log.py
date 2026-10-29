import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "summarize_build_log.py"
spec = importlib.util.spec_from_file_location("summarize_build_log", SCRIPT)
summarize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summarize)


class SummarizeBuildLogTests(unittest.TestCase):
    def run_main(self, text: str | None) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "native-build.log"
            if text is not None:
                log.write_text(text, encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(summarize.main([str(log)]), 0)
            return out.getvalue()

    def test_reports_first_failing_edge_and_diagnostic_in_log_order(self):
        noise = "\n".join(f"[{i}/900] cc -c file{i}.c" for i in range(5000))
        log = (
            f"{noise}\n"
            "FAILED: trainer_ai_script.o\n"
            "script.ss:12:5: error: invalid instruction\n"
            "ninja: build stopped: subcommand failed.\n"
        )
        out = self.run_main(log).splitlines()
        self.assertEqual(len(out), 3)
        self.assertIn("FAILED: trainer_ai_script.o", out[0])
        self.assertIn("log line 5001", out[0])
        self.assertIn("invalid instruction", out[1])

    def test_limits_and_deduplicates_annotations(self):
        log = "\n".join("a.c:1:1: error: same problem" for _ in range(50))
        log += "\n" + "\n".join(f"b{i}.c:1:1: error: problem {i}" for i in range(30))
        out = self.run_main(log).splitlines()
        self.assertEqual(len(out), summarize.MAX_ANNOTATIONS)
        self.assertEqual(sum("same problem" in line for line in out), 1)

    def test_escapes_workflow_command_data_and_strips_ansi(self):
        log = "\x1b[31mmain.c:1:1: error: 100% broken\x1b[0m\r\n"
        out = self.run_main(log)
        self.assertIn("100%25 broken", out)
        self.assertNotIn("\x1b", out)
        self.assertEqual(len(out.splitlines()), 1)

    def test_missing_or_clean_log_prints_note_and_never_fails(self):
        self.assertIn("No build log found", self.run_main(None))
        self.assertIn("No recognizable error", self.run_main("all good\nlinked\n"))


if __name__ == "__main__":
    unittest.main()
