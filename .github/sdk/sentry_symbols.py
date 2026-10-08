#!/usr/bin/env python3
"""Stage matching PDB/dSYM files from the shipped VTK Release build."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from package_sdk import cache_values, digest, inventory, require, safe_name, validate_manifest
from package_csharp import validate_runtime_manifest

REPOSITORY = "amplifier-ai/vtk"


def cli_run(cli, arguments, environment=None):
    result = subprocess.run([str(cli), *map(str, arguments)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env=environment)
    token = os.environ.get("SENTRY_AUTH_TOKEN", "")
    diagnostic = result.stderr.replace(token, "[REDACTED]") if token else result.stderr
    require(result.returncode == 0, f"Sentry CLI failed (exit {result.returncode}): {diagnostic[-1500:]}")
    return result.stdout


def decode_info(data):
    require(data.get("is_usable") is True and isinstance(data.get("variants"), list), "Unusable debug file")
    variants = sorted(((v.get("debug_id") or "").lower(), v.get("arch", ""), v.get("code_id"))
                      for v in data["variants"])
    require(len(variants) == 1 and all(variants[0][:2]), "Expected one identifiable native architecture")
    return {"debug_id": variants[0][0], "arch": variants[0][1], "code_id": variants[0][2],
            "features": sorted({f.strip() for f in data["features"].split(",")}), "type": data["type"]}


def debug_info(cli, path):
    return decode_info(json.loads(cli_run(cli, ["debug-files", "check", "--json", path])))


def require_pair(binary, debug):
    require((binary["debug_id"], binary["arch"]) == (debug["debug_id"], debug["arch"])
            and "debug" in debug["features"], "Native binary and full debug information differ")


def normalized(path):
    return str(path).replace("\\", "/").rstrip("/")


def build_targets(build):
    reply = build / ".cmake/api/v1/reply"
    index = json.loads(sorted(reply.glob("index-*.json"))[-1].read_text())
    model = json.loads((reply / index["reply"]["codemodel-v2"]["jsonFile"]).read_text())
    configuration, = [c for c in model["configurations"] if c["name"] in ("Release", "")]
    targets = {}
    for item in configuration["targets"]:
        target = json.loads((reply / item["jsonFile"]).read_text())
        if target["type"] not in ("SHARED_LIBRARY", "MODULE_LIBRARY", "EXECUTABLE"):
            continue
        for artifact in target.get("artifacts", []):
            path = (build / artifact["path"]).resolve()
            if path.suffix.lower() in (".dll", ".dylib", ".exe") or path.is_file() and not path.suffix:
                require(path.name not in targets or targets[path.name][0] == path, "Ambiguous producer binary")
                targets[path.name] = (path, target["name"])
    require(targets, "CMake File API contains no native producer binaries")
    return targets


def stage_file(path, root, role):
    require(path.is_file() and not path.is_symlink(), "Artifact must be an individual regular file")
    checksum = digest(path)
    destination = root / role / checksum / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        require(digest(destination) == checksum, "Existing symbol staging artifact changed")
    else:
        shutil.copy2(path, destination)
    return {"path": destination.relative_to(root).as_posix(), "sha256": checksum}


def prepare(sdk, runtime, build, source, output, platform, cli, packages):
    sdk, runtime, build, source, output = [Path(p).resolve() for p in (sdk, runtime, build, source, output)]
    require(not output.exists(), "Symbol staging must be new")
    sdk_manifest = validate_manifest(sdk)
    runtime_manifest = validate_runtime_manifest(runtime)
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "-C", str(source), "diff", "--exit-code", "HEAD", "--"], check=True,
                   stdout=subprocess.DEVNULL)
    require(sdk_manifest["source_revision"] == runtime_manifest["source_revision"] == revision,
            "Package source identities differ from the compiled source")
    require(sdk_manifest["source_tree"] == runtime_manifest["source_tree"], "Package source trees differ")
    require(sdk_manifest["platform"] == runtime_manifest["platform"] == platform, "Package platform mismatch")
    targets = build_targets(build)
    packaged = {}
    for product, directory, manifest in (("sdk", sdk, sdk_manifest), ("runtime", runtime, runtime_manifest)):
        for relative, metadata in manifest["files"].items():
            if "symlink" in metadata:
                continue
            file = (directory / relative).resolve()
            if (file.suffix.lower() not in (".dll", ".dylib", ".exe") and file.name not in targets) or file.name == "VTK.CSharp.dll":
                continue
            packaged.setdefault(file.name, []).append((product, file, relative))
    output.mkdir(parents=True)
    modules, suppliers = [], []
    for name, variants in sorted(packaged.items()):
        if name not in targets:
            require(not name.casefold().startswith(("vtk", "libvtk")), f"Unaccounted VTK producer binary: {name}")
            suppliers.append({"name": name, "policy": "External supplier debug information is not fabricated",
                              "binaries": [{"product": p, "package_path": r, "sha256": digest(f)} for p, f, r in variants]})
            continue
        original, target = targets[name]
        binary = debug_info(cli, original)
        require(binary["arch"] == ("x86_64" if platform == "win-x64" else "arm64"), "Producer architecture mismatch")
        if platform == "win-x64":
            candidates = [build / "native-pdb" / f"{original.stem}.pdb",
                          build / "native-pdb" / f"{target}.pdb", original.with_suffix(".pdb")]
            candidates = list(dict.fromkeys(p for p in candidates if p.is_file()))
            require(candidates, f"Linker PDB missing: {name}")
            matches = [p for p in candidates if debug_info(cli, p)["debug_id"] == binary["debug_id"]]
            require(len(matches) == 1, f"Missing or ambiguous matching linker PDB: {name}")
            debug = matches[0]
        else:
            dsym = output / "dsym" / (name + ".dSYM")
            dsym.parent.mkdir(exist_ok=True)
            subprocess.run(["dsymutil", str(original), "-o", str(dsym)], check=True)
            members = list((dsym / "Contents/Resources/DWARF").iterdir())
            require(len(members) == 1, "Expected one arm64 DWARF payload")
            debug = members[0]
        debug_data = debug_info(cli, debug)
        require_pair(binary, debug_data)
        staged_binaries = []
        for product, file, relative in variants:
            final = debug_info(cli, file)
            require_pair(final, debug_data)
            require(final["code_id"] == binary["code_id"], "Packaged native code identity changed")
            staged_binaries.append({"product": product, "package_path": relative, "sha256": digest(file), **final})
        modules.append({"name": name, "target": target, "debug_id": binary["debug_id"],
                        "arch": binary["arch"], "code_id": binary["code_id"],
                        "binaries": staged_binaries,
                        "debug": {**stage_file(debug, output, "debug"), **debug_data}})
        if platform == "osx-arm64":
            shutil.rmtree(dsym)
    require(modules, "No packaged producer modules were recorded")
    extension = "zip" if platform == "win-x64" else "tar.gz"
    archives = {f"vtk-{product}-{platform}.{extension}": digest(Path(packages) / f"vtk-{product}-{platform}.{extension}")
                for product in ("sdk", "csharp")}
    values = cache_values(build)
    compiler_settings = {key: value for key, value in values.items()
                         if key.startswith(("CMAKE_C_COMPILER", "CMAKE_CXX_COMPILER", "CMAKE_MSVC_DEBUG_",
                                            "CMAKE_C_FLAGS_RELEASE", "CMAKE_CXX_FLAGS_RELEASE", "CMAKE_SHARED_LINKER_FLAGS_RELEASE"))}
    reply = build / ".cmake/api/v1/reply"
    cmake_version = json.loads(sorted(reply.glob("index-*.json"))[-1].read_text())["cmake"]["version"]["string"]
    for language in ("C", "CXX"):
        compiler_file = build / "CMakeFiles" / cmake_version / f"CMake{language}Compiler.cmake"
        for suffix in ("ID", "VERSION"):
            key = f"CMAKE_{language}_COMPILER_{suffix}"
            match = re.search(rf'set\({key} "([^"]+)"\)', compiler_file.read_text())
            require(match is not None, f"Missing compiler identity: {key}")
            compiler_settings[key] = match.group(1)
    manifest = {"schema_version": 2, "repository": REPOSITORY, "source_revision": revision,
                "source_tree": sdk_manifest["source_tree"], "vtk_version": sdk_manifest["vtk_version"],
                "platform": platform, "configuration": sdk_manifest["configuration"],
                "source_prefix": normalized(source) + "/", "build_prefix": normalized(build) + "/",
                "compiler_settings": compiler_settings, "archives": archives,
                "cmake_version": cmake_version,
                "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
                "modules": modules, "supplier_modules": suppliers,
                "artifacts": inventory(output), "outcome": "passed"}
    (output / "sentry-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    verify(output, revision, cli)
    return manifest


def verify(root, revision, cli):
    root = Path(root).resolve()
    manifest = json.loads((root / "sentry-manifest.json").read_text())
    require(manifest["source_revision"] == revision and manifest["repository"] == REPOSITORY
            and manifest["outcome"] == "passed", "Symbol manifest source/outcome mismatch")
    actual = inventory(root)
    actual.pop("sentry-manifest.json", None)
    require(actual == manifest["artifacts"], "Symbol staging inventory or hashes changed")
    require(manifest["platform"] in ("win-x64", "osx-arm64") and manifest["modules"], "Missing platform/module inventory")
    require(manifest.get("schema_version") == 2, "Unsupported symbol manifest schema")
    for module in manifest["modules"]:
        artifact = module["debug"]
        safe_name(artifact["path"])
        require(actual.get(artifact["path"]) == {"sha256": artifact["sha256"]}, "Artifact reference/digest mismatch")
        info = debug_info(cli, root / artifact["path"])
        require(info["debug_id"] == module["debug_id"] and info["arch"] == module["arch"], "Staged debug identity changed")
        require("debug" in info["features"], "Missing native debug information")
        for binary in module["binaries"]:
            require_pair(binary, info)
            require(binary["code_id"] == module["code_id"], "Packaged native code identity changed")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    for key in ("sdk", "runtime", "build", "source", "output"):
        prepare_parser.add_argument("--" + key, type=Path, required=True)
    prepare_parser.add_argument("--platform", choices=("win-x64", "osx-arm64"), required=True)
    prepare_parser.add_argument("--sentry-cli", required=True)
    prepare_parser.add_argument("--packages", type=Path, required=True)
    verifier = sub.add_parser("verify")
    verifier.add_argument("--root", type=Path, required=True)
    verifier.add_argument("--source-sha", required=True)
    verifier.add_argument("--sentry-cli", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.sdk, args.runtime, args.build, args.source, args.output, args.platform, args.sentry_cli, args.packages)
    else:
        result = verify(args.root, args.source_sha, args.sentry_cli)
    print(json.dumps({"source_revision": result["source_revision"], "modules": len(result["modules"]), "outcome": "passed"}))


if __name__ == "__main__":
    main()
