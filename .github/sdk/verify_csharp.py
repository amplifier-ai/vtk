#!/usr/bin/env python3
"""Run a .NET consumer against the exact C# archive with the original build hidden."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from package_csharp import macos_version, validate_native_runtime, validate_runtime_manifest
from package_sdk import digest, extract_sdk, require


@contextmanager
def hidden_build(build):
    build = Path(build).resolve()
    hidden = build.with_name(build.name + ".csharp-verification-hidden")
    require(build.is_dir() and not hidden.exists(), "Original build cannot be hidden safely")
    build.rename(hidden)
    try:
        yield
    finally:
        unexpected = None
        if build.exists():
            unexpected = build.with_name(build.name + ".csharp-unexpected-" + uuid.uuid4().hex)
            build.rename(unexpected)
        hidden.rename(build)
        require(unexpected is None,
                f"Consumer recreated the build path; original restored and unexpected content preserved at {unexpected}")


def consumer_environment(environment, original_build, package, work):
    result = environment.copy()
    build = str(original_build.resolve()).replace("\\", "/").rstrip("/").casefold()
    paths = []
    for value in result.get("PATH", "").split(os.pathsep):
        if not value:
            continue
        normalized = str(Path(value.strip('"')).resolve()).replace("\\", "/").rstrip("/").casefold()
        if normalized == build or normalized.startswith(build + "/") or "vcpkg" in normalized.split("/"):
            continue
        paths.append(value)
    if os.name == "nt":
        paths.insert(0, str(package / "native"))
    result["PATH"] = os.pathsep.join(paths)
    for name in ("DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
                 "DYLD_INSERT_LIBRARIES", "LD_LIBRARY_PATH", "LD_PRELOAD"):
        result.pop(name, None)
    result.update({"DOTNET_CLI_HOME": str(work / "dotnet-home"),
                   "NUGET_PACKAGES": str(work / "nuget-packages"),
                   "NUGET_HTTP_CACHE_PATH": str(work / "nuget-http-cache"),
                   "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1", "DOTNET_NOLOGO": "1",
                   "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false",
                   "DOTNET_CLI_TELEMETRY_OPTOUT": "1"})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("package", "consumer", "build", "work"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--platform", choices=("win-x64", "osx-arm64"), required=True)
    parser.add_argument("--minimum-macos", default="26.0")
    args = parser.parse_args()
    archive, consumer, original, work = (path.resolve() for path in
                                         (args.package, args.consumer, args.build, args.work))
    require(sys.platform == ("win32" if args.platform == "win-x64" else "darwin"), "Verification host mismatch")
    require(archive.is_file() and consumer.is_dir(), "C# archive or consumer is missing")
    require(not work.exists(), "C# runtime verification work directory must be new")
    for path in (work, archive, consumer):
        require(not path.is_relative_to(original) and not original.is_relative_to(path),
                "Verification inputs and work must be separate from the original build")
    package = work / "runtime"
    extract_sdk(archive, package)
    manifest = validate_runtime_manifest(package)
    require(manifest["platform"] == args.platform, "C# package platform differs from verifier")
    if args.platform == "osx-arm64":
        require(macos_version(manifest["minimum_macos"]) == macos_version(args.minimum_macos),
                "Packaged C# minimum macOS differs from verification contract")
    expected_source = os.environ.get("SDK_SOURCE_SHA")
    if expected_source:
        require(manifest["source_revision"] == expected_source, "C# package source differs from workflow source")
    project = work / "consumer"
    shutil.copytree(consumer, project)
    environment = consumer_environment(os.environ, original, package, work)
    output = work / "consumer-output"
    commands = [["dotnet", "build", str(project / "CSharpRuntimeConsumer.csproj"),
                 "--configuration", "Release", "--output", str(output)],
                ["dotnet", str(output / "CSharpRuntimeConsumer.dll"),
                 str(package / "managed/VTK.CSharp.dll")]]
    if args.platform == "osx-arm64":
        commands[-1].append("--require-onnx")
    result = {"archive_sha256": digest(archive), "source_revision": manifest["source_revision"],
              "platform": args.platform, "package_tree_sha256": hashlib.sha256(
                  json.dumps(manifest["files"], sort_keys=True).encode()).hexdigest(),
              "minimum_macos": manifest["minimum_macos"],
              "original_build_hidden": False, "original_build_restored": False,
              "loader_environment_overrides_removed": True, "commands": [], "outcome": "running"}
    try:
        with hidden_build(original):
            result["original_build_hidden"] = True
            result["native_validation"] = validate_native_runtime(package, args.platform,
                                                                    minimum_macos=args.minimum_macos)
            for command in commands:
                completed = subprocess.run(command, env=environment, timeout=240,
                                           capture_output=True, text=True, errors="replace")
                result["commands"].append({"command": command, "exit_code": completed.returncode,
                                           "stdout": completed.stdout[-16384:], "stderr": completed.stderr[-16384:]})
                print(completed.stdout, end="")
                print(completed.stderr, end="", file=sys.stderr)
                require(completed.returncode == 0, f"Packaged C# consumer failed: {command[0]}")
        result["outcome"] = "passed"
    except BaseException:
        result["outcome"] = "failed"
        raise
    finally:
        result["original_build_restored"] = original.is_dir() and not original.with_name(
            original.name + ".csharp-verification-hidden").exists()
        (work / "csharp-verification.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
