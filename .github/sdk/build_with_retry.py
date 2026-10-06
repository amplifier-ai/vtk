#!/usr/bin/env python3
"""Recover one Windows link-command access denial without changing build inputs."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time


class Failures:
    def __init__(self):
        self.blocks = []
        self.current = None
        self.fatal = False

    def feed(self, line):
        text = line.strip()
        if text.startswith("FAILED: "):
            self.current = {"target": text[8:], "command": None, "denied": False,
                            "other_output": False}
            self.blocks.append(self.current)
        elif re.match(r"^\[\d+/\d+\]", text):
            self.current = None
        elif self.current and text:
            if self.current["command"] is None:
                self.current["command"] = text
            elif text == "Access is denied.":
                self.current["denied"] = True
            elif not text.startswith("ninja: build stopped:"):
                self.current["other_output"] = True
        if re.search(r"(?:fatal error|\berror\s+(?:C\d+|LNK\d+)|out of memory|disk full)",
                     text, re.I):
            self.fatal = True

    def retry_eligible(self):
        return bool(self.blocks) and not self.fatal and all(
            re.search(r"\.(?:dll|exe)\b", block["target"], re.I)
            and re.search(r"\s-E\s+vs_link_(?:dll|exe)\b", block["command"] or "")
            and block["denied"] and not block["other_output"]
            for block in self.blocks)


def run_build(command, evidence):
    evidence.mkdir(parents=True, exist_ok=True)
    windows = sys.platform == "win32"
    for attempt in (1, 2):
        failures = Failures()
        started = time.monotonic()
        launch_error = None
        try:
            child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace")
        except OSError as error:
            launch_error = str(error)
            exit_code = None
            print(f"Native build could not launch: {error}", file=sys.stderr, flush=True)
        else:
            with child, child.stdout:
                for line in child.stdout:
                    sys.stdout.write(line)
                    failures.feed(line)
                sys.stdout.flush()
                exit_code = child.wait()
        eligible = windows and exit_code not in (None, 0) and failures.retry_eligible()
        retry = eligible and attempt == 1
        receipt = {"command": command, "cwd": str(Path.cwd()), "platform": sys.platform,
                   "attempt": attempt, "exit_code": exit_code, "launch_error": launch_error,
                   "elapsed_seconds": time.monotonic() - started,
                   "failed_targets": [block["target"] for block in failures.blocks],
                   "failed_commands": failures.blocks, "retry_eligible": bool(eligible),
                   "will_retry": bool(retry)}
        path = evidence / f"native-build-{time.time_ns()}-{attempt}.json"
        path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        if not retry:
            return exit_code if exit_code is not None else 1
        print("Retrying the identical native build once after a Windows link-command "
              "access denial; the first failed attempt is retained in SDK evidence.", flush=True)
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("A native build command is required")
    raise SystemExit(run_build(command, args.evidence))


if __name__ == "__main__":
    main()
