#!/usr/bin/env python3
"""Complete only installed native targets in an existing configured C# build."""
import argparse
import json
from pathlib import Path
import subprocess


def prepare(build):
    query = build / ".cmake/api/v1/query/codemodel-v2"
    query.parent.mkdir(parents=True, exist_ok=True)
    query.touch()


def installed_targets(build):
    reply = build / ".cmake/api/v1/reply"
    indexes = sorted(reply.glob("index-*.json"))
    if not indexes:
        raise RuntimeError("CMake File API reply missing; prepare the query before configure")
    index = json.loads(indexes[-1].read_text())
    reference = index["reply"]["codemodel-v2"]
    if "error" in reference:
        raise RuntimeError(f"CMake File API error: {reference['error']}")
    model = json.loads((reply / reference["jsonFile"]).read_text())
    configuration, = [c for c in model["configurations"] if c["name"] in ("Release", "")]
    selected = []
    for reference in configuration["targets"]:
        target = json.loads((reply / reference["jsonFile"]).read_text())
        if target["type"] in ("SHARED_LIBRARY", "STATIC_LIBRARY", "MODULE_LIBRARY", "EXECUTABLE"):
            if target.get("install", {}).get("destinations"):
                selected.append(target["name"])
    if not selected:
        raise RuntimeError("CMake File API lists no installed native SDK targets")
    return sorted(set(selected))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    build = args.build.resolve()
    if args.prepare:
        prepare(build)
        return
    targets = installed_targets(build)
    print(f"Complete {len(targets)} installed targets in the existing build directory", flush=True)
    subprocess.run(["cmake", "--build", str(build), "--config", "Release", "--parallel", "4",
                    "--target", *targets], check=True)


if __name__ == "__main__":
    main()
