import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HELPER = Path(__file__).resolve().parents[1] / 'qualify_sentry_frame.py'
sys.path.insert(0, str(HELPER.parent))
SHA = 'a' * 40
RELEASE = 'vtk-sdk@9.7.1+' + SHA
DSN = 'https://' + '1' * 32 + '@o4508885211873280.ingest.us.sentry.io/4509486293712896'
TOKEN = 'fixture-token-not-written'


class FrameQualificationContracts(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.is_file(), 'Native frame qualification helper is required')
        specification = importlib.util.spec_from_file_location('qualify_sentry_frame', HELPER)
        self.module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(self.module)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.evidence = self.root / 'evidence'
        self.receipt = self.root / 'qualification.json'
        self.roots = []
        self.manifests = []
        self.source = b'// VTK version\nconst char* vtkVersion::GetVTKVersionFull()\n{\n  return VTK_VERSION_FULL;\n}\n'
        for index, (platform, name, relative, image_type, arch) in enumerate([
                ('win-x64', 'vtkCommonCore-9.7.dll', 'bin/vtkCommonCore-9.7.dll', 'pe', 'x86_64'),
                ('osx-arm64', 'libvtkCommonCore-9.7.1.dylib', 'lib/libvtkCommonCore-9.7.1.dylib', 'macho', 'arm64')]):
            root = self.root / platform
            root.mkdir()
            self.roots.append(root)
            (root / name).write_bytes((platform + 'module').encode())
            module_hash = self.module.digest(root / name)
            debug_id = ('01234567-89ab-cdef-0123-456789abcdef-1' if index == 0 else '12345678-9abc-def0-1234-56789abcdef0')
            original = '/runner/source/Common/Core/vtkVersion.cxx'
            bundle = root / 'sources.src.zip'
            with bundle.open('wb') as stream:
                stream.write(b'SYSB\x02\x00\x00\x00')
                with zipfile.ZipFile(stream, 'w') as archive:
                    archive.writestr('files/version.cxx', self.source)
                    archive.writestr('manifest.json', json.dumps({'debug_id': debug_id, 'files': {
                        'files/version.cxx': {'type': 'source', 'path': original,
                        'url': f'https://raw.githubusercontent.com/amplifier-ai/vtk/{SHA}/Common/Core/vtkVersion.cxx'}}}))
            extension = 'zip' if index == 0 else 'tar.gz'
            manifest = {'platform': platform, 'outcome': 'passed', 'repository': 'amplifier-ai/vtk',
                        'source_revision': SHA, 'run_id': '123', 'archives': {f'vtk-sdk-{platform}.{extension}': 'c' * 64},
                        'modules': [{'name': name, 'debug_id': debug_id, 'arch': arch,
                            'binaries': [{'product': 'sdk', 'package_path': relative, 'sha256': module_hash,
                                          'path': name, 'code_id': None}],
                            'debug': {'path': name + ('.pdb' if index == 0 else '.dwarf')},
                            'sources': {'path': bundle.name, 'sha256': self.module.digest(bundle)},
                            'source_coverage': [{'kind': 'tracked', 'path': 'Common/Core/vtkVersion.cxx',
                                                'original_path': original, 'sha256': hashlib.sha256(self.source).hexdigest()}]}]}
            self.manifests.append(manifest)
            (root / 'sentry-manifest.json').write_text(json.dumps(manifest))
            probe = {'schema_version': 1, 'synthetic': True, 'probe_function': 'vtkVersion::GetVTKVersionFull',
                     'instruction_addr': '0x1040', 'image_addr': '0x1000', 'image_size': 4096,
                     'image_type': image_type, 'module_path': '/relocated/sdk/' + relative,
                     'module_relative_path': relative, 'module_sha256': module_hash}
            directory = self.evidence / platform
            directory.mkdir(parents=True)
            (directory / 'verification.json').write_text(json.dumps({'platform': platform, 'outcome': 'passed',
                'source_revision': SHA, 'archive_sha256': 'c' * 64, 'native_frame_probe': probe}))
        self.environment = patch.dict(os.environ, {'SENTRY_AUTH_TOKEN': TOKEN, 'GITHUB_RUN_ID': '123'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.specifications = self.module.bind_probes(self.roots, self.evidence, SHA, '123')

    def event(self, specification):
        return {'eventID': specification['event_id'], 'platform': 'native', 'release': {'version': RELEASE},
                'tags': [{'key': 'environment', 'value': 'ci-symbol-qualification'}, {'key': 'level', 'value': 'info'}],
                'entries': [{'type': 'threads', 'data': {'values': [{'stacktrace': {'frames': [{
                    'function': 'vtkVersion::GetVTKVersionFull()', 'absPath': '/runner/Common/Core/vtkVersion.cxx',
                    'lineNo': 4, 'context': [[4, '  return VTK_VERSION_FULL;']],
                    'sourceLink': f'https://www.github.com/amplifier-ai/vtk/blob/{SHA}/Common/Core/vtkVersion.cxx#L4'}]}}]}}]}

    def call(self):
        return self.module.qualify(self.roots, self.evidence, SHA, RELEASE, self.receipt, 60)

    def test_observed_probe_is_bound_to_sdk_name_hash_source_and_loaded_image(self):
        self.assertEqual(len(self.specifications), 2)
        probe_path = self.evidence / 'win-x64/verification.json'
        original = json.loads(probe_path.read_text())
        for field, value in [('module_sha256', '0' * 64), ('module_relative_path', 'bin/other.dll'),
                             ('instruction_addr', '0x3000'), ('image_type', 'macho'), ('synthetic', False)]:
            result = copy.deepcopy(original)
            result['native_frame_probe'][field] = value
            probe_path.write_text(json.dumps(result))
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.module.bind_probes(self.roots, self.evidence, SHA, '123')
        probe_path.write_text(json.dumps(original))
        with self.assertRaises(RuntimeError):
            self.module.bind_probes(self.roots, self.evidence, SHA, 'different-run')

    def test_info_payload_contains_only_observed_native_addresses_without_symbolication_hints(self):
        event = self.module.synthetic_event(self.specifications[0], SHA, RELEASE, '123')
        thread = event['threads']['values'][0]
        frame = thread['stacktrace']['frames'][0]
        self.assertEqual(frame['instruction_addr'], '0x1040')
        self.assertEqual(thread['stacktrace']['instruction_addr_adjustment'], 'none')
        self.assertFalse(thread['crashed'])
        self.assertEqual(event['environment'], 'ci-symbol-qualification')
        self.assertEqual(event['level'], 'info')
        for key in ('function', 'filename', 'lineno', 'context_line', 'source_link'):
            self.assertNotIn(key, frame)
        self.assertNotIn('user', event)

    def test_dsn_is_limited_to_approved_official_ingest_host_project_and_public_key(self):
        endpoint, key = self.module.ingest_target(DSN)
        self.assertEqual(endpoint, 'https://o4508885211873280.ingest.us.sentry.io/api/4509486293712896/envelope/')
        self.assertEqual(key, '1' * 32)
        for invalid in [DSN.replace('sentry.io', 'example.com'), DSN.replace('/4509486293712896', '/1'),
                        DSN.replace('https:', 'http:'), DSN.replace('@', ':secret@'), DSN + '?unexpected=1']:
            with self.subTest(dsn=invalid), self.assertRaises(RuntimeError):
                self.module.ingest_target(invalid)

    def test_qualification_requires_processed_function_file_line_exact_context_and_commit_link(self):
        specification = self.specifications[0]
        event = self.event(specification)
        frame = self.module.qualified_frame(event, specification, SHA, RELEASE)
        self.assertEqual(frame['filename'], 'Common/Core/vtkVersion.cxx')
        for key, value in [('function', 'otherFunction'), ('absPath', '/other/file.cxx'), ('lineNo', 0),
                           ('context', []), ('context', [[4, 'wrong source']]),
                           ('sourceLink', event['entries'][0]['data']['values'][0]['stacktrace']['frames'][0]['sourceLink'].replace(SHA, 'b' * 40))]:
            changed = copy.deepcopy(event)
            changed['entries'][0]['data']['values'][0]['stacktrace']['frames'][0][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.module.qualified_frame(changed, specification, SHA, RELEASE)
        changed = copy.deepcopy(event)
        changed['entries'][0]['data']['values'][0]['rawStacktrace'] = changed['entries'][0]['data']['values'][0].pop('stacktrace')
        with self.assertRaises(RuntimeError):
            self.module.qualified_frame(changed, specification, SHA, RELEASE)

    def test_ids_are_deterministic_per_source_run_and_platform_despite_aslr_retry(self):
        probe_path = self.evidence / 'win-x64/verification.json'
        result = json.loads(probe_path.read_text())
        result['native_frame_probe'].update(image_addr='0x5000', instruction_addr='0x5040')
        probe_path.write_text(json.dumps(result))
        retry = self.module.bind_probes(self.roots, self.evidence, SHA, '123')
        self.assertEqual([r['event_id'] for r in retry], [r['event_id'] for r in self.specifications])
        self.assertNotEqual(self.specifications[0]['event_id'], self.specifications[1]['event_id'])

    def test_success_sends_exactly_two_info_events_after_receipt_persistence(self):
        sent = {}
        def sender(dsn, event):
            stored = json.loads(self.receipt.read_text())
            platform = event['tags']['vtk.sdk.platform']
            self.assertEqual(stored['events'][platform]['state'], 'pending')
            self.assertEqual(stored['events'][platform]['event_id'], event['event_id'])
            self.assertNotIn(DSN, self.receipt.read_text())
            self.assertNotIn(TOKEN, self.receipt.read_text())
            sent[event['event_id']] = event
        def api(method, path, token, body=None, allow_missing=False):
            event_id = path.rstrip('/').rsplit('/', 1)[-1]
            specification = next((row for row in self.specifications if row['event_id'] == event_id), None)
            return (self.event(specification) if event_id in sent else None), None
        with patch.object(self.module, 'enabled_dsn', return_value=DSN), \
                patch.object(self.module, 'send_event', side_effect=sender) as send, \
                patch.object(self.module, 'api_request', side_effect=api):
            result = self.call()
            self.assertEqual(send.call_count, 2)
            self.assertEqual(result['outcome'], 'passed')
            self.call()
            self.assertEqual(send.call_count, 2)

    def test_uncertain_send_preserves_attempted_ids_and_retry_only_reads_them(self):
        with patch.object(self.module, 'enabled_dsn', return_value=DSN), \
                patch.object(self.module, 'api_request', return_value=(None, None)), \
                patch.object(self.module, 'send_event', side_effect=[None, RuntimeError('send uncertain')]):
            with self.assertRaisesRegex(RuntimeError, 'uncertain'):
                self.call()
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual({row['state'] for row in receipt['events'].values()}, {'pending'})
        def api(method, path, token, body=None, allow_missing=False):
            event_id = path.rstrip('/').rsplit('/', 1)[-1]
            specification = next(row for row in self.specifications if row['event_id'] == event_id)
            return self.event(specification), None
        with patch.object(self.module, 'api_request', side_effect=api), patch.object(self.module, 'send_event') as sender:
            result = self.call()
            sender.assert_not_called()
            self.assertEqual(result['outcome'], 'passed')

    def test_poll_timeout_keeps_pending_receipt_without_success_claim(self):
        receipt = {'repository': 'amplifier-ai/vtk', 'organization': 'amplifier-ai', 'project': 'unity-plugin',
                   'release': RELEASE, 'source_revision': SHA, 'outcome': 'pending',
                   'events': {row['platform']: {'event_id': row['event_id'], 'state': 'pending'} for row in self.specifications}}
        self.module.write_receipt(self.receipt, receipt)
        with patch.object(self.module.time, 'monotonic', side_effect=[0, 61]), patch.object(self.module, 'api_request') as api:
            with self.assertRaisesRegex(RuntimeError, 'pending'):
                self.module.poll_events(self.specifications, receipt, self.receipt, TOKEN, SHA, RELEASE, 60)
            api.assert_not_called()
        self.assertEqual(json.loads(self.receipt.read_text())['outcome'], 'pending')


if __name__ == '__main__':
    unittest.main()
