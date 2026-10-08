"""Install a hash- and version-verified Sentry CLI into a task-owned directory."""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import urllib.request


VERSION = "3.8.0"
# GitHub release asset digests: https://api.github.com/repos/getsentry/sentry-cli/releases/tags/3.8.0
ASSETS = {
    "win-x64": (
        "sentry-cli-Windows-x86_64.exe",
        "2257cf6805a616f5c3ee291a549ebbba021190048b646adc006beb4e8cdef7fd",
    ),
    "osx-arm64": (
        "sentry-cli-Darwin-arm64",
        "1dda212b0e168b9c4dc48d7d3aa24c1c37de9c6edf786e6ae661236e529969cd",
    ),
    "linux-x64": (
        "sentry-cli-Linux-x86_64",
        "13f8cb34ae01a6a272d7d7c22e277a105286615b4020de900ea95a8de47cdbb6",
    ),
}


def _download(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as response:
        with destination.open("xb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)


def _verify(path: Path, expected_sha256: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as binary:
        for chunk in iter(lambda: binary.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"SHA256 mismatch for {path.name}: expected {expected_sha256}, got {actual_sha256}"
        )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    result = subprocess.run(
        [str(path), "--version"],
        check=True, capture_output=True, text=True, timeout=30,
    )
    expected_version = f"sentry-cli {VERSION}"
    if result.stdout.strip() != expected_version:
        raise RuntimeError(f"Expected {expected_version}, got {result.stdout.strip()!r}")


def install(output_directory: Path, platform: str, *, loader=None) -> Path:
    """Return the verified executable; preserve unexpected existing contents."""
    if platform not in ASSETS:
        raise ValueError(f"Unsupported platform: {platform}")
    filename, checksum = ASSETS[platform]
    directory = Path(output_directory).resolve()
    executable = directory / filename
    if executable.is_symlink() or (executable.exists() and not executable.is_file()):
        raise RuntimeError(f"Expected a regular file at {executable}")
    if executable.exists():
        _verify(executable, checksum)
        return executable

    directory.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/getsentry/sentry-cli/releases/download/{VERSION}/{filename}"
    with tempfile.TemporaryDirectory(prefix=".sentry-cli-", dir=directory) as staging:
        downloaded = Path(staging) / filename
        (loader or _download)(url, downloaded)
        _verify(downloaded, checksum)
        downloaded.replace(executable)
    return executable


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--platform", choices=tuple(ASSETS), required=True)
    args = parser.parse_args(argv)
    try:
        executable = install(args.directory, args.platform)
        output_file = os.environ.get("GITHUB_OUTPUT")
        if output_file:
            with Path(output_file).open("a", encoding="utf-8") as output:
                output.write(f"path={executable}\n")
        else:
            print(executable)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
