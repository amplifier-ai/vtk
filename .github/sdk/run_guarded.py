#!/usr/bin/env python3
"""Bound disk usage and elapsed time for an owned SDK command."""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time

GIB = 1024 ** 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--reserve-gib", type=float, required=True)
    parser.add_argument("--peak-gib", type=float, default=0)
    parser.add_argument("--timeout", type=float, default=14400)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not all(math.isfinite(x) and x >= 0 for x in (args.reserve_gib, args.peak_gib, args.timeout)):
        raise ValueError("Storage/time bounds must be finite and nonnegative")
    root = args.path.resolve()
    free = shutil.disk_usage(root).free
    required = math.ceil((args.reserve_gib + args.peak_gib) * GIB)
    if free < required:
        raise RuntimeError(f"SDK storage preflight failed: {free} bytes free; {required} required")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        print(json.dumps({"free_bytes": free, "required_bytes": required, "outcome": "ready"}))
        return
    evidence = root / ".sdk-evidence"
    evidence.mkdir(exist_ok=True)
    started = time.monotonic()
    child = subprocess.Popen(command, start_new_session=os.name != "nt")
    minimum = free
    stopped = None
    try:
        while child.poll() is None:
            minimum = min(minimum, shutil.disk_usage(root).free)
            if minimum < args.reserve_gib * GIB:
                raise RuntimeError("SDK command crossed the storage reserve")
            if time.monotonic() - started > args.timeout:
                raise RuntimeError("SDK command exceeded its time limit")
            time.sleep(0.5)
    except BaseException as error:
        stopped = str(error)
        if child.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], check=False)
            else:
                os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    os.killpg(child.pid, signal.SIGKILL)
                else:
                    child.kill()
                child.wait(timeout=10)
        raise
    finally:
        receipt = {"command": command, "exit_code": child.returncode, "stop_reason": stopped,
                   "elapsed_seconds": time.monotonic() - started, "minimum_free_bytes": minimum,
                   "reserve_gib": args.reserve_gib}
        (evidence / f"command-{time.time_ns()}.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if child.returncode != 0:
        raise SystemExit(child.returncode)


if __name__ == "__main__":
    main()
