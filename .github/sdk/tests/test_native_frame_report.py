"""Validate the native module report using a real loaded shared library."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SDK = Path(__file__).resolve().parents[1]
AVAILABLE = (sys.platform in ("win32", "darwin") and shutil.which("cmake")
             and shutil.which("ninja") and shutil.which("cl" if sys.platform == "win32" else "clang++"))


def run(command, expected=0):
    result = subprocess.run([str(item) for item in command], capture_output=True, text=True, timeout=120)
    if result.returncode != expected:
        raise AssertionError(f"Command returned {result.returncode}: {command}\n{result.stdout}\n{result.stderr}")
    return result


@unittest.skipUnless(AVAILABLE, "Requires a native producer platform, compiler, CMake and Ninja")
class NativeFrameReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="vtk-native-frame-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        source = cls.root / "source"
        source.mkdir()
        header = (SDK / "consumer").as_posix()
        (source / "CMakeLists.txt").write_text(
            'cmake_minimum_required(VERSION 4.0)\nproject(NativeFrameFixture LANGUAGES CXX)\n'
            'set(CMAKE_CXX_STANDARD 17)\nset(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)\n'
            'set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")\n'
            'add_library(frame_fixture SHARED library.cxx)\n'
            'add_executable(frame_driver driver.cxx)\n'
            f'target_include_directories(frame_driver PRIVATE "{header}")\n'
            'target_link_libraries(frame_driver PRIVATE frame_fixture ${CMAKE_DL_LIBS})\n'
            'file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/driver.path" CONTENT "$<TARGET_FILE:frame_driver>\\n")\n'
            'file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/library.path" CONTENT "$<TARGET_FILE:frame_fixture>\\n")\n')
        (source / "library.cxx").write_text('extern "C" int FixtureSymbol() { return 7; }\n')
        (source / "driver.cxx").write_text(r'''
#include "native_frame_report.h"
#include <iostream>
#if defined(_WIN32)
extern "C" __declspec(dllimport) int FixtureSymbol();
#else
extern "C" int FixtureSymbol();
#endif
int main(int argc, char* argv[])
{
  if (argc != 3) { return 3; }
  int local = 0;
  const void* address = std::string(argv[2]) == "invalid"
    ? static_cast<const void*>(&local) : reinterpret_cast<const void*>(&FixtureSymbol);
  try
  {
    native_sdk::WriteNativeFrameReport(argv[1], address, argv[2]);
  }
  catch (const std::exception& error)
  {
    std::cerr << error.what() << std::endl;
    return 2;
  }
  return 0;
}
''')
        cls.driver = None

    def ensure_fixture(self):
        cls = type(self)
        if cls.driver is not None:
            return
        source = cls.root / "source"
        build = cls.root / "build"
        run(["cmake", "-G", "Ninja", "-S", source, "-B", build,
             "-C", SDK / "native-sdk.cmake"])
        run(["cmake", "--build", build, "--config", "Release", "--parallel", "2"])
        cls.driver = Path((build / "driver.path").read_text().strip())
        cls.library = Path((build / "library.path").read_text().strip()).resolve()

    def test_function_address_is_inside_the_actual_loaded_library(self):
        self.ensure_fixture()
        report = self.root / "frame.json"
        run([self.driver, report, "FixtureSymbol"])
        data = json.loads(report.read_text())
        self.assertEqual(data["schema_version"], 1)
        self.assertIs(data["synthetic"], True)
        self.assertEqual(data["probe_function"], "FixtureSymbol")
        self.assertEqual(Path(data["module_path"]).resolve(), self.library)
        self.assertEqual(data["image_type"], "pe" if sys.platform == "win32" else "macho")
        base, address = int(data["image_addr"], 16), int(data["instruction_addr"], 16)
        self.assertGreater(base, 0)
        self.assertGreater(data["image_size"], 0)
        self.assertLessEqual(base, address)
        self.assertLess(address, base + data["image_size"])

    def test_report_is_valid_json_with_quotes_and_backslashes(self):
        self.ensure_fixture()
        report = self.root / "escaped-frame.json"
        function = 'Fixture "quoted" \\ symbol'
        run([self.driver, report, function])
        self.assertEqual(json.loads(report.read_text())["probe_function"], function)

    def test_non_module_address_is_rejected(self):
        self.ensure_fixture()
        report = self.root / "invalid-frame.json"
        run([self.driver, report, "invalid"], expected=2)
        self.assertFalse(report.exists())


if __name__ == "__main__":
    unittest.main()
