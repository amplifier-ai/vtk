import copy
import importlib.util
import json
import io
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
import unittest
from unittest.mock import patch


HELPER = Path(__file__).resolve().parents[1] / "publish_sentry.py"
sys.path.insert(0, str(HELPER.parent))
REVISION = "a" * 40
RELEASE = "vtk-sdk@9.7.1+" + REVISION
TOKEN = "fixture-token-never-persist"
IDS = ["01234567-89ab-cdef-0123-456789abcdef-1", "12345678-9abc-def0-1234-56789abcdef0"]


class PublicationContracts(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.is_file(), "VTK publication helper is required")
        spec = importlib.util.spec_from_file_location("publish_sentry", HELPER)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.packages = self.root / "packages"
        self.runtime = self.root / "runtime"
        self.packages.mkdir()
        self.runtime.mkdir()
        self.roots, self.manifests = [], []
        for index, (platform, arch, prefix) in enumerate([
                ("win-x64", "x86_64", "D:/a/vtk/vtk/"),
                ("osx-arm64", "arm64", "/Users/runner/work/vtk/vtk/")]):
            root = self.root / platform
            root.mkdir()
            self.roots.append(root)
            artifacts = []
            for role, file_type, features in [("binary", "pe" if index == 0 else "dsym", ["symtab"]),
                                               ("debug", "pdb" if index == 0 else "dsym", ["debug", "symtab"])]:
                path = root / role
                path.write_bytes((platform + role).encode())
                artifacts.append({"path": role, "sha256": self.module.digest(path),
                                  "type": file_type, "features": features})
            extension = "zip" if index == 0 else "tar.gz"
            archives = {}
            for product, directory in (("sdk", self.packages), ("csharp", self.runtime)):
                name = f"vtk-{product}-{platform}.{extension}"
                path = directory / name
                path.write_bytes((platform + product).encode())
                archives[name] = self.module.digest(path)
            manifest = {"platform": platform, "source_revision": REVISION, "source_tree": "b" * 40,
                        "vtk_version": "9.7.1", "source_prefix": prefix, "run_id": "123", "run_attempt": str(index+1),
                        "archives": archives, "modules": [{"debug_id": IDS[index], "arch": arch,
                                                          "binaries": [artifacts[0]], "debug": artifacts[1]}]}
            (root / "sentry-manifest.json").write_text(json.dumps(manifest))
            self.manifests.append(manifest)
        self.receipt = self.root / "publication.json"
        self.environment = patch.dict(os.environ, {"SENTRY_AUTH_TOKEN": TOKEN, "GITHUB_RUN_ID": "123"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.files = self.module.upload_inputs(self.roots, self.manifests)

    def provider_release(self):
        return {"version": RELEASE, "ref": REVISION, "dateReleased": "2026-10-08T07:00:00Z",
                "projects": [{"slug": "unity-plugin"}]}

    def provider_commits(self):
        return [{"repository": {"name": "amplifier-ai/vtk"}, "id": REVISION}]

    def provider_files(self):
        return [{"id": str(index), "debugId": item["debug_id"], "cpuName": item["arch"],
                 "symbolType": item["type"], "sha1": item["sha1"], "size": item["size"],
                 "data": {"features": item["features"]}} for index, item in enumerate(self.files.values())]

    def call_publish(self):
        return self.module.publish(self.roots, REVISION, RELEASE, self.receipt, "pinned-cli",
                                   self.packages, self.runtime)

    def test_release_create_and_retry_bind_the_exact_vtk_repository_sha(self):
        method, body = self.module.release_plan(None, [], RELEASE, REVISION)
        self.assertEqual(method, 'POST')
        self.assertEqual(body['refs'], [{'repository': 'amplifier-ai/vtk', 'commit': REVISION}])
        self.assertEqual(body['commits'], [{'repository': 'amplifier-ai/vtk', 'id': REVISION}])
        self.assertEqual(self.module.release_plan(self.provider_release(), self.provider_commits(), RELEASE, REVISION), (None, None))
        existing = self.provider_release()
        existing['ref'] = None
        self.assertEqual(self.module.release_plan(existing, [], RELEASE, REVISION)[0], 'PUT')

    def test_release_cannot_overwrite_other_revisions_repositories_or_projects(self):
        cases = [(dict(self.provider_release(), ref='c' * 40), self.provider_commits()),
                 (self.provider_release(), [{'repository': 'amplifier-ai/vr', 'id': REVISION}]),
                 (self.provider_release(), [{'repository': 'amplifier-ai/vtk', 'id': 'c' * 40}]),
                 (dict(self.provider_release(), projects=[{'slug': 'vr'}]), self.provider_commits())]
        for existing, commits in cases:
            with self.subTest(existing=existing, commits=commits), self.assertRaises(RuntimeError):
                self.module.release_plan(existing, commits, RELEASE, REVISION)

    def test_unfinalized_release_is_not_qualified(self):
        release = {**self.provider_release(), 'dateReleased': None}
        with patch.object(self.module, 'api_request', return_value=(release, None)), \
                self.assertRaisesRegex(RuntimeError, 'finalization'):
            self.module.verify_release(TOKEN, 'release/', RELEASE, REVISION, finalized=True)

    def test_upload_readback_requires_exact_processed_bytes_format_architecture_and_features(self):
        valid = self.provider_files()
        with patch.object(self.module, 'api_list', return_value=valid):
            self.assertEqual(len(self.module.verify_uploads(TOKEN, self.files)), 2)
        for field, value in [('sha1', '0' * 40), ('size', -1), ('symbolType', 'elf'),
                             ('cpuName', 'unknown'), ('debugId', 'old-debug-id'), ('data', {'features': []})]:
            invalid = copy.deepcopy(valid)
            invalid[0][field] = value
            with self.subTest(field=field), patch.object(self.module, 'api_list', return_value=invalid), self.assertRaises(RuntimeError):
                self.module.verify_uploads(TOKEN, self.files)
        with patch.object(self.module, 'api_list', return_value=valid[:-1]), self.assertRaisesRegex(RuntimeError, 'debug'):
            self.module.verify_uploads(TOKEN, self.files)

    def test_archive_run_or_hash_mismatch_fails_before_http(self):
        with patch.object(self.module, 'run_cli', return_value='sentry-cli 3.8.0'), \
                patch.object(self.module, 'verify', side_effect=self.manifests), patch.object(self.module, 'api_request') as request:
            (self.runtime / next(iter(self.manifests[0]['archives'].keys() - {next(k for k in self.manifests[0]['archives'] if k.startswith('vtk-sdk-'))}))).write_bytes(b'changed')
            with self.assertRaisesRegex(RuntimeError, 'archive bytes'):
                self.call_publish()
            request.assert_not_called()
        with patch.dict(os.environ, {'GITHUB_RUN_ID': '456'}), self.assertRaisesRegex(RuntimeError, 'workflow run'):
            self.module.validate_archives(self.manifests, self.packages, self.runtime)

    def test_platform_retry_attempts_can_differ_within_the_same_run(self):
        self.module.validate_archives(self.manifests, self.packages, self.runtime)
        self.assertNotEqual(self.manifests[0]['run_attempt'], self.manifests[1]['run_attempt'])

    def test_two_platform_source_identity_and_cli_pin_are_required_before_http(self):
        with patch.object(self.module, 'run_cli', return_value='sentry-cli 0.0.0'), patch.object(self.module, 'api_request') as request:
            with self.assertRaisesRegex(RuntimeError, 'CLI version'):
                self.call_publish()
            request.assert_not_called()
        broken = copy.deepcopy(self.manifests)
        broken[1]['source_tree'] = 'c' * 40
        with patch.object(self.module, 'run_cli', return_value='sentry-cli 3.8.0'), \
                patch.object(self.module, 'verify', side_effect=broken), patch.object(self.module, 'api_request') as request:
            with self.assertRaisesRegex(RuntimeError, 'different VTK'):
                self.call_publish()
            request.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, 'full VTK'):
            self.module.publish(self.roots, 'abcdef', RELEASE, self.receipt, 'cli', self.packages, self.runtime)

    def test_api_timeout_identifies_method_endpoint_and_reason(self):
        opener = SimpleNamespace(open=unittest.mock.Mock(side_effect=URLError(TimeoutError('timed out'))))
        with patch.object(self.module, 'build_opener', return_value=opener):
            with self.assertRaises(RuntimeError) as failure:
                self.module.api_request('GET', 'release/commits/', TOKEN)
        self.assertIn('GET release/commits/', str(failure.exception))
        self.assertIn('TimeoutError', str(failure.exception))

    def test_api_http_error_identifies_endpoint_without_response_body(self):
        error = HTTPError('https://sentry.io/api/0/release/', 403, 'Forbidden', {}, None)
        opener = SimpleNamespace(open=unittest.mock.Mock(side_effect=error))
        with patch.object(self.module, 'build_opener', return_value=opener):
            with self.assertRaises(RuntimeError) as failure:
                self.module.api_request('POST', 'release/', TOKEN)
        self.assertIn('POST release/', str(failure.exception))
        self.assertIn('403', str(failure.exception))

    def test_api_invalid_json_is_distinguished_and_transport_secrets_are_redacted(self):
        opener = SimpleNamespace(open=unittest.mock.Mock(return_value=io.BytesIO(b'')))
        with patch.object(self.module, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(RuntimeError, 'GET release/.*JSON'):
                self.module.api_request('GET', 'release/', TOKEN)
        opener.open.side_effect = URLError(OSError('connection reset ' + TOKEN))
        with patch.object(self.module, 'build_opener', return_value=opener):
            with self.assertRaises(RuntimeError) as failure:
                self.module.api_request('GET', 'release/', TOKEN)
        self.assertNotIn(TOKEN, str(failure.exception))
        self.assertIn('connection reset', str(failure.exception))

    def test_provider_collections_are_fully_paginated_and_cannot_loop(self):
        with patch.object(self.module, 'api_request', side_effect=[([{'id': 1}], 'page-two'), ([{'id': 2}], None)]):
            self.assertEqual(self.module.api_list('page-one', TOKEN), [{'id': 1}, {'id': 2}])
        with patch.object(self.module, 'api_request', return_value=([], 'page-one')), self.assertRaisesRegex(RuntimeError, 'pagination'):
            self.module.api_list('page-one', TOKEN)
        self.assertEqual(self.module.next_page('<https://sentry.io/api/0/path/?cursor=abc>; rel="next"; results="true"'), 'path/?cursor=abc')
        with self.assertRaisesRegex(RuntimeError, 'origin'):
            self.module.next_page('<https://other.example/api/0/path/>; rel="next"; results="true"')

    def test_cli_token_is_environment_only_and_failures_are_redacted(self):
        failure = SimpleNamespace(returncode=1, stderr='', stdout='provider echoed ' + TOKEN)
        with patch.object(self.module.subprocess, 'run', return_value=failure) as run:
            with self.assertRaises(RuntimeError) as failure_context:
                self.module.run_cli('cli', ['debug-files', 'upload'], TOKEN)
            self.assertNotIn(TOKEN, str(failure_context.exception))
            self.assertIn('[REDACTED]', str(failure_context.exception))
            command = run.call_args.args[0]
            self.assertNotIn(TOKEN, command)
            self.assertEqual(run.call_args.kwargs['env']['SENTRY_AUTH_TOKEN'], TOKEN)
            self.assertEqual(command[1:3], ['--url', 'https://sentry.io'])

    def test_cli_failure_retains_missing_ids_from_stdout_and_redacts_both_streams(self):
        failure = SimpleNamespace(returncode=1, stderr='Some symbols missing ' + TOKEN,
                                  stdout='missing-debug-id ' + TOKEN)
        with patch.object(self.module.subprocess, 'run', return_value=failure):
            with self.assertRaises(RuntimeError) as result:
                self.module.run_cli('cli', ['debug-files', 'upload'], TOKEN)
        self.assertIn('Some symbols missing', str(result.exception))
        self.assertIn('missing-debug-id', str(result.exception))
        self.assertNotIn(TOKEN, str(result.exception))

    def test_repeat_publication_verifies_existing_files_without_reupload(self):
        remote_release = None
        calls = []
        def request(method, path, token, body=None, allow_missing=False):
            nonlocal remote_release
            calls.append((method, path, body))
            if method == 'POST':
                remote_release = self.provider_release()
            return remote_release, None
        def listing(path, token):
            if 'commits/' in path:
                return self.provider_commits()
            return self.provider_files()
        with patch.object(self.module, 'verify', side_effect=self.manifests) as verify, \
                patch.object(self.module, 'run_cli', return_value='sentry-cli 3.8.0') as cli, \
                patch.object(self.module, 'api_request', side_effect=request), patch.object(self.module, 'api_list', side_effect=listing):
            result = self.call_publish()
        self.assertEqual(verify.call_count, 2)
        self.assertFalse(any('code-mappings' in call[1] for call in calls))
        self.assertFalse(any(call.args[1][:2] == ['debug-files', 'upload'] for call in cli.call_args_list))
        self.assertEqual(cli.call_args_list[-1].args[1], ["releases", "finalize", "--org", "amplifier-ai", "--project", "unity-plugin", RELEASE])
        stored = self.receipt.read_text()
        self.assertNotIn(TOKEN, stored)
        self.assertEqual(json.loads(stored)['outcome'], 'passed')
        self.assertEqual(len(result['files']), 2)

    def test_missing_files_upload_keeps_require_all_and_exact_ids(self):
        uploaded = False
        def command(cli, arguments, token):
            nonlocal uploaded
            if arguments[:2] == ['debug-files', 'upload']:
                uploaded = True
            return 'sentry-cli 3.8.0'
        def listing(path, token):
            if 'commits/' in path:
                return self.provider_commits()
            return self.provider_files() if uploaded else self.provider_files()[:1]
        with patch.object(self.module, 'verify', side_effect=self.manifests), \
                patch.object(self.module, 'run_cli', side_effect=command) as cli, \
                patch.object(self.module, 'api_request', return_value=(self.provider_release(), None)), \
                patch.object(self.module, 'api_list', side_effect=listing):
            result = self.call_publish()
        upload = next(call.args[1] for call in cli.call_args_list if call.args[1][:2] == ['debug-files', 'upload'])
        self.assertIn('--wait', upload)
        self.assertIn('--require-all', upload)
        self.assertEqual([upload[i+1] for i, word in enumerate(upload) if word == '--id'], IDS[1:])
        self.assertEqual(len(result['files']), 2)

    def test_missing_readback_preserves_existing_receipt(self):
        prior = {'repository': 'amplifier-ai/vtk', 'organization': 'amplifier-ai', 'project': 'unity-plugin',
                 'release': RELEASE, 'source_revision': REVISION, 'outcome': 'old-receipt'}
        self.receipt.write_text(json.dumps(prior))
        def listing(path, token):
            if 'commits/' in path: return self.provider_commits()
            return []
        with patch.object(self.module, 'verify', side_effect=self.manifests), \
                patch.object(self.module, 'run_cli', return_value='sentry-cli 3.8.0'), \
                patch.object(self.module, 'api_request', return_value=(self.provider_release(), None)), \
                patch.object(self.module, 'api_list', side_effect=listing):
            with self.assertRaisesRegex(RuntimeError, 'processed'):
                self.call_publish()
        self.assertEqual(json.loads(self.receipt.read_text()), prior)


if __name__ == '__main__':
    unittest.main()
