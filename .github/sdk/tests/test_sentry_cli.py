"""Verify the pinned installer without downloading or executing Sentry CLI."""

import contextlib
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "install_sentry_cli.py"
SPEC = importlib.util.spec_from_file_location("install_sentry_cli", SCRIPT)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "tools"
        self.payload = b"fixture CLI bytes, never executed"
        self.filename = "sentry-cli-Darwin-arm64"
        self.checksum = hashlib.sha256(self.payload).hexdigest()
        self.asset_patch = mock.patch.dict(
            installer.ASSETS,
            {"osx-arm64": (self.filename, self.checksum)},
        )
        self.asset_patch.start()
        self.addCleanup(self.asset_patch.stop)
        version_patch = mock.patch.object(
            installer.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, "sentry-cli 3.8.0\n", ""),
        )
        self.version = version_patch.start()
        self.addCleanup(version_patch.stop)
        self.urls = []

    def download_fixture(self, url, destination):
        self.urls.append(url)
        destination.write_bytes(self.payload)

    def test_installs_hash_verified_fixture_and_returns_absolute_path(self):
        path = installer.install(
            self.directory, "osx-arm64", loader=self.download_fixture
        )
        self.assertEqual(path, self.directory.resolve() / self.filename)
        self.assertEqual(path.read_bytes(), self.payload)
        self.assertEqual(
            self.urls,
            ["https://github.com/getsentry/sentry-cli/releases/download/3.8.0/"
             + self.filename],
        )
        self.version.assert_called_once_with(
            [str(self.version.call_args.args[0][0]), "--version"],
            check=True, capture_output=True, text=True, timeout=30,
        )

    def test_reuses_verified_existing_binary_without_downloading(self):
        self.directory.mkdir()
        existing = self.directory / self.filename
        existing.write_bytes(self.payload)
        loader = mock.Mock(side_effect=AssertionError("Unexpected download"))
        self.assertEqual(
            installer.install(self.directory, "osx-arm64", loader=loader),
            existing.resolve(),
        )
        loader.assert_not_called()
        self.version.assert_called_once()

    def test_download_hash_mismatch_never_chmods_or_executes(self):
        self.directory.mkdir()
        unrelated = self.directory / "keep.txt"
        unrelated.write_text("preserve", encoding="utf-8")

        def corrupt_download(url, destination):
            destination.write_bytes(b"corrupt fixture")

        with mock.patch.object(Path, "chmod") as chmod:
            with self.assertRaisesRegex(RuntimeError, "SHA256 mismatch"):
                installer.install(self.directory, "osx-arm64", loader=corrupt_download)
            chmod.assert_not_called()
        self.version.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [unrelated])
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "preserve")

    def test_rejects_existing_wrong_hash_without_replacing_it(self):
        self.directory.mkdir()
        existing = self.directory / self.filename
        existing.write_bytes(b"preexisting different binary")
        loader = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "SHA256 mismatch"):
            installer.install(self.directory, "osx-arm64", loader=loader)
        self.assertEqual(existing.read_bytes(), b"preexisting different binary")
        loader.assert_not_called()
        self.version.assert_not_called()

    def test_rejects_wrong_version_and_removes_only_staged_fixture(self):
        self.version.return_value.stdout = "sentry-cli 3.8.1\n"
        with self.assertRaisesRegex(RuntimeError, "Expected sentry-cli 3.8.0"):
            installer.install(self.directory, "osx-arm64", loader=self.download_fixture)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_reused_binary_also_requires_exact_version(self):
        self.directory.mkdir()
        existing = self.directory / self.filename
        existing.write_bytes(self.payload)
        self.version.return_value.stdout = "sentry-cli 3.8.1\n"
        with self.assertRaisesRegex(RuntimeError, "Expected sentry-cli 3.8.0"):
            installer.install(self.directory, "osx-arm64", loader=mock.Mock())
        self.assertEqual(existing.read_bytes(), self.payload)

    def test_failed_version_process_does_not_publish_fixture(self):
        self.version.side_effect = subprocess.CalledProcessError(1, ["fixture", "--version"])
        with self.assertRaises(subprocess.CalledProcessError):
            installer.install(self.directory, "osx-arm64", loader=self.download_fixture)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_unsupported_platform_fails_before_filesystem_or_network_work(self):
        loader = mock.Mock()
        with self.assertRaisesRegex(ValueError, "Unsupported platform"):
            installer.install(self.directory, "other", loader=loader)
        self.assertFalse(self.directory.exists())
        loader.assert_not_called()
        self.version.assert_not_called()

    def test_rejects_symlink_without_touching_target(self):
        self.directory.mkdir()
        target = Path(self.temporary.name) / "keep.txt"
        target.write_bytes(self.payload)
        link = self.directory / self.filename
        try:
            link.symlink_to(target)
        except OSError as error:
            self.skipTest(f"Symlinks are unavailable: {error}")
        loader = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "regular file"):
            installer.install(self.directory, "osx-arm64", loader=loader)
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_bytes(), self.payload)
        loader.assert_not_called()
        self.version.assert_not_called()

    def test_default_loader_streams_fixture_response(self):
        response = io.BytesIO(self.payload)
        with mock.patch.object(installer.urllib.request, "urlopen", return_value=response):
            path = installer.install(self.directory, "osx-arm64")
        self.assertTrue(path.is_file(), "The fixture download was not published")
        self.assertEqual(path.read_bytes(), self.payload)

    def test_cli_prints_path_when_github_output_is_absent(self):
        expected = self.directory / self.filename
        stdout = io.StringIO()
        with mock.patch.object(installer, "install", return_value=expected):
            with mock.patch.dict(os.environ, {}, clear=True):
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(installer.main([
                        "--directory", str(self.directory), "--platform", "osx-arm64"
                    ]), 0)
        self.assertEqual(stdout.getvalue(), f"{expected}\n")

    def test_cli_appends_github_output_without_printing_path(self):
        expected = self.directory / self.filename
        output = Path(self.temporary.name) / "github-output.txt"
        output.write_text("existing=value\n", encoding="utf-8")
        stdout = io.StringIO()
        with mock.patch.object(installer, "install", return_value=expected):
            with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}, clear=True):
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(installer.main([
                        "--directory", str(self.directory), "--platform", "osx-arm64"
                    ]), 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            output.read_text(encoding="utf-8"), f"existing=value\npath={expected}\n"
        )


if __name__ == "__main__":
    unittest.main()
