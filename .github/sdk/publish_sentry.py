#!/usr/bin/env python3
"""Create the VTK Sentry release and upload matching PDB/dSYM files."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from install_sentry_cli import VERSION as CLI_VERSION
from package_sdk import digest, require
from sentry_symbols import verify

ORGANIZATION = "amplifier-ai"
PROJECT = "unity-plugin"
REPOSITORY = "amplifier-ai/vtk"
API_ORIGIN = "https://sentry.io/api/0/"

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None  # Authorization must never follow a provider redirect.


def next_page(header):
    for part in header.split(","):
        if 'rel="next"' in part and 'results="true"' in part:
            match = re.search(r"<([^>]+)>", part)
            require(match is not None, "Invalid Sentry pagination link")
            parsed = urlparse(match[1])
            require(parsed.scheme == "https" and parsed.netloc == "sentry.io"
                    and parsed.path.startswith("/api/0/") and not parsed.fragment,
                    "Sentry pagination left the API origin")
            return parsed.path[len("/api/0/"):] + ("?" + parsed.query if parsed.query else "")
    return None


def api_request(method, path, token, body=None, allow_missing=False):
    require(not path.startswith(("/", "http:" , "https:")) and ".." not in path.split("/"),
            "Invalid Sentry API path")
    encoded = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(API_ORIGIN + path, data=encoded, method=method,
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            return json.load(response), next_page(response.headers.get("Link", ""))
    except HTTPError as error:
        if error.code == 404 and allow_missing:
            return None, None
        raise RuntimeError(f"Sentry API {method} failed (HTTP {error.code})") from None
    except (URLError, OSError, ValueError):
        raise RuntimeError("Sentry API request failed") from None


def api_list(path, token):
    rows, seen = [], set()
    while path:
        require(path not in seen and len(seen) < 100, "Invalid or excessive Sentry pagination")
        seen.add(path)
        data, path = api_request("GET", path, token)
        require(isinstance(data, list), "Invalid Sentry collection response")
        rows.extend(data)
    return rows


def run_cli(cli, arguments, token):
    environment = {**os.environ, "SENTRY_AUTH_TOKEN": token,
                   "SENTRY_URL": "https://sentry.io", "SENTRY_DISABLE_UPDATE_CHECK": "1"}
    environment.pop("SENTRY_LOG_FILE", None)
    result = subprocess.run([str(cli), "--url", "https://sentry.io", *map(str, arguments)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment)
    diagnostic = (result.stderr or result.stdout).replace(token, "[REDACTED]") if token else result.stderr
    require(result.returncode == 0, f"Sentry CLI failed (exit {result.returncode}): {diagnostic[-1500:]}")
    return result.stdout


def validate_archives(manifests, packages, runtime_packages):
    run_id = os.environ.get("GITHUB_RUN_ID")
    require(run_id, "GITHUB_RUN_ID is required to bind the builder artifacts")
    for manifest in manifests:
        require(str(manifest.get("run_id")) == run_id, "Symbol manifest belongs to another workflow run")
        platform = manifest["platform"]
        extension = "zip" if platform == "win-x64" else "tar.gz"
        expected = {f"vtk-sdk-{platform}.{extension}", f"vtk-csharp-{platform}.{extension}"}
        require(set(manifest.get("archives", {})) == expected, "Missing or unexpected package archive binding")
        for name, checksum in manifest["archives"].items():
            directory = Path(runtime_packages if name.startswith("vtk-csharp-") else packages).resolve()
            path = directory / name
            require(path.is_file() and not path.is_symlink(), f"Package archive is missing: {name}")
            require(re.fullmatch(r"[a-f0-9]{64}", checksum) and digest(path) == checksum,
                    f"Package archive bytes differ from the symbol build: {name}")


def upload_inputs(roots, manifests):
    files = {}
    for root, manifest in zip(roots, manifests):
        root = Path(root).resolve()
        for module in manifest["modules"]:
            artifact = module["debug"]
            relative = PurePosixPath(artifact["path"])
            require(not relative.is_absolute() and ".." not in relative.parts,
                    "Symbol artifact leaves the verified staging root")
            path = root / str(relative)
            require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root),
                    "Symbol artifact is not a regular staged file")
            require(digest(path) == artifact["sha256"], "Symbol artifact bytes changed")
            expected_type = "pdb" if manifest["platform"] == "win-x64" else "macho"
            require(artifact["type"] == ("pdb" if expected_type == "pdb" else "dsym"),
                    "Unexpected staged symbol format")
            features = set(artifact["features"])
            require("debug" in features, "Missing native debug information")
            with path.open("rb") as stream:
                sha1 = hashlib.file_digest(stream, "sha1").hexdigest()
            expected = {"debug_id": module["debug_id"].lower(), "arch": module["arch"],
                        "type": expected_type, "features": sorted(features),
                        "sha1": sha1, "size": path.stat().st_size, "role": "debug"}
            if path in files:
                require(files[path] == expected, "Conflicting staged symbol declarations")
            files[path] = expected
    require(files, "Expected matching PDB/dSYM artifacts")
    return files


def repository_name(row):
    repository = row.get("repository")
    return repository.get("name") if isinstance(repository, dict) else repository


def release_plan(existing, commits, release, revision):
    body = {"projects": [PROJECT], "ref": revision,
            "url": f"https://github.com/{REPOSITORY}/commit/{revision}",
            "refs": [{"repository": REPOSITORY, "commit": revision}],
            "commits": [{"repository": REPOSITORY, "id": revision}]}
    if existing is None:
        return "POST", {"version": release, **body}
    require(existing.get("version") == release and existing.get("ref") in (None, revision),
            "The Sentry release identifies another source revision")
    require(all(repository_name(row) == REPOSITORY and row.get("id") == revision for row in commits),
            "The Sentry release is associated with other source commits")
    require(all(repository_name(row) != REPOSITORY or row.get("commit") == revision
                for row in existing.get("refs", [])), "The Sentry release has a conflicting repository ref")
    projects = {row.get("slug") for row in existing.get("projects", [])}
    require(projects <= {PROJECT}, "The Sentry release belongs to another project")
    if not commits or existing.get("ref") != revision or PROJECT not in projects:
        return "PUT", body
    return None, None


def verify_release(token, path, release, revision, finalized=False):
    final, _ = api_request("GET", path, token)
    require(final.get("version") == release and final.get("ref") == revision
            and PROJECT in {row.get("slug") for row in final.get("projects", [])},
            "Sentry did not confirm the VTK release identity")
    require(not finalized or final.get("dateReleased"), "Sentry did not confirm release finalization")
    commits = api_list(path + "commits/?per_page=100", token)
    require(commits and all(repository_name(row) == REPOSITORY and row.get("id") == revision for row in commits),
            "Sentry did not confirm the exact VTK commit")


def verify_uploads(token, files):
    confirmed = []
    for debug_id in sorted({item["debug_id"] for item in files.values()}):
        path = f"projects/{ORGANIZATION}/{PROJECT}/files/dsyms/?" + urlencode({"debug_id": debug_id, "per_page": 100})
        rows = api_list(path, token)
        for expected in [item for item in files.values() if item["debug_id"] == debug_id]:
            matches = [row for row in rows if str(row.get("debugId", "")).lower() == debug_id
                       and row.get("cpuName") == expected["arch"]
                       and row.get("symbolType") == expected["type"]
                       and row.get("sha1") == expected["sha1"] and row.get("size") == expected["size"]
                       and set(expected["features"]) <= set((row.get("data") or {}).get("features", []))]
            require(matches, f"Sentry did not confirm processed {expected['role']} bytes for {debug_id}")
            confirmed.append({**expected, "id": str(matches[0]["id"])})
    return confirmed


def write_receipt(path, receipt):
    path = Path(path)
    require(not path.is_symlink(), "Publication receipt must not be a symbolic link")
    if path.exists():
        previous = json.loads(path.read_text())
        require(all(previous.get(key) == receipt[key] for key in
                    ("repository", "organization", "project", "release", "source_revision")),
                "Existing publication receipt belongs to another release")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        try:
            json.dump(receipt, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.close()
            os.replace(temporary.name, path)
        finally:
            Path(temporary.name).unlink(missing_ok=True)


def publish(roots, revision, release, receipt, cli, packages, runtime_packages):
    token = os.environ.get("SENTRY_AUTH_TOKEN", "").strip()
    require(token, "SENTRY_AUTH_TOKEN is required for publication")
    revision = revision.lower()
    require(re.fullmatch(r"[a-f0-9]{40}", revision), "Expected the full VTK source SHA")
    require(release and len(release) <= 200 and not any(c.isspace() for c in release), "Invalid SDK release identity")
    roots = [Path(root).resolve() for root in roots]
    require(len(roots) == len(set(roots)) == 2, "Expected exactly two distinct symbol roots")
    require(not any(Path(receipt).resolve().is_relative_to(root) for root in roots),
            "Publication receipt must stay outside frozen staging roots")
    require(run_cli(cli, ["--version"], token).strip() == f"sentry-cli {CLI_VERSION}", "Unexpected Sentry CLI version")
    manifests = [verify(root, revision, cli) for root in roots]
    require({item["platform"] for item in manifests} == {"win-x64", "osx-arm64"}, "Expected both SDK platforms")
    require(len({(item["vtk_version"], item["source_tree"]) for item in manifests}) == 1,
            "Platform manifests identify different VTK sources")
    validate_archives(manifests, packages, runtime_packages)
    files = upload_inputs(roots, manifests)
    collection = f"organizations/{ORGANIZATION}/releases/"
    release_path = collection + quote(release, safe="") + "/"
    existing, _ = api_request("GET", release_path, token, allow_missing=True)
    commits = api_list(release_path + "commits/?per_page=100", token) if existing else []
    method, body = release_plan(existing, commits, release, revision)
    if method:
        api_request(method, collection if method == "POST" else release_path, token, body)
    verify_release(token, release_path, release, revision)
    arguments = ["debug-files", "upload", "--org", ORGANIZATION, "--project", PROJECT, "--wait", "--require-all"]
    for debug_id in sorted({item["debug_id"] for item in files.values()}):
        arguments.extend(["--id", debug_id])
    run_cli(cli, [*arguments, *sorted(map(str, files))], token)
    confirmed = verify_uploads(token, files)
    run_cli(cli, ["releases", "finalize", "--org", ORGANIZATION, "--project", PROJECT, release], token)
    verify_release(token, release_path, release, revision, finalized=True)
    result = {"schema_version": 1, "repository": REPOSITORY, "organization": ORGANIZATION,
              "project": PROJECT, "release": release, "source_revision": revision,
              "run_id": os.environ["GITHUB_RUN_ID"], "outcome": "passed", "files": confirmed,
              "builders": [{"platform": item["platform"], "run_attempt": item.get("run_attempt"),
                            "manifest_sha256": digest(root / "sentry-manifest.json"), "archives": item["archives"]}
                           for root, item in zip(roots, manifests)]}
    write_receipt(receipt, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", nargs=2, type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--sentry-cli", required=True)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--runtime-packages", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = publish(args.roots, args.source_sha, args.release, args.receipt, args.sentry_cli,
                         args.packages, args.runtime_packages)
        print(json.dumps({key: result[key] for key in ("release", "source_revision", "outcome")}))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        token = os.environ.get("SENTRY_AUTH_TOKEN", "")
        diagnostic = str(error).replace(token, "[REDACTED]") if token else str(error)
        if not args.receipt.exists() and re.fullmatch(r"[a-f0-9]{40}", args.source_sha):
            write_receipt(args.receipt, {"repository": REPOSITORY, "organization": ORGANIZATION,
                          "project": PROJECT, "release": args.release, "source_revision": args.source_sha,
                          "outcome": "failed", "error": diagnostic[-1500:]})
        parser.exit(1, f"error: {diagnostic}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
