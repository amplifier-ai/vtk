#!/usr/bin/env python3
"""Package installed C# libraries with a portable native dependency closure."""
import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile

from package_sdk import cache_values, digest, require


VC_RUNTIME = re.compile(r"(?:msvcp|vcruntime|concrt|vcomp|vcamp)\d+.*\.dll$", re.I)


def macos_version(value):
    require(bool(re.fullmatch(r"\d+\.\d+(?:\.\d+)?", value)), "Invalid minimum macOS version")
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) * (3 - len(parts))


def parse_macos_dependencies(text, identity):
    dependencies = []
    for line in text.splitlines():
        if " (compatibility version " in line:
            name = line.strip().split(" (compatibility version ", 1)[0]
            if name != identity:
                dependencies.append(name)
    return dependencies


def parse_windows_dependencies(text):
    return list(dict.fromkeys(re.findall(r"^\s+([^\s\\/:]+\.dll)\s*$", text, re.M | re.I)))


class NativeTools:
    def __init__(self, platform):
        self.platform = platform

    def inspect(self, library):
        if self.platform == "win-x64":
            output = subprocess.check_output(
                ["dumpbin", "/NOLOGO", "/DEPENDENTS", str(library)], text=True, errors="replace")
            return {"dependencies": parse_windows_dependencies(output), "rpaths": [], "identity": None}
        architectures = subprocess.check_output(["lipo", "-archs", str(library)], text=True).split()
        require("arm64" in architectures, f"Native runtime has no arm64 slice: {library.name}")
        identity_output = subprocess.check_output(["otool", "-arch", "arm64", "-D", str(library)], text=True)
        identities = [line.strip() for line in identity_output.splitlines()[1:] if line.strip()]
        require(len(identities) == 1, f"Expected one thin dylib install identity: {library.name}")
        output = subprocess.check_output(["otool", "-arch", "arm64", "-L", str(library)], text=True)
        commands = subprocess.check_output(["otool", "-arch", "arm64", "-l", str(library)], text=True)
        minimum = re.search(r"cmd LC_BUILD_VERSION\s+cmdsize \d+\s+platform (?:1|MACOS|macOS)\s+minos ([\d.]+)", commands)
        if minimum is None:
            minimum = re.search(r"cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version ([\d.]+)", commands)
        require(minimum is not None, f"Native runtime has no macOS deployment version: {library.name}")
        return {"identity": identities[0],
                "dependencies": parse_macos_dependencies(output, identities[0]),
                "rpaths": re.findall(r"cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset", commands),
                "architectures": architectures, "minimum_macos": minimum.group(1)}

    def rewrite(self, library, info, replacements):
        command = ["install_name_tool", "-id", "@loader_path/" + library.name]
        for before, after in sorted(replacements.items()):
            if before != after:
                command.extend(["-change", before, after])
        for rpath in sorted(set(info["rpaths"])):
            if rpath != "@loader_path":
                command.extend(["-delete_rpath", rpath])
        if "@loader_path" not in info["rpaths"]:
            command.extend(["-add_rpath", "@loader_path"])
        command.append(str(library))
        subprocess.run(command, check=True)

    @staticmethod
    def sign(library):
        subprocess.run(["codesign", "--force", "--sign", "-", str(library)], check=True)
        subprocess.run(["codesign", "--verify", "--strict", str(library)], check=True)


def windows_redist_directories():
    root = os.environ.get("VCToolsRedistDir")
    if not root:
        return []
    return sorted({path.parent for path in (Path(root) / "x64").glob("*/*.dll")})


def system_dependency(name, platform, system_directory=None):
    if platform == "osx-arm64":
        return name.startswith(("/usr/lib/", "/System/Library/"))
    if VC_RUNTIME.fullmatch(name):
        return False
    if name.lower().startswith(("api-ms-win-", "ext-ms-")):
        return True
    directory = system_directory
    if directory is None:
        directory = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"
    return (directory / name).is_file()


def runtime_inventory(package):
    result = {}
    for path in sorted(package.rglob("*")):
        name = path.relative_to(package).as_posix()
        if name == "runtime-manifest.json":
            continue
        if path.is_symlink():
            target = path.readlink()
            require(not target.is_absolute() and path.exists()
                    and path.resolve().is_relative_to(package.resolve()), f"Invalid runtime alias: {name}")
            result[name] = {"symlink": target.as_posix()}
        elif path.is_file():
            result[name] = {"sha256": digest(path)}
    return result


