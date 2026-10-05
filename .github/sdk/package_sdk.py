#!/usr/bin/env python3
"""Package an installed native SDK without regenerating or rebuilding VTK."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import zipfile


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def cache_values(build):
    return dict(re.findall(r"^([^#/:\n]+):[^=\n]+=(.*)$",
                          (build / "CMakeCache.txt").read_text(), re.MULTILINE))


def inventory(sdk):
    files = {}
    for path in sorted(sdk.rglob("*")):
        name = path.relative_to(sdk).as_posix()
        if name == "sdk-manifest.json":
            continue
        if path.is_symlink():
            target = path.readlink()
            require(not target.is_absolute() and path.resolve().is_relative_to(sdk.resolve())
                    and path.exists(), f"Invalid SDK symlink: {name}")
            files[name] = {"symlink": str(target)}
        elif path.is_file():
            files[name] = {"sha256": digest(path)}
    return files


def package_sdk(sdk, build, source, platform, output):
    original_paths = [Path(p).absolute() for p in (sdk, build, source)]
    sdk, build, source, output = [Path(p).resolve() for p in (sdk, build, source, output)]
    require(platform in ("win-x64", "osx-arm64"), "Unsupported SDK platform")
    values = cache_values(build)
    expected = {"CMAKE_BUILD_TYPE": "Release", "BUILD_SHARED_LIBS": "ON", "VTK_INSTALL_SDK": "ON",
                "VTK_USE_64BIT_IDS": "ON", "VTK_USE_FUTURE_BOOL": "OFF",
                "VTK_USE_FUTURE_CONST": "OFF", "VTK_SMP_IMPLEMENTATION_TYPE": "Sequential"}
    for name, value in expected.items():
        require(values.get(name) == value, f"SDK profile mismatch: {name}")
    if platform == "osx-arm64":
        require(values.get("CMAKE_OSX_ARCHITECTURES") == "arm64", "SDK must target arm64")
        require(values.get("CMAKE_OSX_DEPLOYMENT_TARGET") == "14.0", "SDK must target macOS 14.0")
    version_file = (source / "CMake/vtkVersion.cmake").read_text()
    version = ".".join(re.search(rf"set\({name} (\d+)\)", version_file).group(1)
                       for name in ("VTK_MAJOR_VERSION", "VTK_MINOR_VERSION", "VTK_BUILD_VERSION"))
    require(version == "9.7.1", "SDK profile supports VTK 9.7.1")
    include = sdk / "include/vtk-9.7"
    for name in ("vtkVersion.h", "vtkType.h", "vtkExternalOpenGLCamera.h"):
        require((include / name).is_file(), f"SDK development header missing: {name}")
    for name in ("vtk-config.cmake", "VTK-targets.cmake"):
        require((sdk / "lib/cmake/vtk-9.7" / name).is_file(), f"SDK CMake package missing: {name}")
    require(bool(list((sdk / ("bin" if platform == "win-x64" else "lib")).glob(
        "*.dll" if platform == "win-x64" else "*.dylib"))), "SDK runtime libraries missing")
    for path in sdk.rglob("*.cmake"):
        text = path.read_text(errors="replace").replace("\\", "/")
        for original in (*original_paths, build, source, sdk):
            require(original.as_posix() not in text, f"SDK CMake file embeds a build/source/install path: {path.name}")
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD^{tree}"], text=True).strip()
    keys = (*expected, "CMAKE_CXX_COMPILER", "CMAKE_OSX_ARCHITECTURES", "CMAKE_OSX_DEPLOYMENT_TARGET",
            "CMAKE_MSVC_RUNTIME_LIBRARY")
    manifest = {"schema_version": 1, "vtk_version": version, "platform": platform,
                "source_revision": revision, "source_tree": tree,
                "configuration": {key: values[key] for key in keys if key in values},
                "files": inventory(sdk)}
    (sdk / "sdk-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    output.mkdir(parents=True, exist_ok=True)
    extension = "zip" if platform == "win-x64" else "tar.gz"
    archive = output / f"vtk-sdk-{platform}.{extension}"
    require(not archive.exists(), f"SDK archive already exists: {archive}")
    if platform == "win-x64":
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(sdk.rglob("*")):
                require(not path.is_symlink(), "Windows SDK archive cannot contain symlinks")
                if path.is_file():
                    bundle.write(path, path.relative_to(sdk).as_posix())
    else:
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(sdk, arcname=".")
    Path(str(archive) + ".sha256").write_text(f"{digest(archive)}  {archive.name}\n")
    return archive


def validate_manifest(sdk):
    manifest = json.loads((sdk / "sdk-manifest.json").read_text())
    actual = inventory(sdk)
    require(actual == manifest["files"], "SDK file digest or symlink inventory differs from manifest")
    return manifest


def safe_name(name):
    name = name.replace("\\", "/")
    path = PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts and ":" not in name,
            f"Invalid archive path: {name}")


def extract_sdk(archive, destination):
    require(not destination.exists(), "Relocated SDK destination must be new")
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                safe_name(member.filename)
                require((member.external_attr >> 16) & 0o170000 != 0o120000,
                        "Windows SDK archive cannot contain symlinks")
            bundle.extractall(destination)
    else:
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                safe_name(member.name)
                if member.issym() or member.islnk():
                    target = PurePosixPath(member.name).parent / member.linkname
                    safe_name(str(target))
                require(member.isfile() or member.isdir() or member.issym() or member.islnk(),
                        "Unsupported SDK archive entry")
            bundle.extractall(destination, filter="data")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sdk", "build", "source", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--platform", choices=("win-x64", "osx-arm64"), required=True)
    args = parser.parse_args()
    print(package_sdk(args.sdk, args.build, args.source, args.platform, args.output))


if __name__ == "__main__":
    main()
