import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / "workflows/native-sdk.yml"


class NativeSDKPublication(unittest.TestCase):
    def publish(self, event, ref="refs/heads/master", existing_tag=False):
        source = WORKFLOW.read_text()
        step = re.search(
            r"(?m)^      - name: Create unique (?:pre)?release with source revision\n",
            source,
        )
        self.assertIsNotNone(step, "The SDK publisher step is missing")
        body = source[step.end():].split("        run: |\n", 1)[1]
        script = textwrap.dedent(body.split("\n      - name:", 1)[0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "packages").mkdir()
            (root / "packages/vtk-sdk-win-x64.zip").write_bytes(b"verified fixture")
            executable = root / "gh"
            executable.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "if sys.argv[1] == 'api':\n"
                "    print(os.environ['EXISTING_TAG'])\n"
                "elif sys.argv[1:3] == ['release', 'create']:\n"
                "    Path('release-arguments.json').write_text(json.dumps(sys.argv[1:]))\n"
                "else:\n"
                "    sys.exit(2)\n"
            )
            executable.chmod(0o755)
            (root / "python").symlink_to(sys.executable)
            environment = {
                **os.environ,
                "PATH": str(root) + os.pathsep + os.environ["PATH"],
                "GITHUB_REPOSITORY": "amplifier-ai/vtk",
                "GITHUB_EVENT_NAME": event,
                "GITHUB_REF": ref,
                "GITHUB_RUN_ID": "123",
                "GITHUB_RUN_ATTEMPT": "1",
                "SDK_SOURCE_SHA": "a" * 40,
                "SDK_PR_URL": "https://github.com/amplifier-ai/vtk/pull/3" if event == "pull_request" else "",
                "EXISTING_TAG": "1" if existing_tag else "0",
            }
            result = subprocess.run(
                ["bash", "-e", "-o", "pipefail", "-c", script],
                cwd=root, env=environment, capture_output=True, text=True,
            )
            arguments = root / "release-arguments.json"
            notes = root / "release-notes.md"
            return (
                result,
                json.loads(arguments.read_text()) if arguments.exists() else None,
                notes.read_text() if notes.exists() else "",
            )

    def test_master_push_publishes_stable_sdk_for_exact_source(self):
        result, arguments, notes = self.publish("push")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("--prerelease", arguments)
        self.assertIn("--latest=false", arguments)
        self.assertEqual(arguments[arguments.index("--target") + 1], "a" * 40)
        self.assertNotIn("Pull request:", notes)

    def test_pull_request_keeps_sdk_prerelease(self):
        result, arguments, notes = self.publish("pull_request", "refs/pull/3/merge")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--prerelease", arguments)
        self.assertIn("https://github.com/amplifier-ai/vtk/pull/3", notes)

    def test_other_push_branch_cannot_publish_stable_sdk(self):
        result, arguments, _ = self.publish("push", "refs/heads/feature")
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(arguments)

    def test_existing_sdk_tag_is_not_replaced(self):
        result, arguments, _ = self.publish("push", existing_tag=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(arguments)


if __name__ == "__main__":
    unittest.main()