def validate_runtime_manifest(package):
    manifest = json.loads((package / "runtime-manifest.json").read_text())
    require(runtime_inventory(package) == manifest["files"], "C# runtime inventory differs from manifest")
    require(manifest["vtk_version"] == "9.7.1", "Unexpected C# runtime VTK version")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", manifest["source_revision"])), "Invalid C# source revision")
    return manifest


def validate_native_runtime(package, platform, tools=None, system_directory=None, minimum_macos="26.0"):
    tools = tools or NativeTools(platform)
    native = package / "native"
    require(native.is_dir(), "C# native runtime directory is missing")
    checked = []
    for library in sorted(native.iterdir()):
        if library.is_symlink() or not library.is_file():
            continue
        info = tools.inspect(library)
        if platform == "osx-arm64":
            minimum = macos_version(info.get("minimum_macos", "26.0"))
            require(minimum <= macos_version(minimum_macos),
                    f"Native runtime requires newer macOS than {minimum_macos}: {library.name}")
            require(info["identity"] == "@loader_path/" + library.name,
                    f"Non-portable native identity: {library.name}")
            require(all(rpath == "@loader_path" for rpath in info["rpaths"]),
                    f"Non-portable native rpath: {library.name}")
        for dependency in info["dependencies"]:
            if system_dependency(dependency, platform, system_directory):
                continue
            if platform == "osx-arm64":
                require(dependency.startswith("@loader_path/"),
                        f"Non-portable native dependency: {dependency}")
                target = native / dependency.removeprefix("@loader_path/")
                require(target.resolve().is_relative_to(native.resolve()), "Native dependency escapes package")
            else:
                require(Path(dependency).name == dependency, f"Non-portable native dependency: {dependency}")
                target = find_library(native, dependency)
            require(target is not None and target.is_file(), f"Unresolved packaged dependency: {dependency}")
        checked.append({"name": library.name, **info})
    require(bool(checked), "C# runtime contains no native libraries")
    return checked


def find_library(directory, name):
    candidate = directory / name
    if candidate.is_file():
        return candidate
    if directory.is_dir():
        matches = [path for path in directory.iterdir() if path.name.casefold() == name.casefold() and path.is_file()]
        require(len(matches) <= 1, f"Ambiguous native dependency: {name}")
        if matches:
            return matches[0]
    return None


class RuntimeBundle:
    def __init__(self, sdk, output, platform, tools, dependency_directories, system_directory, redist_directories):
        self.sdk = sdk
        self.output = output
        self.native = output / "native"
        self.platform = platform
        self.tools = tools
        self.directories = [sdk / "bin", sdk / "lib", sdk / "lib/csharp", *dependency_directories]
        self.system_directory = system_directory
        self.redist_directories = redist_directories
        self.sources = {}
        self.source_digests = {}
        self.pending = deque()
        self.records = []
        self.system = set()

    def copy_library(self, source):
        source = Path(source).absolute()
        require(source.is_file(), f"Native dependency is missing: {source}")
        real = source.resolve()
        checksum = digest(real)
        for path in (real, source):
            name = path.name
            require(name not in self.source_digests or self.source_digests[name] == checksum,
                    f"Native basename collision: {name}")
        if real.name not in self.sources:
            shutil.copy2(real, self.native / real.name)
            self.sources[real.name] = real
            self.source_digests[real.name] = checksum
            self.pending.append(real.name)
        if source.name != real.name and source.name not in self.source_digests:
            require(self.platform == "osx-arm64", "Windows native runtime cannot contain symlinks")
            (self.native / source.name).symlink_to(real.name)
            self.source_digests[source.name] = checksum
        return source.name

    def resolve(self, dependency, source, info):
        if self.platform == "osx-arm64":
            if dependency.startswith("/"):
                path = Path(dependency)
                return path if path.is_file() else None
            if dependency.startswith("@loader_path/"):
                path = source.parent / dependency.removeprefix("@loader_path/")
                return path if path.is_file() else None
            if dependency.startswith("@rpath/"):
                suffix = dependency.removeprefix("@rpath/")
                for rpath in info["rpaths"]:
                    expanded = rpath.replace("@loader_path", str(source.parent))
                    if expanded.startswith("/"):
                        path = Path(expanded) / suffix
                        if path.is_file():
                            return path
            if dependency.startswith("@executable_path"):
                return None
            name = Path(dependency).name
            directories = [source.parent, *self.directories]
        else:
            name = dependency
            directories = self.redist_directories if VC_RUNTIME.fullmatch(name) else [source.parent, *self.directories]
        for directory in directories:
            candidate = find_library(Path(directory), name)
            if candidate is not None:
                return candidate
        return None

    def close(self):
        while self.pending:
            name = self.pending.popleft()
            source = self.sources[name]
            info = self.tools.inspect(source)
            replacements = {}
            for dependency in info["dependencies"]:
                if system_dependency(dependency, self.platform, self.system_directory):
                    self.system.add(dependency)
                    continue
                candidate = self.resolve(dependency, source, info)
                require(candidate is not None, f"Unresolved native dependency {dependency} required by {name}")
                packaged_name = self.copy_library(candidate)
                replacements[dependency] = ("@loader_path/" if self.platform == "osx-arm64" else "") + packaged_name
            self.records.append({"name": name, "source_path": str(source),
                                 "source_sha256": self.source_digests[name], "original_imports": info,
                                 "packaged_dependencies": replacements})
            if self.platform == "osx-arm64":
                library = self.native / name
                mode = library.stat().st_mode
                library.chmod(mode | stat.S_IWUSR)
                self.tools.rewrite(library, info, replacements)
                self.tools.sign(library)
                library.chmod(mode)


