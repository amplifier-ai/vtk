import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


VALIDATOR = Path(__file__).resolve().parents[1] / "validate_release.py"
SOURCE = "a" * 40
ARCHIVES = {"win-x64": "vtk-sdk-win-x64.zip", "osx-arm64": "vtk-sdk-osx-arm64.tar.gz"}


class ReleaseValidation(unittest.TestCase):
    def setUp(self):
        self.assertTrue(VALIDATOR.is_file(), "SDK publication receipts are not validated")
        spec = importlib.util.spec_from_file_location("validate_release", VALIDATOR)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packages = self.root / "packages"
        self.evidence = self.root / "evidence"
        self.packages.mkdir()
        self.reports = {}
        self.digests = {}
        for platform, name in ARCHIVES.items():
            data = f"Small {platform} archive fixture".encode()
            self.digests[platform] = hashlib.sha256(data).hexdigest()
            (self.packages / name).write_bytes(data)
            (self.packages / f"{name}.sha256").write_text(
                f"{self.digests[platform]}  {name}\n", encoding="utf-8")
            (self.evidence / platform).mkdir(parents=True)
            self.reports[platform] = {
                "archive_sha256": self.digests[platform], "source_revision": SOURCE,
                "platform": platform, "original_sdk_removed": True, "outcome": "passed",
                "commands": [
                    {"command": ["cmake", "-S", "consumer", "-B", "consumer-build"], "exit_code": 0},
                    {"command": ["cmake", "--build", "consumer-build"], "exit_code": 0},
                    {"command": ["ctest", "--test-dir", "consumer-build", "--output-on-failure"],
                     "exit_code": 0},
                ],
            }
            self.write_report(platform)

    def write_report(self, platform="win-x64"):
        (self.evidence / platform / "verification.json").write_text(
            json.dumps(self.reports[platform]), encoding="utf-8")

    def validate(self, source=SOURCE):
        return self.module.validate_release(self.packages, self.evidence, source)

    def test_both_platforms_require_matching_passed_receipts(self):
        self.assertEqual(self.validate(), self.digests)

    def test_rejects_failed_consumer_receipt_despite_valid_archive_checksum(self):
        self.reports["win-x64"]["outcome"] = "failed"
        self.write_report()
        with self.assertRaisesRegex(RuntimeError, "outcome"):
            self.validate()

    def test_rejects_report_identity_mismatches(self):
        original = copy.deepcopy(self.reports["win-x64"])
        for field, value in [("source_revision", "b" * 40), ("platform", "osx-arm64"),
                             ("archive_sha256", "0" * 64), ("original_sdk_removed", False),
                             ("original_sdk_removed", 1)]:
            with self.subTest(field=field, value=value):
                self.reports["win-x64"] = {**original, field: value}
                self.write_report()
                with self.assertRaisesRegex(RuntimeError, field):
                    self.validate()

    def test_rejects_archive_bytes_changed_after_consumer_verification(self):
        (self.packages / ARCHIVES["win-x64"]).write_bytes(b"Different bytes")
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            self.validate()

    def test_checksum_cannot_select_another_file_or_extra_records(self):
        name = ARCHIVES["win-x64"]
        checksum = self.packages / f"{name}.sha256"
        for text in [f"{self.digests['win-x64']}  ../{name}\n",
                     f"{self.digests['win-x64']}  {name}\n{self.digests['win-x64']}  other.zip\n",
                     "malformed checksum\n"]:
            with self.subTest(text=text):
                checksum.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    self.validate()

    def test_rejects_missing_archive_checksum_or_receipt_on_either_platform(self):
        for platform, name in ARCHIVES.items():
            for path in [self.packages / name, self.packages / f"{name}.sha256",
                         self.evidence / platform / "verification.json"]:
                with self.subTest(path=path):
                    content = path.read_bytes()
                    path.unlink()
                    try:
                        with self.assertRaises(RuntimeError):
                            self.validate()
                    finally:
                        path.write_bytes(content)

    def test_rejects_malformed_or_non_object_receipts(self):
        path = self.evidence / "win-x64" / "verification.json"
        for text in ["{", "[]", "null"]:
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "verification"):
                    self.validate()

    def test_requires_configure_build_and_test_receipts(self):
        original = copy.deepcopy(self.reports["win-x64"]["commands"])
        for omitted in range(3):
            with self.subTest(omitted=omitted):
                self.reports["win-x64"]["commands"] = original[:omitted] + original[omitted + 1:]
                self.write_report()
                with self.assertRaisesRegex(RuntimeError, "commands"):
                    self.validate()
        self.reports["win-x64"]["commands"] = []
        self.write_report()
        with self.assertRaisesRegex(RuntimeError, "commands"):
            self.validate()

    def test_exit_codes_must_be_present_integer_zero_on_every_command(self):
        original = copy.deepcopy(self.reports["win-x64"]["commands"])
        for index in range(3):
            for value in [1, None, False, True, 0.0, "0", "missing"]:
                with self.subTest(index=index, value=value):
                    commands = copy.deepcopy(original)
                    if value == "missing":
                        commands[index].pop("exit_code")
                    else:
                        commands[index]["exit_code"] = value
                    self.reports["win-x64"]["commands"] = commands
                    self.write_report()
                    with self.assertRaisesRegex(RuntimeError, "exit_code"):
                        self.validate()

    def test_rejects_version_queries_disguised_as_consumer_checks(self):
        for option in ["--version", "--show-only=json", "-N"]:
            with self.subTest(option=option):
                self.reports["win-x64"]["commands"][2]["command"] = [
                    "ctest", "--test-dir", "consumer-build", option]
                self.write_report()
                with self.assertRaisesRegex(RuntimeError, "commands"):
                    self.validate()

    def test_rejects_malformed_command_records(self):
        for commands in [None, "commands", [None], [{"exit_code": 0}],
                         [{"command": [], "exit_code": 0}],
                         [{"command": ["ctest", None], "exit_code": 0}]]:
            with self.subTest(commands=commands):
                self.reports["win-x64"]["commands"] = commands
                self.write_report()
                with self.assertRaisesRegex(RuntimeError, "commands"):
                    self.validate()

    def test_requires_consumer_commands_to_use_the_same_build_directory(self):
        self.reports["win-x64"]["commands"][2]["command"][2] = "unrelated-build"
        self.write_report()
        with self.assertRaisesRegex(RuntimeError, "commands"):
            self.validate()

    def test_rejects_missing_and_invalid_expected_source(self):
        for source in ["", "a" * 39, "g" * 40]:
            with self.subTest(source=source):
                with self.assertRaisesRegex(RuntimeError, "source"):
                    self.validate(source)

    def test_cli_refuses_failed_receipts_and_accepts_validated_packages(self):
        command = [sys.executable, str(VALIDATOR), "--packages", str(self.packages),
                   "--evidence", str(self.evidence), "--source-sha", SOURCE]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.digests)
        self.reports["osx-arm64"]["outcome"] = "failed"
        self.write_report("osx-arm64")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outcome", result.stderr)


if __name__ == "__main__":
    unittest.main()
