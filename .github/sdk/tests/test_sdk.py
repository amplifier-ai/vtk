import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest


PACKAGER = Path(__file__).resolve().parents[1] / "package_sdk.py"


class NativeSDKPackaging(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PACKAGER.is_file(), "Native SDK release packaging is not implemented")
        spec = importlib.util.spec_from_file_location("package_sdk", PACKAGER)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sdk = self.root / "sdk"
        self.build = self.root / "build"
        self.source = self.root / "source"
        self.output = self.root / "packages"
        for path in [self.build, self.source / "CMake", self.sdk / "include/vtk-9.7",
                     self.sdk / "lib/cmake/vtk-9.7", self.sdk / "bin"]:
            path.mkdir(parents=True)
        (self.source / "CMake/vtkVersion.cmake").write_text(
            "set(VTK_MAJOR_VERSION 9)\nset(VTK_MINOR_VERSION 7)\nset(VTK_BUILD_VERSION 1)\n")
        for args in [["init", "-q"], ["config", "user.name", "SDK test"],
                     ["config", "user.email", "sdk-test@example.invalid"],
                     ["add", "."], ["commit", "-qm", "SDK fixture"]]:
            subprocess.run(["git", "-C", str(self.source), *args], check=True)
        for name in ["vtkVersion.h", "vtkType.h", "vtkExternalOpenGLCamera.h"]:
            (self.sdk / "include/vtk-9.7" / name).write_text("// fixture\n")
        (self.sdk / "lib/cmake/vtk-9.7/vtk-config.cmake").write_text("# installed fixture\n")
        (self.sdk / "lib/cmake/vtk-9.7/VTK-targets.cmake").write_text("# relocatable targets\n")
        (self.sdk / "lib/libvtkCommonCore-9.7.1.dylib").write_bytes(b"runtime fixture")
        (self.sdk / "lib/libvtkCommonCore-9.7.dylib").symlink_to("libvtkCommonCore-9.7.1.dylib")
        self.cache = {
            "CMAKE_BUILD_TYPE": "Release", "BUILD_SHARED_LIBS": "ON", "VTK_INSTALL_SDK": "ON",
            "VTK_USE_64BIT_IDS": "ON", "VTK_USE_FUTURE_BOOL": "OFF", "VTK_USE_FUTURE_CONST": "OFF",
            "VTK_SMP_IMPLEMENTATION_TYPE": "Sequential", "CMAKE_OSX_ARCHITECTURES": "arm64",
            "CMAKE_OSX_DEPLOYMENT_TARGET": "14.0",
        }
        self.write_cache()

    def write_cache(self):
        (self.build / "CMakeCache.txt").write_text(
            "".join(f"{key}:STRING={value}\n" for key, value in self.cache.items()))

    def package(self):
        return self.module.package_sdk(self.sdk, self.build, self.source, "osx-arm64", self.output)

    def test_archive_preserves_libraries_and_relative_symlinks(self):
        archive = self.package()
        checksum = Path(str(archive) + ".sha256").read_text().split()[0]
        self.assertEqual(checksum, hashlib.sha256(archive.read_bytes()).hexdigest())
        relocated = self.root / "relocated"
        self.module.extract_sdk(archive, relocated)
        self.module.validate_manifest(relocated)
        self.assertTrue((relocated / "lib/libvtkCommonCore-9.7.dylib").is_symlink())
        manifest = json.loads((relocated / "sdk-manifest.json").read_text())
        self.assertEqual(manifest["vtk_version"], "9.7.1")
        self.assertEqual(manifest["platform"], "osx-arm64")
        self.assertEqual(len(manifest["source_revision"]), 40)

    def test_missing_development_header_refuses_package(self):
        (self.sdk / "include/vtk-9.7/vtkExternalOpenGLCamera.h").unlink()
        with self.assertRaisesRegex(RuntimeError, "header"):
            self.package()

    def test_windows_archive_uses_installed_dlls_and_import_libraries(self):
        for path in (self.sdk / "lib").glob("*.dylib"):
            path.unlink()
        (self.sdk / "bin/vtkCommonCore-9.7.dll").write_bytes(b"windows runtime fixture")
        (self.sdk / "lib/vtkCommonCore-9.7.lib").write_bytes(b"windows import fixture")
        archive = self.module.package_sdk(self.sdk, self.build, self.source, "win-x64", self.output)
        self.assertEqual(archive.suffix, ".zip")
        relocated = self.root / "relocated"
        self.module.extract_sdk(archive, relocated)
        manifest = self.module.validate_manifest(relocated)
        self.assertEqual(manifest["platform"], "win-x64")
        self.assertEqual((relocated / "lib/vtkCommonCore-9.7.lib").read_bytes(), b"windows import fixture")

    def test_different_abi_profile_refuses_package(self):
        self.cache["VTK_USE_64BIT_IDS"] = "OFF"
        self.write_cache()
        with self.assertRaisesRegex(RuntimeError, "VTK_USE_64BIT_IDS"):
            self.package()

    def test_absolute_build_path_in_cmake_refuses_package(self):
        (self.sdk / "lib/cmake/vtk-9.7/VTK-targets.cmake").write_text(str(self.build))
        with self.assertRaisesRegex(RuntimeError, "build.*path"):
            self.package()

    def test_changed_library_fails_manifest_validation(self):
        archive = self.package()
        relocated = self.root / "relocated"
        self.module.extract_sdk(archive, relocated)
        (relocated / "lib/libvtkCommonCore-9.7.1.dylib").write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "digest"):
            self.module.validate_manifest(relocated)

    def test_archive_path_traversal_is_rejected(self):
        archive = self.root / "unsafe.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            item = tarfile.TarInfo("../outside")
            bundle.addfile(item)
        with self.assertRaisesRegex(RuntimeError, "archive.*path"):
            self.module.extract_sdk(archive, self.root / "relocated")
        self.assertFalse((self.root / "outside").exists())

    def test_symlink_outside_sdk_is_rejected(self):
        (self.sdk / "lib/escape").symlink_to(self.root)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.package()


if __name__ == "__main__":
    unittest.main()
