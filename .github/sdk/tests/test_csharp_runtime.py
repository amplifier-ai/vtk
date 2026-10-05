import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


SDK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SDK))
from package_sdk import extract_sdk


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, SDK / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CSharpRuntime(unittest.TestCase):
    def setUp(self):
        self.packager = load_module("package_csharp")
        self.verifier = load_module("verify_csharp")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sdk = self.root / "sdk"
        self.build = self.root / "build"
        self.source = self.root / "source"
        self.output = self.root / "artifacts"
        for directory in (self.sdk / "bin", self.sdk / "lib/csharp", self.build, self.source):
            directory.mkdir(parents=True, exist_ok=True)
        (self.source / "Copyright.txt").write_text("VTK fixture license\n")
        (self.build / "CMakeCache.txt").write_text(
            f"CMAKE_HOME_DIRECTORY:INTERNAL={self.source}\n")
        (self.sdk / "sdk-manifest.json").write_text(json.dumps({
            "vtk_version": "9.7.1", "source_revision": "a" * 40,
            "source_tree": "b" * 40, "platform": "osx-arm64",
        }))
        (self.sdk / "lib/csharp/VTK.CSharp.dll").write_bytes(b"managed assembly fixture")

        class FixtureTools:
            def inspect(inner, library):
                return json.loads(library.read_text())

            def rewrite(inner, library, info, replacements):
                data = inner.inspect(library)
                data["dependencies"] = [replacements.get(name, name) for name in data["dependencies"]]
                data["rpaths"] = ["@loader_path"]
                data["identity"] = "@loader_path/" + library.name
                library.write_text(json.dumps(data))

            def sign(inner, library):
                pass

        self.tools = FixtureTools()

    def library(self, path, dependencies=(), rpaths=(), identity=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"dependencies": list(dependencies), "rpaths": list(rpaths),
                                    "identity": identity or "@rpath/" + path.name,
                                    "minimum_macos": "26.0"}))
        return path

    def mac_sdk(self):
        real = self.library(self.sdk / "lib/libvtkCommonCore-9.7.1.dylib")
        (self.sdk / "lib/libvtkCommonCore-9.7.dylib").symlink_to(real.name)
        self.library(self.sdk / "lib/csharp/libvtkCommonCoreCSharp.dylib",
                     ["@rpath/libvtkCommonCore-9.7.dylib"], [str(self.sdk / "lib")])
        self.library(self.sdk / "lib/csharp/libvtkCSharpHelper.dylib",
                     ["@rpath/libvtkCommonCore-9.7.dylib"], [str(self.sdk / "lib")])

    def package(self, platform="osx-arm64", **kwargs):
        return self.packager.package_csharp(
            self.sdk, self.build, self.output, platform, tools=self.tools, **kwargs)

    def test_packaged_archive_keeps_relative_aliases_and_rewrites_build_rpaths(self):
        self.mac_sdk()
        original = (self.sdk / "lib/csharp/libvtkCommonCoreCSharp.dylib").read_bytes()
        self.package()
        archive = self.root / "vtk-csharp-osx-arm64.tar.gz"
        self.packager.archive_csharp(self.output, archive, "osx-arm64")
        relocated = self.root / "relocated"
        extract_sdk(archive, relocated)
        self.packager.validate_runtime_manifest(relocated)
        alias = relocated / "native/libvtkCommonCore-9.7.dylib"
        self.assertTrue(alias.is_symlink())
        self.assertEqual(alias.readlink(), Path("libvtkCommonCore-9.7.1.dylib"))
        wrapped = self.tools.inspect(relocated / "native/libvtkCommonCoreCSharp.dylib")
        self.assertEqual(wrapped["dependencies"], ["@loader_path/libvtkCommonCore-9.7.dylib"])
        self.assertEqual(wrapped["rpaths"], ["@loader_path"])
        self.assertEqual((self.sdk / "lib/csharp/libvtkCommonCoreCSharp.dylib").read_bytes(), original)

    def test_external_runtime_dependency_closure_is_recursive(self):
        self.mac_sdk()
        external = self.root / "brew/lib"
        leaf = self.library(external / "libsecond.1.dylib", ["/usr/lib/libSystem.B.dylib"])
        dependency = self.library(external / "libfirst.1.dylib", [str(leaf)])
        self.library(self.sdk / "lib/libvtkCommonArchive-9.7.1.dylib", [str(dependency)])
        self.package()
        self.assertTrue((self.output / "native/libfirst.1.dylib").is_file())
        self.assertTrue((self.output / "native/libsecond.1.dylib").is_file())
        manifest = self.packager.validate_runtime_manifest(self.output)
        self.assertIn("/usr/lib/libSystem.B.dylib", manifest["system_dependencies"])
        self.assertEqual(self.tools.inspect(self.output / "native/libfirst.1.dylib")["dependencies"],
                         ["@loader_path/libsecond.1.dylib"])

    def test_unresolved_external_dependency_refuses_package(self):
        self.mac_sdk()
        self.library(self.sdk / "lib/libvtkCommonArchive-9.7.1.dylib",
                     ["/missing/libarchive.13.dylib"])
        with self.assertRaisesRegex(RuntimeError, "Unresolved"):
            self.package()

    def test_different_dependency_bytes_with_same_basename_refuse_package(self):
        self.mac_sdk()
        first = self.library(self.root / "first/libcollision.dylib")
        second = self.library(self.root / "second/libcollision.dylib", ["/usr/lib/libSystem.B.dylib"])
        self.library(self.sdk / "lib/libvtkCommonArchive-9.7.1.dylib", [str(first)])
        self.library(self.sdk / "lib/libvtkIOFFMPEG-9.7.1.dylib", [str(second)])
        with self.assertRaisesRegex(RuntimeError, "collision"):
            self.package()

    def test_portable_runtime_validation_rejects_original_absolute_rpath(self):
        self.mac_sdk()
        self.package()
        native = self.output / "native/libvtkCommonCoreCSharp.dylib"
        data = self.tools.inspect(native)
        data["rpaths"] = [str(self.build / "lib")]
        native.write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError, "rpath"):
            self.packager.validate_native_runtime(self.output, "osx-arm64", tools=self.tools)

    def test_external_dependency_cannot_silently_raise_macos_deployment_requirement(self):
        self.mac_sdk()
        library = self.sdk / "lib/libvtkCommonCore-9.7.1.dylib"
        data = self.tools.inspect(library)
        data["minimum_macos"] = "27.0"
        library.write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError, "newer macOS than 26.0"):
            self.package()

    def test_explicit_newer_macos_contract_is_recorded_and_verified(self):
        self.mac_sdk()
        library = self.sdk / "lib/libvtkCommonCore-9.7.1.dylib"
        data = self.tools.inspect(library)
        data["minimum_macos"] = "27.0"
        library.write_text(json.dumps(data))
        result = self.package(minimum_macos="27.0")
        self.assertEqual(result["minimum_macos"], "27.0")
        self.packager.validate_native_runtime(self.output, "osx-arm64", tools=self.tools,
                                             minimum_macos="27.0")
        with self.assertRaisesRegex(RuntimeError, "newer macOS than 26.0"):
            self.packager.validate_native_runtime(self.output, "osx-arm64", tools=self.tools)

    def test_windows_external_dlls_are_included_without_bundling_os_libraries(self):
        manifest = json.loads((self.sdk / "sdk-manifest.json").read_text())
        manifest["platform"] = "win-x64"
        (self.sdk / "sdk-manifest.json").write_text(json.dumps(manifest))
        dependencies = self.root / "vcpkg/bin"
        system = self.root / "Windows/System32"
        self.library(system / "kernel32.dll")
        self.library(dependencies / "archive.dll", ["kernel32.dll"])
        self.library(self.sdk / "bin/vtkCommonCore-9.7.dll", ["archive.dll", "kernel32.dll"])
        self.library(self.sdk / "bin/vtkCommonCoreCSharp.dll", ["vtkCommonCore-9.7.dll"])
        self.library(self.sdk / "bin/vtkCSharpHelper.dll", ["vtkCommonCore-9.7.dll"])
        result = self.package("win-x64", dependency_directories=[dependencies], system_directory=system)
        self.assertTrue((self.output / "native/archive.dll").is_file())
        self.assertFalse((self.output / "native/kernel32.dll").exists())
        self.assertIn("kernel32.dll", result["system_dependencies"])

    def test_windows_vc_runtime_is_bundled_from_redist_instead_of_using_system_copy(self):
        manifest = json.loads((self.sdk / "sdk-manifest.json").read_text())
        manifest["platform"] = "win-x64"
        (self.sdk / "sdk-manifest.json").write_text(json.dumps(manifest))
        redist = self.root / "redist"
        system = self.root / "Windows/System32"
        self.library(system / "vcruntime140.dll")
        self.library(redist / "vcruntime140.dll")
        self.library(self.sdk / "bin/vtkCommonCore-9.7.dll", ["vcruntime140.dll"])
        self.library(self.sdk / "bin/vtkCommonCoreCSharp.dll", ["vtkCommonCore-9.7.dll"])
        self.library(self.sdk / "bin/vtkCSharpHelper.dll", ["vtkCommonCore-9.7.dll"])
        result = self.package("win-x64", system_directory=system, redist_directories=[redist])
        self.assertTrue((self.output / "native/vcruntime140.dll").is_file())
        self.assertNotIn("vcruntime140.dll", result["system_dependencies"])

    def test_windows_vc_runtime_in_system_directory_cannot_hide_missing_redist(self):
        manifest = json.loads((self.sdk / "sdk-manifest.json").read_text())
        manifest["platform"] = "win-x64"
        (self.sdk / "sdk-manifest.json").write_text(json.dumps(manifest))
        system = self.root / "Windows/System32"
        self.library(system / "vcruntime140.dll")
        self.library(self.sdk / "bin/vtkCommonCore-9.7.dll", ["vcruntime140.dll"])
        self.library(self.sdk / "bin/vtkCommonCoreCSharp.dll", ["vtkCommonCore-9.7.dll"])
        self.library(self.sdk / "bin/vtkCSharpHelper.dll", ["vtkCommonCore-9.7.dll"])
        with self.assertRaisesRegex(RuntimeError, "Unresolved.*vcruntime140"):
            self.package("win-x64", system_directory=system, redist_directories=[])

    def test_original_build_is_restored_when_consumer_fails(self):
        (self.build / "marker").write_text("original build")
        with self.assertRaisesRegex(RuntimeError, "consumer failed"):
            with self.verifier.hidden_build(self.build):
                self.assertFalse(self.build.exists())
                raise RuntimeError("consumer failed")
        self.assertEqual((self.build / "marker").read_text(), "original build")
        self.assertFalse(self.build.with_name(self.build.name + ".csharp-verification-hidden").exists())

    def test_original_build_is_restored_even_if_consumer_recreates_its_path(self):
        (self.build / "marker").write_text("original build")
        with self.assertRaisesRegex(RuntimeError, "original restored"):
            with self.verifier.hidden_build(self.build):
                self.build.mkdir()
                (self.build / "unexpected").write_text("owned consumer output")
        self.assertEqual((self.build / "marker").read_text(), "original build")
        preserved, = self.root.glob("build.csharp-unexpected-*")
        self.assertEqual((preserved / "unexpected").read_text(), "owned consumer output")

    def test_verification_environment_removes_build_and_external_native_overrides(self):
        environment = {"PATH": os.pathsep.join([str(self.build / "bin"), "/usr/bin", "/vcpkg/bin"]),
                       "DYLD_LIBRARY_PATH": "/external/lib", "DYLD_FALLBACK_LIBRARY_PATH": "/fallback",
                       "LD_LIBRARY_PATH": "/external/lib", "LD_PRELOAD": "/external/inject.so"}
        result = self.verifier.consumer_environment(environment, self.build, self.output, self.root / "work")
        self.assertNotIn(str(self.build / "bin"), result["PATH"])
        self.assertNotIn("/vcpkg/bin", result["PATH"])
        for name in ("DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "LD_LIBRARY_PATH", "LD_PRELOAD"):
            self.assertNotIn(name, result)

    def test_mac_import_parser_does_not_treat_install_identity_as_dependency(self):
        text = "fixture:\n\t@rpath/libself.dylib (compatibility version 1.0.0, current version 1.0.0)\n\t@rpath/libother.dylib (compatibility version 1.0.0, current version 1.0.0)\n"
        self.assertEqual(self.packager.parse_macos_dependencies(text, "@rpath/libself.dylib"),
                         ["@rpath/libother.dylib"])

    def test_windows_import_parser_includes_delayed_imports(self):
        text = "Image has the following dependencies:\n    KERNEL32.dll\n    archive.dll\nImage has the following delay load dependencies:\n    helper.dll\n  Summary\n"
        self.assertEqual(self.packager.parse_windows_dependencies(text),
                         ["KERNEL32.dll", "archive.dll", "helper.dll"])


if __name__ == "__main__":
    unittest.main()
