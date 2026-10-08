import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SDK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SDK))
spec = importlib.util.spec_from_file_location("sentry_symbols", SDK / "sentry_symbols.py")
symbols = importlib.util.module_from_spec(spec)
spec.loader.exec_module(symbols)
REVISION = "a" * 40
ID = "01234567-89ab-cdef-0123-456789abcdef"
INFO = {"debug_id": ID, "arch": "arm64", "code_id": "code", "features": ["debug"], "type": "dsym"}


class NativeDebugFiles(unittest.TestCase):
    def test_binary_debug_pair_rejects_wrong_id_architecture_or_missing_debug_info(self):
        symbols.require_pair(INFO, INFO)
        for change in ({"debug_id": "other"}, {"arch": "x86_64"}, {"features": ["symtab"]}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                symbols.require_pair(INFO, {**INFO, **change})

    def test_frozen_symbols_reject_changed_bytes_and_other_source_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            debug = root / "module.dwarf"
            debug.write_bytes(b"native debug fixture")
            manifest = {"schema_version": 2, "repository": "amplifier-ai/vtk",
                        "source_revision": REVISION, "platform": "osx-arm64", "outcome": "passed",
                        "artifacts": symbols.inventory(root),
                        "modules": [{**INFO, "binaries": [INFO],
                                     "debug": {"path": debug.name, "sha256": symbols.digest(debug), **INFO}}]}
            (root / "sentry-manifest.json").write_text(json.dumps(manifest))
            with patch.object(symbols, "debug_info", return_value=INFO):
                self.assertEqual(symbols.verify(root, REVISION, "fixture-cli"), manifest)
                with self.assertRaisesRegex(RuntimeError, "source/outcome"):
                    symbols.verify(root, "b" * 40, "fixture-cli")
                debug.write_bytes(b"changed debug bytes")
                with self.assertRaisesRegex(RuntimeError, "inventory or hashes"):
                    symbols.verify(root, REVISION, "fixture-cli")

    def test_debug_file_check_rejects_unusable_or_ambiguous_architectures(self):
        report = {"is_usable": True, "variants": [{"debug_id": ID, "arch": "arm64"}],
                  "features": "debug, symtab", "type": "dsym"}
        self.assertEqual(symbols.decode_info(report)["debug_id"], ID)
        for change in ({"is_usable": False}, {"variants": report["variants"] * 2}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                symbols.decode_info({**report, **change})


if __name__ == "__main__":
    unittest.main()
