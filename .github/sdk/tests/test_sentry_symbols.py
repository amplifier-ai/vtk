import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest
import zipfile


HELPER = Path(__file__).resolve().parents[1] / "sentry_symbols.py"
sys.path.insert(0, str(HELPER.parent))
ID = "01234567-89ab-cdef-0123-456789abcdef-1"


class SymbolContracts(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.is_file(), "VTK needs verified symbol/source publication")
        spec = importlib.util.spec_from_file_location("sentry_symbols", HELPER)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.build = self.root / "build"
        self.source.mkdir()
        self.build.mkdir()
        (self.source / "file.cxx").write_text("int original() { return 1; }\n")
        (self.build / "generated.cxx").write_text("int generated() { return 2; }\n")

    def info(self, debug_id=ID, arch="x86_64", features="symtab, debug"):
        return {"type": "pdb", "variants": [{"debug_id": debug_id, "code_id": None, "arch": arch}],
                "features": features, "is_usable": True}

    def bundle(self, files, debug_id=ID):
        path = self.root / "sources.src.zip"
        with path.open("wb") as stream:
            stream.write(b"SYSB\x02\x00\x00\x00")
            with zipfile.ZipFile(stream, "w") as archive:
                manifest = {"debug_id": debug_id, "arch": "x86_64", "files": {}}
                for number, (original, content) in enumerate(files):
                    name = f"files/{number}.cxx"
                    archive.writestr(name, content)
                    manifest["files"][name] = {"type": "source", "path": str(original)}
                archive.writestr("manifest.json", json.dumps(manifest))
        return path

    def test_binary_and_symbol_must_share_complete_identity_and_architecture(self):
        binary = self.module.decode_info(self.info(features="symtab, unwind"))
        symbols = self.module.decode_info(self.info())
        self.module.require_pair(binary, symbols)
        for invalid in [self.info(debug_id=ID[:-1] + "2"), self.info(arch="arm64"),
                        self.info(features="symtab")]:
            with self.subTest(invalid=invalid), self.assertRaises(RuntimeError):
                self.module.require_pair(binary, self.module.decode_info(invalid))

    def test_source_bundle_contains_exact_tracked_and_generated_bytes(self):
        path = self.bundle([(self.source / "file.cxx", (self.source / "file.cxx").read_bytes()),
                            (self.build / "generated.cxx", (self.build / "generated.cxx").read_bytes())])
        coverage = self.module.verify_sources(path, self.source, self.build, ID)
        self.assertEqual({item['kind'] for item in coverage}, {'tracked', 'generated'})
        (self.build / "generated.cxx").write_text("changed after compilation")
        with self.assertRaisesRegex(RuntimeError, "source bytes"):
            self.module.verify_sources(path, self.source, self.build, ID)

    def test_missing_sources_wrong_id_and_plain_zip_are_rejected(self):
        for files, identity in [([], ID), ([(self.source / "file.cxx", b"wrong")], ID),
                                ([(self.source / "file.cxx", (self.source / "file.cxx").read_bytes())], "wrong")]:
            path = self.bundle(files, identity)
            with self.subTest(files=files, identity=identity), self.assertRaises(RuntimeError):
                self.module.verify_sources(path, self.source, self.build, ID)
        path.write_bytes(path.read_bytes()[8:])
        with self.assertRaisesRegex(RuntimeError, "source bundle header"):
            self.module.verify_sources(path, self.source, self.build, ID)

    def test_source_urls_freeze_exact_commit_and_do_not_invent_generated_git_files(self):
        path = self.bundle([(self.source / "file.cxx", (self.source / "file.cxx").read_bytes()),
                            (self.build / "generated.cxx", (self.build / "generated.cxx").read_bytes())])
        self.module.add_source_urls(path, self.source, self.build, "a" * 40)
        self.assertTrue(path.read_bytes().startswith(b"SYSB\x02\x00\x00\x00"))
        with zipfile.ZipFile(path) as archive:
            entries = list(json.loads(archive.read('manifest.json'))['files'].values())
        self.assertEqual(entries[0]['url'], 'https://raw.githubusercontent.com/amplifier-ai/vtk/' + 'a' * 40 + '/file.cxx')
        self.assertNotIn('url', entries[1])

    def test_supplier_paths_do_not_count_as_verified_vtk_source_coverage(self):
        supplier = self.root / "supplier.cxx"
        supplier.write_text("external")
        with self.assertRaisesRegex(RuntimeError, "VTK source"):
            self.module.verify_sources(self.bundle([(supplier, b"external")]), self.source, self.build, ID)

    def test_referenced_generated_source_cannot_silently_disappear(self):
        path = self.bundle([(self.source / "file.cxx", (self.source / "file.cxx").read_bytes())])
        referenced = f"macho {ID} references sources:\n  {self.source / 'file.cxx'}\n    Available.\n  {self.build / 'generated.cxx'}\n    Missing.\n"
        with self.assertRaisesRegex(RuntimeError, "Referenced VTK source missing"):
            self.module.verify_referenced_sources(path, referenced, self.source, self.build)

    def test_frozen_source_coverage_validates_payload_without_runner_paths(self):
        path = self.bundle([(self.source / "file.cxx", (self.source / "file.cxx").read_bytes())])
        coverage = self.module.verify_sources(path, self.source, self.build, ID)
        self.module.add_source_urls(path, self.source, self.build, "a" * 40)
        self.module.verify_frozen_sources(path, coverage, "a" * 40)
        changed = self.bundle([(self.source / "file.cxx", b"corrupt")])
        with self.assertRaisesRegex(RuntimeError, "Frozen source"):
            self.module.verify_frozen_sources(changed, coverage, "a" * 40)

    def test_generated_cpp_include_fragments_have_verified_bytes_and_no_fictitious_git_url(self):
        fragment = self.build / "vtkAffineImplicitBackendInstantiate_char.cxx.inc"
        fragment.write_text("template class Backend<char>;\n")
        path = self.bundle([(fragment, fragment.read_bytes())])
        coverage = self.module.verify_sources(path, self.source, self.build, ID)
        self.assertEqual(coverage[0]["kind"], "generated")
        self.module.add_source_urls(path, self.source, self.build, "a" * 40)
        self.module.verify_frozen_sources(path, coverage, "a" * 40)
        self.assertNotIn("url", next(iter(self.module.read_bundle(path)["files"].values())))
        fragment.write_text("changed generated instantiation\n")
        with self.assertRaisesRegex(RuntimeError, "source bytes"):
            self.module.verify_sources(path, self.source, self.build, ID)

    def test_referenced_cpp_include_fragment_is_required_even_when_other_source_is_present(self):
        fragment = self.build / "vtkAffineImplicitBackendInstantiate_char.cxx.inc"
        fragment.write_text("template class Backend<char>;\n")
        path = self.bundle([(self.source / "file.cxx", (self.source / "file.cxx").read_bytes())])
        listing = f"macho {ID} references sources:\n  {fragment}\n    Available.\n"
        with self.assertRaisesRegex(RuntimeError, "Referenced VTK source missing"):
            self.module.verify_referenced_sources(path, listing, self.source, self.build)

    def test_eigen_extensionless_headers_keep_exact_bytes_and_immutable_source_urls(self):
        header = self.source / "ThirdParty/eigen/vtkeigen/eigen/Core"
        header.parent.mkdir(parents=True)
        header.write_text("template <class T> struct Matrix { T value; };\n")
        path = self.bundle([(header, header.read_bytes())])
        coverage = self.module.verify_sources(path, self.source, self.build, ID)
        self.assertEqual(coverage[0]["kind"], "tracked")
        self.module.add_source_urls(path, self.source, self.build, "a" * 40)
        self.module.verify_frozen_sources(path, coverage, "a" * 40)
        self.assertTrue(next(iter(self.module.read_bundle(path)["files"].values()))["url"].endswith("/eigen/Core"))
        header.write_text("changed header\n")
        with self.assertRaisesRegex(RuntimeError, "source bytes"):
            self.module.verify_sources(path, self.source, self.build, ID)

    def test_referenced_eigen_extensionless_header_cannot_silently_disappear(self):
        header = self.source / "ThirdParty/eigen/vtkeigen/eigen/Core"
        header.parent.mkdir(parents=True)
        header.write_text("template <class T> struct Matrix {};\n")
        path = self.bundle([(self.source / "file.cxx", (self.source / "file.cxx").read_bytes())])
        with self.assertRaisesRegex(RuntimeError, "Referenced VTK source missing"):
            self.module.verify_referenced_sources(path, f"macho {ID} references sources:\n  {header}\n", self.source, self.build)


if __name__ == "__main__":
    unittest.main()
