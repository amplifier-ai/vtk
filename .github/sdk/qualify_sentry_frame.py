#!/usr/bin/env python3
"""Qualify two observed SDK addresses through synthetic native Sentry INFO events."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener
import uuid
import zipfile

from package_sdk import digest, require
from publish_sentry import (NoRedirect, ORGANIZATION, PROJECT,
                           PROJECT_ID, REPOSITORY, api_list, api_request, write_receipt)
from sentry_symbols import read_bundle

ENVIRONMENT = "ci-symbol-qualification"
FUNCTION = "vtkVersion::GetVTKVersionFull"
SOURCE_FILE = "Common/Core/vtkVersion.cxx"
ORGANIZATION_ID = "4508885211873280"


def bind_probes(roots, evidence, revision, run_id):
    specifications = []
    for root in roots:
        root = Path(root).resolve()
        manifest = json.loads((root / "sentry-manifest.json").read_text())
        platform = manifest["platform"]
        require(platform in ("win-x64", "osx-arm64") and manifest.get("outcome") == "passed"
                and manifest.get("repository") == REPOSITORY and manifest.get("source_revision") == revision
                and str(manifest.get("run_id")) == run_id, "Invalid frozen native symbol identity")
        result = json.loads((Path(evidence) / platform / "verification.json").read_text())
        extension = "zip" if platform == "win-x64" else "tar.gz"
        require(result.get("outcome") == "passed" and result.get("source_revision") == revision
                and result.get("platform") == platform
                and result.get("archive_sha256") == manifest["archives"][f"vtk-sdk-{platform}.{extension}"],
                "Consumer evidence does not identify the published SDK archive")
        probe = result["native_frame_probe"]
        require(probe.get("schema_version") == 1 and probe.get("synthetic") is True
                and probe.get("probe_function") == FUNCTION, "Expected the observed synthetic VTK function probe")
        relative = PurePosixPath(probe["module_relative_path"])
        require(not relative.is_absolute() and ".." not in relative.parts
                and probe["module_path"].replace("\\", "/").rsplit("/", 1)[-1] == relative.name,
                "Probe module name or SDK path is invalid")
        matches = [(module, binary) for module in manifest["modules"] for binary in module["binaries"]
                   if binary.get("product") == "sdk" and binary.get("package_path") == str(relative)
                   and binary.get("sha256") == probe["module_sha256"] and module.get("name") == relative.name]
        require(len(matches) == 1, "Probe module does not match one frozen SDK binary")
        module, binary = matches[0]
        require(digest(root / binary["path"]) == probe["module_sha256"], "Frozen probe binary changed")
        expected_type = "pe" if platform == "win-x64" else "macho"
        expected_arch = "x86_64" if platform == "win-x64" else "arm64"
        require(probe["image_type"] == expected_type and module["arch"] == expected_arch,
                "Probe image format or architecture differs from the SDK")
        for field in ("image_addr", "instruction_addr"):
            require(isinstance(probe[field], str) and re.fullmatch(r"0x[0-9a-fA-F]{1,16}", probe[field]),
                    "Probe contains an invalid observed address")
        base, instruction = int(probe["image_addr"], 16), int(probe["instruction_addr"], 16)
        size = probe["image_size"]
        require(type(size) is int and 0 < size < 2**64 and base > 0
                and base + size <= 2**64 and base <= instruction < base + size,
                "Observed instruction is outside its loaded image")
        coverage = [row for row in module["source_coverage"] if row["kind"] == "tracked" and row["path"] == SOURCE_FILE]
        require(len(coverage) == 1, "VTK version source is absent from the frozen bundle")
        bundle = root / module["sources"]["path"]
        require(digest(bundle) == module["sources"]["sha256"], "Frozen source bundle changed")
        bundled = read_bundle(bundle)
        require(bundled.get("debug_id", "").lower() == module["debug_id"].lower(), "Probe source/debug identities differ")
        source_entries = [name for name, metadata in bundled["files"].items()
                          if metadata.get("path", "").replace("\\", "/") == coverage[0]["original_path"].replace("\\", "/")
                          and metadata.get("url") == f"https://raw.githubusercontent.com/{REPOSITORY}/{revision}/{SOURCE_FILE}"]
        require(len(source_entries) == 1, "Probe source lacks its immutable Git URL")
        with zipfile.ZipFile(bundle) as archive:
            source = archive.read(source_entries[0])
        require(hashlib.sha256(source).hexdigest() == coverage[0]["sha256"], "Probe source bytes changed")
        event_id = uuid.uuid5(uuid.NAMESPACE_URL,
            f"https://sentry.io/{ORGANIZATION}/{PROJECT}/{run_id}/{revision}/{platform}/"
            f"{module['debug_id']}/{probe['module_sha256']}/vtk-sdk-native-frame-v1").hex
        specifications.append({"platform": platform, "event_id": event_id, "module_name": relative.name,
                               "module_sha256": probe["module_sha256"], "debug_id": module["debug_id"],
                               "debug_file": PurePosixPath(module["debug"]["path"]).name,
                               "code_id": binary.get("code_id"), "arch": module["arch"], "probe": probe,
                               "source_lines": source.decode("utf-8-sig").splitlines()})
    require(len(specifications) == 2 and {row["platform"] for row in specifications} == {"win-x64", "osx-arm64"},
            "Expected exactly one consumer probe per SDK platform")
    return specifications


def synthetic_event(specification, revision, release, run_id):
    probe = specification["probe"]
    image = {"type": probe["image_type"], "debug_id": specification["debug_id"],
             "debug_file": specification["debug_file"],
             "code_file": specification["module_name"], "image_addr": probe["image_addr"],
             "image_size": probe["image_size"], "arch": specification["arch"]}
    if specification["code_id"]:
        image["code_id"] = specification["code_id"]
    return {"event_id": specification["event_id"], "platform": "native", "level": "info",
            "environment": ENVIRONMENT, "release": release,
            "timestamp": datetime.now(timezone.utc).isoformat(), "server_name": "vtk-sdk-ci",
            "message": "Synthetic VTK SDK symbol and source-context qualification",
            "tags": {"vtk.sdk.qualification": "native-frame", "vtk.sdk.platform": specification["platform"],
                     "vtk.sdk.source": revision, "vtk.sdk.run": run_id},
            "fingerprint": ["vtk-sdk-native-qualification", revision, specification["platform"]],
            "debug_meta": {"images": [image]},
            "threads": {"values": [{"id": 1, "current": True, "crashed": False,
                        "stacktrace": {"instruction_addr_adjustment": "none", "frames": [
                            {"instruction_addr": probe["instruction_addr"], "in_app": True,
                             "package": specification["module_name"]}]}}]}}


def ingest_target(dsn):
    parsed = urlparse(dsn)
    host = parsed.hostname or ""
    require(parsed.scheme == "https" and parsed.password is None and parsed.port is None
            and re.fullmatch(r"[0-9a-f]{32}", parsed.username or "")
            and re.fullmatch(r"o" + ORGANIZATION_ID + r"\.ingest(?:\.[a-z0-9-]+)?\.sentry\.io", host)
            and parsed.path == "/" + PROJECT_ID and not parsed.query and not parsed.fragment,
            "DSN does not belong to the approved official Sentry ingest project")
    return f"https://{host}/api/{PROJECT_ID}/envelope/", parsed.username


def enabled_dsn(token):
    rows = api_list(f"projects/{ORGANIZATION}/{PROJECT}/keys/?status=active", token)
    active = [row for row in rows if row.get("isActive") is True and str(row.get("projectId")) == PROJECT_ID]
    require(active, "The qualification project has no enabled DSN")
    dsn = sorted(active, key=lambda row: str(row["id"]))[0]["dsn"]["public"]
    ingest_target(dsn)
    return dsn


def send_event(dsn, event):
    endpoint, public_key = ingest_target(dsn)
    payload = json.dumps(event, separators=(",", ":")).encode("utf-8")
    envelope = (json.dumps({"event_id": event["event_id"], "dsn": dsn}).encode() + b"\n"
                + json.dumps({"type": "event", "length": len(payload)}).encode() + b"\n" + payload + b"\n")
    request = Request(endpoint, data=envelope, method="POST", headers={
        "Content-Type": "application/x-sentry-envelope",
        "X-Sentry-Auth": f"Sentry sentry_version=7,sentry_key={public_key},sentry_client=vtk-sdk-qualification/1"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            require(response.status in (200, 202), "Unexpected native qualification ingest response")
    except HTTPError as error:
        raise RuntimeError(f"Native qualification envelope failed (HTTP {error.code}); event will not be resent") from None
    except (URLError, OSError, ValueError):
        raise RuntimeError("Native qualification send is uncertain; event will not be resent") from None


def qualified_frame(event, specification, revision, release):
    tags = {row["key"]: row["value"] for row in event.get("tags", [])}
    version = event.get("release") or {}
    version = version.get("version") if isinstance(version, dict) else version
    require(event.get("eventID") == specification["event_id"] and event.get("platform") == "native"
            and (event.get("environment") or tags.get("environment")) == ENVIRONMENT
            and (event.get("level") or tags.get("level")) == "info" and version == release,
            "Processed event identity differs from the synthetic qualification")
    frames = [frame for entry in event.get("entries", []) if entry.get("type") == "threads"
              for thread in entry["data"].get("values", [])
              for frame in (thread.get("stacktrace") or {}).get("frames", [])]
    for frame in frames:
        line = frame.get("lineNo")
        filename = (frame.get("absPath") or frame.get("filename") or "").replace("\\", "/")
        if ("GetVTKVersionFull" not in (frame.get("function") or "")
                or not (filename == SOURCE_FILE or filename.endswith("/" + SOURCE_FILE))
                or type(line) is not int or not 0 < line <= len(specification["source_lines"])):
            continue
        context = [text for number, text in frame.get("context", []) if number == line]
        link = urlparse(frame.get("sourceLink") or "")
        expected_path = f"/{REPOSITORY}/blob/{revision}/{SOURCE_FILE}"
        if (not context or not context[0].strip()
                or context[0].strip() != specification["source_lines"][line-1].strip()
                or link.scheme != "https" or link.netloc not in ("github.com", "www.github.com")
                or link.path != expected_path or link.fragment != f"L{line}" or link.query):
            continue
        return {"function": frame["function"], "filename": SOURCE_FILE, "line": line,
                "sourceLink": frame["sourceLink"], "context_sha256": hashlib.sha256(context[0].encode()).hexdigest()}
    raise RuntimeError("Native function, source line, context and immutable link are not fully processed")


def poll_events(specifications, receipt, path, token, revision, release, timeout):
    deadline = time.monotonic() + timeout
    remaining = {row["platform"] for row in specifications}
    while remaining and time.monotonic() < deadline:
        for specification in specifications:
            platform = specification["platform"]
            if platform not in remaining or time.monotonic() >= deadline:
                continue
            event, _ = api_request("GET", f"projects/{ORGANIZATION}/{PROJECT}/events/{specification['event_id']}/", token, allow_missing=True)
            if event is None:
                continue
            try:
                frame = qualified_frame(event, specification, revision, release)
            except RuntimeError:
                continue
            receipt["events"][platform].update(state="qualified", frame=frame)
            write_receipt(path, receipt)
            remaining.remove(platform)
        if remaining:
            time.sleep(min(3, max(0, deadline - time.monotonic())))
    require(not remaining, "Synthetic native frame qualification remains pending; preserved event IDs will not be resent")
    receipt["outcome"] = "passed"
    write_receipt(path, receipt)
    return receipt


def qualify(roots, evidence, revision, release, path, timeout=120):
    token, run_id = os.environ.get("SENTRY_AUTH_TOKEN", "").strip(), os.environ.get("GITHUB_RUN_ID")
    require(token and run_id, "SENTRY_AUTH_TOKEN and GITHUB_RUN_ID are required")
    require(re.fullmatch(r"[a-f0-9]{40}", revision) and release and 60 <= timeout <= 120,
            "Expected full source SHA, release identity and bounded 60-120 second polling")
    specifications = bind_probes(roots, evidence, revision, run_id)
    owner = {"schema_version": 1, "repository": REPOSITORY, "organization": ORGANIZATION,
             "project": PROJECT, "source_revision": revision, "release": release, "run_id": run_id,
             "qualification": "synthetic-native-sdk-frame", "environment": ENVIRONMENT}
    if Path(path).exists():
        receipt = json.loads(Path(path).read_text())
        require(all(receipt.get(key) == value for key, value in owner.items()), "Existing qualification receipt belongs to another run or source")
        require(set(receipt.get("events", {})) == {row["platform"] for row in specifications}, "Existing qualification receipt lacks its two event identities")
        for specification in specifications:
            previous = receipt["events"][specification["platform"]]
            require(all(previous.get(key) == specification[key] for key in ("event_id", "module_name", "module_sha256", "debug_id"))
                    and previous.get("state") in ("not_attempted", "pending", "qualified"), "Existing qualification binding differs from the SDK probe")
    else:
        receipt = {**owner, "outcome": "pending", "events": {row["platform"]: {
            **{key: row[key] for key in ("event_id", "module_name", "module_sha256", "debug_id")},
            "state": "not_attempted"} for row in specifications}}
        write_receipt(path, receipt)
    receipt["outcome"] = "pending"
    write_receipt(path, receipt)
    dsn = None
    for specification in specifications:
        state = receipt["events"][specification["platform"]]
        if state["state"] != "not_attempted":
            continue
        existing, _ = api_request("GET", f"projects/{ORGANIZATION}/{PROJECT}/events/{specification['event_id']}/", token, allow_missing=True)
        if existing is None and dsn is None:
            dsn = enabled_dsn(token)
        state["state"] = "pending"
        write_receipt(path, receipt)  # Persist before any uncertain ingest call.
        if existing is None:
            send_event(dsn, synthetic_event(specification, revision, release, run_id))
    return poll_events(specifications, receipt, path, token, revision, release, timeout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--roots", nargs=2, type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    try:
        result = qualify(args.roots, args.evidence, args.source_sha, args.release, args.receipt, args.timeout)
        print(json.dumps({"source_revision": result["source_revision"], "qualification": result["qualification"], "outcome": result["outcome"]}))
    except (OSError, ValueError, RuntimeError) as error:
        token = os.environ.get("SENTRY_AUTH_TOKEN", "")
        diagnostic = str(error).replace(token, "[REDACTED]") if token else str(error)
        parser.exit(1, f"error: {diagnostic}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
