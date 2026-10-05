import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1] / "build_installable.py"


class InstallableTargets(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.is_file(), "Installed SDK targets are not completed from the shared build")
        spec = importlib.util.spec_from_file_location("build_installable", HELPER)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.build = Path(self.temp.name)
        self.reply = self.build / ".cmake/api/v1/reply"
        self.reply.mkdir(parents=True)
        (self.reply / "index-2026-10-05.json").write_text(json.dumps(
            {"reply": {"codemodel-v2": {"jsonFile": "model.json"}}}))

    def targets(self, items):
        links = []
        for i, item in enumerate(items):
            name = f"target-{i}.json"
            (self.reply / name).write_text(json.dumps(item))
            links.append({"jsonFile": name})
        (self.reply / "model.json").write_text(json.dumps(
            {"configurations": [{"name": "Release", "targets": links}]}))

    def test_completes_installed_libraries_and_tools_but_not_test_executables(self):
        self.targets([
            {"name": "vtkCommonCore", "type": "SHARED_LIBRARY", "install": {"destinations": [{}]}},
            {"name": "vtkProbeOpenGLVersion", "type": "EXECUTABLE", "install": {"destinations": [{}]}},
            {"name": "TestRendering", "type": "EXECUTABLE"},
            {"name": "VTKCSharpTests", "type": "UTILITY"},
            {"name": "generate_proj_db", "type": "UTILITY"},
        ])
        self.assertEqual(self.module.installed_targets(self.build),
                         ["generate_proj_db", "vtkCommonCore", "vtkProbeOpenGLVersion"])

    def test_missing_cmake_reply_is_an_error(self):
        (self.reply / "index-2026-10-05.json").unlink()
        with self.assertRaisesRegex(RuntimeError, "File API"):
            self.module.installed_targets(self.build)

    def test_prepare_requests_codemodel_without_another_configuration(self):
        self.module.prepare(self.build)
        self.assertTrue((self.build / ".cmake/api/v1/query/codemodel-v2").is_file())


if __name__ == "__main__":
    unittest.main()
