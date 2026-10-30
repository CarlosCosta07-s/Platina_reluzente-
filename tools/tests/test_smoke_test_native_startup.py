from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = ROOT / "scripts" / "smoke-test-native-startup.sh"


class SmokeTestShellStructureTests(unittest.TestCase):
    def test_inner_script_uses_a_quoted_heredoc(self):
        content = SMOKE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("bash -s <<'PLATINA_SMOKE_TEST'", content)
        self.assertEqual(content.count("PLATINA_SMOKE_TEST"), 2)
        self.assertIn("\nPLATINA_SMOKE_TEST\n) >\"$logfile\"", content)

    def test_fatal_renderer_patterns_are_inside_the_inner_script_without_single_quotes(self):
        content = SMOKE_SCRIPT.read_text(encoding="utf-8")
        start = content.index("bash -s <<'PLATINA_SMOKE_TEST'")
        end = content.index("\nPLATINA_SMOKE_TEST\n", start)
        inner_script = content[start:end]
        self.assertIn(
            'fatal_pattern="SDL video/timer initialization failed|SDL window creation failed|'
            'SDL GL context creation failed|OpenGL function loader initialization failed|'
            'Native renderer initialization failed|ERROR COMPILING _source SHADER"',
            inner_script,
        )
        self.assertIn('grep -Eiq "$fatal_pattern" "$logfile"', inner_script)
        self.assertNotIn("fatal_pattern='", inner_script)


if __name__ == "__main__":
    unittest.main()
