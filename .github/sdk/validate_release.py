#!/usr/bin/env python3
"""Validate SDK archive identities and successful consumer receipts before publication."""
import argparse
import hashlib
import json
from pathlib import Path
import re


ARCHIVES = {"win-x64": "vtk-sdk-win-x64.zip", "osx-arm64": "vtk-sdk-osx-arm64.tar.gz"}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def regular_file(path):
    require(path.is_file() and not path.is_symlink(), f"Required regular file is missing: {path}")
    return path


def archive_digest(path):
    checksum = hashlib.sha256()
    with regular_file(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def option_value(command, option):
    require(command.count(option) == 1, f"verification commands must contain one {option}")
    index = command.index(option)
    require(index + 1 < len(command) and not command[index + 1].startswith("-"),
            f"verification commands have no value for {option}")
    return command[index + 1]


def validate_commands(commands):
    require(isinstance(commands, list) and commands, "verification commands are missing or empty")
    stages = []
    directories = []
    for receipt in commands:
        require(isinstance(receipt, dict), "verification commands contain a malformed receipt")
        exit_code = receipt.get("exit_code")
        require(type(exit_code) is int and exit_code == 0,
                "verification commands require an actual integer exit_code of zero")
        command = receipt.get("command")
        require(isinstance(command, list) and command and
                all(isinstance(value, str) and value for value in command),
                "verification commands contain a malformed command")
        executable = command[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
        require(not any(value == "-N" or value.startswith(("--version", "--help", "--show-only"))
                        for value in command),
                "verification commands must run the consumer, not query or list tests")
        if executable in ("cmake", "cmake.exe") and "--build" in command:
            stage = "build"
            directory = option_value(command, "--build")
        elif executable in ("cmake", "cmake.exe") and "-S" in command and "-B" in command:
            stage = "configure"
            option_value(command, "-S")
            directory = option_value(command, "-B")
        elif executable in ("ctest", "ctest.exe") and "--test-dir" in command:
            stage = "test"
            directory = option_value(command, "--test-dir")
        else:
            raise RuntimeError("verification commands must configure, build and test the consumer")
        stages.append(stage)
        directories.append(directory)
    require(stages == ["configure", "build", "test"],
            "verification commands must configure, build and test the consumer in order")
    require(len(set(directories)) == 1, "verification commands must use the same consumer build directory")


def validate_release(packages, evidence, source_sha):
    require(isinstance(source_sha, str) and re.fullmatch(r"[0-9a-f]{40}", source_sha),
            "Expected source revision must be a full 40-character Git SHA")
    packages, evidence = Path(packages), Path(evidence)
    validated = {}
    for platform, name in ARCHIVES.items():
        checksum_path = regular_file(packages / f"{name}.sha256")
        try:
            checksum_text = checksum_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise RuntimeError(f"Cannot read SDK checksum: {checksum_path}") from error
        checksum = re.fullmatch(r"([0-9a-f]{64}) [ *]" + re.escape(name) + r"\n?", checksum_text)
        require(checksum is not None, f"Malformed SDK checksum or unexpected archive name: {checksum_path}")
        actual_digest = archive_digest(packages / name)
        require(actual_digest == checksum.group(1), f"SDK archive differs from its checksum: {name}")
        report_path = regular_file(evidence / platform / "verification.json")
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as error:
            raise RuntimeError(f"Malformed SDK verification receipt: {report_path}") from error
        require(isinstance(report, dict), f"SDK verification receipt must be an object: {report_path}")
        for field, expected in (("outcome", "passed"), ("platform", platform),
                                ("source_revision", source_sha), ("archive_sha256", actual_digest)):
            require(report.get(field) == expected, f"SDK verification {field} differs from publication: {platform}")
        require(report.get("original_sdk_removed") is True,
                f"SDK verification original_sdk_removed must be true: {platform}")
        validate_commands(report.get("commands"))
        validated[platform] = actual_digest
    return validated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    try:
        result = validate_release(args.packages, args.evidence, args.source_sha)
    except (RuntimeError, OSError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
