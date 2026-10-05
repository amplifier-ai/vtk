#!/usr/bin/env python3
"""Compile and run a native consumer after relocating an SDK archive."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from package_sdk import digest, extract_sdk, require, validate_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "consumer", "work", "original-sdk"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    archive, consumer, work, original = [p.resolve() for p in
                                       (args.archive, args.consumer, args.work, args.original_sdk)]
    require(not work.exists(), "Relocation verification work directory must be new")
    require(original.is_dir(), "Original SDK directory is required")
    require(not original.is_relative_to(work) and not work.is_relative_to(original),
            "Original and relocated SDK directories must be separate")
    require(not archive.is_relative_to(original) and not consumer.is_relative_to(original),
            "Do not remove the archive or consumer with the original SDK")
    checksum = Path(str(archive) + ".sha256").read_text().split()[0]
    require(digest(archive) == checksum, "Archive digest differs from checksum")
    sdk = work / "sdk"
    extract_sdk(archive, sdk)
    manifest = validate_manifest(sdk)
    require(manifest["platform"] == ("win-x64" if sys.platform == "win32" else "osx-arm64"),
            "SDK platform differs from verification host")
    require(validate_manifest(original) == manifest, "Original SDK does not match the packaged SDK")
    # Removal makes accidental use of the former install prefix fail the smoke test.
    shutil.rmtree(original)
    env = os.environ.copy()
    env["PATH"] = str(sdk / "bin") + os.pathsep + env.get("PATH", "")
    if sys.platform == "darwin":
        env["DYLD_LIBRARY_PATH"] = str(sdk / "lib")
    build = work / "consumer-build"
    commands = [
        ["cmake", "-S", str(consumer), "-B", str(build), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
         f"-DVTK_DIR={sdk / 'lib/cmake/vtk-9.7'}", "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF",
         "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF"],
        ["cmake", "--build", str(build), "--parallel", "2"],
        ["ctest", "--test-dir", str(build), "--output-on-failure", "-V"],
    ]
    if sys.platform == "darwin":
        commands[0].extend(["-DCMAKE_OSX_ARCHITECTURES=arm64", "-DCMAKE_OSX_DEPLOYMENT_TARGET=14.0"])
    receipts = []
    result = {"archive_sha256": checksum, "source_revision": manifest["source_revision"],
              "platform": manifest["platform"], "original_sdk_removed": True,
              "relocated_sdk": str(sdk), "commands": receipts, "outcome": "running"}
    try:
        for command in commands:
            child = subprocess.run(command, env=env, timeout=180)
            receipts.append({"command": command, "exit_code": child.returncode})
            require(child.returncode == 0, f"SDK consumer failed: {command[0]}")
        result["outcome"] = "passed"
    except BaseException:
        result["outcome"] = "failed"
        raise
    finally:
        (work / "verification.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
