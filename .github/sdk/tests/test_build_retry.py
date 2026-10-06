import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SDK = Path(__file__).resolve().parents[1]
HELPER = SDK / "build_with_retry.py"
DENIAL = (
    'FAILED: bin/vtkIONetCDF-9.7.dll lib/vtkIONetCDF-9.7.lib\n'
    'cmd.exe /C "cmake.exe -E vs_link_dll -- link.exe && vcpkg.exe z-applocal"\n'
    'Access is denied.\n'
    'ninja: build stopped: subcommand failed.\n'
)
COMPILE_ERROR = (
    'FAILED: example.cxx.obj\n'
    'cl.exe /c example.cxx\n'
    'example.cxx(3): error C2065: undeclared identifier\n'
    'ninja: build stopped: subcommand failed.\n'
)


class NativeBuildRetry(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.is_file(), "Native builds need bounded link-denial recovery")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.child = self.root / "child.py"
        self.child.write_text(
            "import json, os, sys, time\n"
            "from pathlib import Path\n"
            "calls = Path('calls.json')\n"
            "items = json.loads(calls.read_text()) if calls.exists() else []\n"
            "scenario = json.loads(Path('scenarios.json').read_text())[len(items)]\n"
            "items.append({'argv': sys.argv[1:], 'cwd': str(Path.cwd()), "
            "'sentinel': os.environ['BUILD_RETRY_SENTINEL']})\n"
            "calls.write_text(json.dumps(items))\n"
            "time.sleep(scenario.get('sleep', 0))\n"
            "print(scenario['output'], flush=True)\n"
            "sys.exit(scenario['code'])\n"
        )

    def run_build(self, scenarios, platform="win32", guarded=None, command=None):
        (self.root / "scenarios.json").write_text(json.dumps(scenarios))
        command = command if command is not None else [
            sys.executable, str(self.child), "--build", "existing-build",
            "--config", "Release", "--target", "VTKCSharpAssembly", "VTKCSharpTests"]
        # Only the OS probe is simulated. The CLI, fixture child and guard are
        # real processes; the product CLI exposes no platform override.
        bootstrap = (
            "import importlib.util, sys; from types import SimpleNamespace; "
            f"spec = importlib.util.spec_from_file_location('build_retry', {str(HELPER)!r}); "
            "module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
            f"module.sys = SimpleNamespace(platform={platform!r}, stdout=sys.stdout, stderr=sys.stderr); "
            f"sys.argv = [{str(HELPER)!r}, '--evidence', '.sdk-evidence', '--', *{command!r}]; "
            "module.main()"
        )
        invocation = [sys.executable, "-c", bootstrap]
        if guarded:
            invocation = [sys.executable, str(SDK / "run_guarded.py"), "--path", str(self.root),
                          "--reserve-gib", "0", *guarded, "--", *invocation]
        result = subprocess.run(invocation, cwd=self.root, capture_output=True, text=True,
                                env={**os.environ, "BUILD_RETRY_SENTINEL": "unchanged"}, timeout=15)
        calls = self.root / "calls.json"
        receipts = sorted((self.root / ".sdk-evidence").glob("native-build-*.json"))
        return result, json.loads(calls.read_text()) if calls.exists() else [], [
            json.loads(path.read_text()) for path in receipts]

    def test_transient_denial_reuses_exact_command_directory_and_environment(self):
        result, calls, receipts = self.run_build([
            {"output": DENIAL, "code": 5}, {"output": "Build completed", "code": 0}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(calls[0]["sentinel"], "unchanged")
        self.assertEqual([item["exit_code"] for item in receipts], [5, 0])
        self.assertIn("Access is denied.", result.stdout)
        self.assertIn("Retrying", result.stdout)
        self.assertEqual(receipts[0]["failed_targets"],
                         ["bin/vtkIONetCDF-9.7.dll lib/vtkIONetCDF-9.7.lib"])

    def test_persistent_denial_preserves_final_error_after_only_one_retry(self):
        result, calls, receipts = self.run_build([
            {"output": DENIAL, "code": 5}, {"output": DENIAL, "code": 19}])
        self.assertEqual(result.returncode, 19)
        self.assertEqual(len(calls), 2)
        self.assertEqual([item["exit_code"] for item in receipts], [5, 19])

    def test_executable_link_denial_is_also_recoverable(self):
        output = DENIAL.replace(".dll", ".exe").replace("vs_link_dll", "vs_link_exe")
        result, calls, _ = self.run_build([
            {"output": output, "code": 5}, {"output": "Build completed", "code": 0}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)

    def test_compile_errors_fail_without_retry(self):
        result, calls, receipts = self.run_build([{"output": COMPILE_ERROR, "code": 27}])
        self.assertEqual(result.returncode, 27)
        self.assertEqual(len(calls), 1)
        self.assertFalse(receipts[0]["retry_eligible"])

    def test_linker_errors_fail_without_retry(self):
        output = DENIAL.replace("Access is denied.", "LINK : fatal error LNK1104: cannot open file")
        result, calls, _ = self.run_build([{"output": output, "code": 4}])
        self.assertEqual(result.returncode, 4)
        self.assertEqual(len(calls), 1)

    def test_mixed_failure_does_not_hide_compile_error(self):
        result, calls, _ = self.run_build([{"output": DENIAL + COMPILE_ERROR, "code": 31}])
        self.assertEqual(result.returncode, 31)
        self.assertEqual(len(calls), 1)

    def test_unrelated_failed_link_command_is_not_retried(self):
        result, calls, _ = self.run_build([{
            "output": DENIAL + DENIAL.replace("Access is denied.", "Other command failed."),
            "code": 7}])
        self.assertEqual(result.returncode, 7)
        self.assertEqual(len(calls), 1)

    def test_non_windows_denial_is_not_retried(self):
        result, calls, _ = self.run_build([{"output": DENIAL, "code": 5}], platform="darwin")
        self.assertEqual(result.returncode, 5)
        self.assertEqual(len(calls), 1)

    def test_bare_denial_without_failed_link_is_not_retried(self):
        result, calls, _ = self.run_build([{"output": "Access is denied.", "code": 5}])
        self.assertEqual(result.returncode, 5)
        self.assertEqual(len(calls), 1)

    def test_successful_build_is_not_repeated(self):
        result, calls, receipts = self.run_build([{"output": "Build completed", "code": 0}])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(receipts[0]["exit_code"], 0)

    def test_launch_error_is_recorded_without_inventing_a_child_exit_code(self):
        result, calls, receipts = self.run_build([], command=[str(self.root / "missing.exe")])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(calls, [])
        self.assertIsNone(receipts[0]["exit_code"])
        self.assertTrue(receipts[0]["launch_error"])
        self.assertFalse(receipts[0]["will_retry"])

    def test_guard_timeout_still_terminates_owned_build_without_retry(self):
        result, calls, _ = self.run_build([{"output": DENIAL, "code": 5, "sleep": 5}],
                                         guarded=["--timeout", "0.1"])
        self.assertNotEqual(result.returncode, 0)
        self.assertLessEqual(len(calls), 1)
        self.assertIn("SDK command exceeded its time limit", result.stderr)
        receipts = list((self.root / ".sdk-evidence").glob("command-*.json"))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(json.loads(receipts[0].read_text())["stop_reason"],
                         "SDK command exceeded its time limit")

    def test_guard_storage_preflight_still_blocks_build(self):
        result, calls, _ = self.run_build([{"output": DENIAL, "code": 5}],
                                         guarded=["--peak-gib", "1000000000000"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        self.assertIn("SDK storage preflight failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
