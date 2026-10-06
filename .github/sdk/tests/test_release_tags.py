import os
from pathlib import Path
import subprocess
import tempfile
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / "workflows/csharp-bindings.yml"


class CSharpReleaseIdentity(unittest.TestCase):
    def tag(self, run_id, attempt):
        release = WORKFLOW.read_text().split("  release:\n", 1)[1]
        command = release.split("      - name: Generate tag\n", 1)[1]
        command = command.split("        run: ", 1)[1].split("\n", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            date = root / "date"
            date.write_text("#!/bin/sh\nprintf '%s\\n' '2026.10.05.1200'\n")
            date.chmod(0o755)
            output = root / "output"
            result = subprocess.run(
                ["bash", "-e", "-o", "pipefail", "-c", command],
                env={**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"],
                     "GITHUB_OUTPUT": str(output), "GITHUB_RUN_ID": str(run_id),
                     "GITHUB_RUN_ATTEMPT": str(attempt)},
                cwd=root, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return output.read_text().strip().removeprefix("tag=")

    def test_same_minute_runs_have_distinct_tags(self):
        self.assertNotEqual(self.tag(123, 1), self.tag(124, 1))

    def test_same_run_publication_retries_have_distinct_tags(self):
        self.assertNotEqual(self.tag(123, 1), self.tag(123, 2))


if __name__ == "__main__":
    unittest.main()