def copy_licenses(output, source, dependencies, dependency_directories):
    destination = output / "licenses"
    destination.mkdir()
    vtk_license = source / "Copyright.txt"
    require(vtk_license.is_file(), "VTK license is missing from the configured source")
    shutil.copy2(vtk_license, destination / "VTK-Copyright.txt")
    evidence = []
    for record in dependencies:
        path = Path(record["source_path"])
        license_sources = []
        package = None
        parts = path.parts
        if "Cellar" in parts:
            position = parts.index("Cellar")
            if position + 2 < len(parts):
                package = parts[position + 1]
                package_root = Path(*parts[:position + 3])
                for pattern in ("LICENSE*", "COPYING*", "COPYRIGHT*", ".brew/*.rb", "share/licenses/**/*"):
                    license_sources.extend(p for p in package_root.glob(pattern) if p.is_file())
        for directory in dependency_directories:
            root = Path(directory).parent
            metadata = root.parent / "vcpkg/info"
            if not path.is_relative_to(root.resolve()) or not metadata.is_dir():
                continue
            for listing in metadata.glob("*.list"):
                if any(line.casefold().endswith("/bin/" + path.name.casefold())
                       for line in listing.read_text(errors="replace").splitlines()):
                    package = listing.name.split("_", 1)[0]
                    copyright_file = root / "share" / package / "copyright"
                    if copyright_file.is_file():
                        license_sources.append(copyright_file)
                    break
        copied = []
        for license_file in sorted(set(license_sources)):
            token = hashlib.sha256(str(license_file).encode()).hexdigest()[:12]
            name = f"{package or 'dependency'}-{token}-{license_file.name}"
            shutil.copy2(license_file, destination / name)
            copied.append("licenses/" + name)
        if not path.is_relative_to(source.resolve()) and not path.is_relative_to(output.resolve()):
            evidence.append({"library": record["name"], "source_path": str(path),
                             "package": package, "license_evidence": copied})
    return evidence


