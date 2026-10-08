"""Exercise the Release symbol profile with real, bounded native builds."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SDK = Path(__file__).resolve().parents[1]
SENTRY_CLI = os.environ.get("SENTRY_CLI") or shutil.which("sentry-cli")
SUPPORTED = sys.platform in ("win32", "darwin")
COMPILER = shutil.which("cl" if sys.platform == "win32" else "clang++")
NATIVE_SOURCES = {
    "owned": ("owned.c", "owned.cxx", "html5ent.inc", "iso8859x.inc"),
    "wrapper": ("wrapper.cxx", "fragment.cxx.inc", "Core", "template.tpp", "octree"),
    "helper": ("helper.cxx",),
    "vendor": ("vendor.c",),
    "installed_tool": ("tool.c",),
}


def run(command):
    result = subprocess.run([str(arg) for arg in command], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    if result.returncode:
        raise AssertionError(f"Command failed ({result.returncode}): {command}\n{result.stdout}")
    return result.stdout


@unittest.skipUnless(SUPPORTED and COMPILER and shutil.which("cmake") and shutil.which("ninja"),
                     "Requires the producer platform's compiler, CMake and Ninja")
class NativeSymbolProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="vtk-symbol-profile-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / "source"
        shutil.copytree(SDK / "symbol-fixture", cls.source)
        run(["git", "init", "-q", cls.source])
        run(["git", "-C", cls.source, "add", "."])
        run(["git", "-C", cls.source, "-c", "user.name=Native fixture", "-c", "user.email=fixture@example.invalid",
             "-c", "commit.gpgsign=false", "commit", "-qm", "Native fixture sources"])
        cls.build = cls.root / "build"
        cls.sdk = cls.root / "sdk"
        query = cls.build / ".cmake/api/v1/query/codemodel-v2"
        query.parent.mkdir(parents=True)
        query.touch()
        command = ["cmake", "-G", "Ninja", "-S", cls.source, "-B", cls.build,
                   "-C", SDK / "native-sdk.cmake", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
                   f"-DCMAKE_INSTALL_PREFIX={cls.sdk}"]
        if sys.platform == "darwin":
            command += ["-DCMAKE_C_COMPILER=clang", "-DCMAKE_CXX_COMPILER=clang++",
                        "-DCMAKE_OSX_ARCHITECTURES=arm64", "-DCMAKE_OSX_DEPLOYMENT_TARGET=26.0"]
        else:
            command += ["-DCMAKE_C_COMPILER=cl", "-DCMAKE_CXX_COMPILER=cl"]
        run(command)
        run(["cmake", "--build", cls.build, "--config", "Release", "--parallel", "2"])
        run(["cmake", "--install", cls.build, "--config", "Release"])
        cls.artifacts = {name: Path((cls.build / "artifacts" / f"{name}.path").read_text().strip())
                         for name in NATIVE_SOURCES}
        cls.cache = dict(re.findall(r"^([^#/:\n]+):[^=\n]+=(.*)$",
                                   (cls.build / "CMakeCache.txt").read_text(), re.MULTILINE))

    def test_release_keeps_optimization_and_full_compile_debug_information(self):
        self.assertEqual(self.cache["CMAKE_BUILD_TYPE"], "Release")
        commands = json.loads((self.build / "compile_commands.json").read_text())
        self.assertTrue(any(row["file"].endswith("generated/wrapper.cxx") for row in commands))
        self.assertTrue(any(row["file"].endswith("owned.c") for row in commands))
        for row in commands:
            command = row.get("command", " ".join(row.get("arguments", [])))
            with self.subTest(source=row["file"]):
                if sys.platform == "win32":
                    for flag in ("/O2", "/Ob2", "/DNDEBUG", "/Z7"):
                        self.assertIn(flag, command)
                    self.assertNotRegex(command, r"(?:^|\s)/Z[iI](?:\s|$)")
                else:
                    for flag in ("-O3", "-DNDEBUG", "-g", "-mmacosx-version-min=26.0"):
                        self.assertIn(flag, command.split())

    def test_installed_target_graph_covers_native_wrappers_and_embedded_dependencies(self):
        spec = importlib.util.spec_from_file_location("symbol_fixture_installable", SDK / "build_installable.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(set(module.installed_targets(self.build)),
                         {*NATIVE_SOURCES, "fixture_static"})
        run([self.artifacts["installed_tool"]])

    @unittest.skipUnless(sys.platform == "win32", "Requires the Windows MSVC producer")
    def test_windows_linker_pdbs_cover_every_installed_native_binary(self):
        for kind in ("EXE", "SHARED", "MODULE"):
            flags = self.cache[f"CMAKE_{kind}_LINKER_FLAGS_RELEASE"]
            for flag in ("/DEBUG:FULL", "/OPT:REF", "/OPT:ICF", "/INCREMENTAL:NO"):
                self.assertIn(flag, flags)
        for name in NATIVE_SOURCES:
            with self.subTest(target=name):
                pdb = Path((self.build / "artifacts" / f"{name}.pdb-path").read_text().strip())
                self.assertEqual(pdb.parent, self.build / "native-pdb")
                self.assertGreater(pdb.stat().st_size, 0)

    def dsym(self, name):
        if not shutil.which("dsymutil"):
            self.skipTest("Requires Apple's dsymutil")
        output = self.root / "dsyms" / f"{name}.dSYM"
        if not output.exists():
            output.parent.mkdir(exist_ok=True)
            run(["dsymutil", self.artifacts[name], "-o", output])
        return output / "Contents/Resources/DWARF" / self.artifacts[name].name

    @unittest.skipUnless(sys.platform == "darwin" and shutil.which("dwarfdump"),
                         "Requires Apple's Mach-O tools")
    def test_macos_dsyms_match_uuids_and_include_native_and_generated_sources(self):
        self.assertEqual(self.cache["CMAKE_OSX_ARCHITECTURES"], "arm64")
        self.assertEqual(self.cache["CMAKE_OSX_DEPLOYMENT_TARGET"], "26.0")
        for name, sources in NATIVE_SOURCES.items():
            with self.subTest(target=name):
                dsym = self.dsym(name)
                identities = lambda path: set(re.findall(r"UUID: ([0-9A-F-]+) \(([^)]+)\)",
                                                          run(["dwarfdump", "--uuid", path])))
                binary_ids = identities(self.artifacts[name])
                self.assertTrue(binary_ids)
                self.assertEqual(binary_ids, identities(dsym))
                lines = run(["dwarfdump", "--debug-line", dsym])
                for source in sources:
                    self.assertIn(source, lines)

    @unittest.skipUnless(SENTRY_CLI, "Set SENTRY_CLI to check native debug identities with Sentry CLI")
    def test_sentry_cli_matches_each_binary_to_its_debug_file(self):
        def identity(path):
            report = json.loads(run([SENTRY_CLI, "debug-files", "check", "--json", path]))
            self.assertTrue(report["is_usable"], str(path))
            ids = {item["debug_id"] for item in report["variants"]}
            self.assertTrue(ids)
            return ids, report

        for name in NATIVE_SOURCES:
            with self.subTest(target=name):
                if sys.platform == "win32":
                    debug_file = Path((self.build / "artifacts" / f"{name}.pdb-path").read_text().strip())
                else:
                    debug_file = self.dsym(name)
                binary_ids, _ = identity(self.artifacts[name])
                symbol_ids, report = identity(debug_file)
                self.assertEqual(binary_ids, symbol_ids)
                self.assertIn("debug", report["features"].split(", "))

    @unittest.skipUnless(SENTRY_CLI, "Set SENTRY_CLI to exercise complete source staging")
    def test_symbol_collector_freezes_installed_modules_wrappers_generated_sources_and_ids(self):
        sys.path.insert(0, str(SDK))
        self.addCleanup(sys.path.remove, str(SDK))
        import sentry_symbols as collector
        runtime = self.root / "runtime"
        runtime.mkdir()
        for name in ("owned", "wrapper", "helper", "vendor"):
            shutil.copy2(self.artifacts[name], runtime / self.artifacts[name].name)
        revision = run(["git", "-C", self.source, "rev-parse", "HEAD"]).strip()
        tree = run(["git", "-C", self.source, "rev-parse", "HEAD^{tree}"]).strip()
        platform = "win-x64" if sys.platform == "win32" else "osx-arm64"
        identity = {"source_revision": revision, "source_tree": tree, "platform": platform,
                    "vtk_version": "9.7.1", "configuration": {"CMAKE_BUILD_TYPE": "Release"}}
        packages = self.root / "packages"
        packages.mkdir()
        extension = "zip" if sys.platform == "win32" else "tar.gz"
        for product in ("sdk", "csharp"):
            (packages / f"vtk-{product}-{platform}.{extension}").write_bytes(b"fixture archive identity")
        with mock.patch.object(collector, "validate_manifest", return_value={**identity, "files": collector.inventory(self.sdk)}), \
             mock.patch.object(collector, "validate_runtime_manifest", return_value={**identity, "files": collector.inventory(runtime)}):
            manifest = collector.prepare(self.sdk, runtime, self.build, self.source, self.root / "symbols",
                                         platform, SENTRY_CLI, packages)
        self.assertEqual({row['target'] for row in manifest['modules']}, set(NATIVE_SOURCES))
        self.assertTrue(any(row['kind'] == 'generated' for module in manifest['modules']
                            for row in module['source_coverage']))
        self.assertTrue(any(row['kind'] == 'generated' and row['path'].endswith('fragment.cxx.inc')
                            for module in manifest['modules'] for row in module['source_coverage']))
        self.assertTrue(any(row['kind'] == 'tracked' and row['path'] == 'ThirdParty/eigen/vtkeigen/eigen/Core'
                            for module in manifest['modules'] for row in module['source_coverage']))
        self.assertTrue(any(row['kind'] == 'tracked' and row['path'] == 'template.tpp'
                            for module in manifest['modules'] for row in module['source_coverage']))
        for path in ('ThirdParty/libxml2/vtklibxml2/html5ent.inc',
                     'ThirdParty/libxml2/vtklibxml2/iso8859x.inc', 'Utilities/octree/octree/octree'):
            self.assertTrue(any(row['kind'] == 'tracked' and row['path'] == path
                                for module in manifest['modules'] for row in module['source_coverage']))
        self.assertEqual(manifest, collector.verify(self.root / "symbols", revision, SENTRY_CLI))


if __name__ == "__main__":
    unittest.main()
