"""Keep the checked-in generated MTL parser's debug paths materialized."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
PARSER = ROOT / "IO/Import/mtlsyntax.inl"


class MTLSourceContext(unittest.TestCase):
    def test_generated_parser_does_not_redirect_debug_lines_to_missing_historical_files(self):
        source = PARSER.read_text()
        self.assertNotRegex(source, r'(?m)^#line\s+\d+\s+"(?:.*vtk3.*|NONE)"')
        self.assertTrue((ROOT / "IO/Import/mtlsyntax.rl").is_file())
        self.assertTrue(PARSER.is_file())
        self.assertNotRegex(source, r"\b__(?:FILE|LINE)__\b")


if __name__ == "__main__":
    unittest.main()