def package_csharp(sdk, build, output, platform, dependency_directories=(), tools=None,
                   system_directory=None, redist_directories=None, minimum_macos="26.0"):
    sdk, build, output = (Path(path).resolve() for path in (sdk, build, output))
    require(platform in ("win-x64", "osx-arm64"), "Unsupported C# runtime platform")
    macos_version(minimum_macos)
    require(not output.exists(), "C# runtime output must be new")
    require(not output.is_relative_to(sdk) and not sdk.is_relative_to(output), "SDK and runtime must be separate")
    identity = json.loads((sdk / "sdk-manifest.json").read_text())
    require(identity["platform"] == platform and identity["vtk_version"] == "9.7.1", "SDK identity mismatch")
    managed = sdk / "lib/csharp/VTK.CSharp.dll"
    require(managed.is_file(), "Installed managed C# assembly is missing")
    values = cache_values(build)
    source = Path(values["CMAKE_HOME_DIRECTORY"])
    output.mkdir(parents=True)
    (output / "native").mkdir()
    (output / "managed").mkdir()
    shutil.copy2(managed, output / "managed/VTK.CSharp.dll")
    dependency_directories = [Path(path).resolve() for path in dependency_directories]
    tools = tools or NativeTools(platform)
    redist_directories = windows_redist_directories() if redist_directories is None else redist_directories
    bundle = RuntimeBundle(sdk, output, platform, tools, dependency_directories,
                           system_directory, redist_directories)
    extension = ".dll" if platform == "win-x64" else ".dylib"
    for directory in (sdk / "bin", sdk / "lib", sdk / "lib/csharp"):
        if directory.is_dir():
            for library in sorted(directory.iterdir()):
                if library.name != "VTK.CSharp.dll" and library.name.lower().endswith(extension):
                    bundle.copy_library(library)
    helper = "vtkCSharpHelper.dll" if platform == "win-x64" else "libvtkCSharpHelper.dylib"
    require((output / "native" / helper).is_file(), "Native C# helper is missing")
    require(any("CommonCoreCSharp" in name for name in bundle.sources), "Core C# wrapper is missing")
    bundle.close()
    validation = validate_native_runtime(output, platform, tools, system_directory, minimum_macos)
    licenses = copy_licenses(output, source, bundle.records, dependency_directories)
    prerequisites = [".NET 8 runtime"]
    if platform == "win-x64":
        prerequisites.append("Windows 10 or later with the Windows Universal C Runtime")
    else:
        prerequisites.append(f"Apple Silicon with macOS {minimum_macos} or later")
    manifest = {"schema_version": 1, "vtk_version": identity["vtk_version"], "platform": platform,
                "source_revision": identity["source_revision"], "source_tree": identity["source_tree"],
                "minimum_macos": minimum_macos if platform == "osx-arm64" else None,
                "prerequisites": prerequisites, "system_dependencies": sorted(bundle.system),
                "native_dependencies": bundle.records, "native_validation": validation,
                "dependency_license_evidence": licenses,
                "windows_vc_runtime": {"policy": "Bundle dynamically imported VC runtime libraries from the MSVC x64 redistributable directory",
                                       "libraries": sorted(record["name"] for record in bundle.records
                                                           if VC_RUNTIME.fullmatch(record["name"]))} if platform == "win-x64" else None,
                "macos_signing": "Ad hoc native library signatures; not application signing or notarization" if platform == "osx-arm64" else None,
                "files": runtime_inventory(output)}
    (output / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    validate_runtime_manifest(output)
    return manifest


def archive_csharp(package, archive, platform):
    package, archive = Path(package).resolve(), Path(archive).resolve()
    validate_runtime_manifest(package)
    require(not archive.exists() and not archive.is_relative_to(package), "C# archive must be new and separate")
    archive.parent.mkdir(parents=True, exist_ok=True)
    if platform == "win-x64":
        require(archive.suffix == ".zip", "Windows C# runtime requires ZIP")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(package.rglob("*")):
                require(not path.is_symlink(), "Windows C# archive cannot contain symlinks")
                if path.is_file():
                    bundle.write(path, path.relative_to(package).as_posix())
    else:
        require(archive.name.endswith(".tar.gz"), "macOS C# runtime requires tar.gz")
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(package, arcname=".")
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sdk", "build", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--platform", choices=("win-x64", "osx-arm64"), required=True)
    parser.add_argument("--dependency-directory", type=Path, action="append", default=[])
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--minimum-macos", default="26.0")
    args = parser.parse_args()
    require(sys.platform == ("win32" if args.platform == "win-x64" else "darwin"), "Packaging host mismatch")
    result = package_csharp(args.sdk, args.build, args.output, args.platform, args.dependency_directory,
                            minimum_macos=args.minimum_macos)
    if args.archive:
        archive_csharp(args.output, args.archive, args.platform)
    print(json.dumps({"platform": result["platform"], "source_revision": result["source_revision"],
                      "native_libraries": len(result["native_dependencies"]),
                      "archive": str(args.archive) if args.archive else None}))


if __name__ == "__main__":
    main()
