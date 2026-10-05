# VTK SDK and C# packages from one build

The C# producer workflow builds native VTK once per platform in one `build`
directory. The same compiled libraries feed both the C# runtime package and the
Windows x64 or Apple Silicon SDK. The SDK adds installed headers, import libraries,
CMake exports and diagnostic tools to those native libraries.

## Owning configuration

[`../workflows/csharp-bindings.yml`](../workflows/csharp-bindings.yml) owns the
platform module selections, dependencies, compiler cache, C# compilation and
tests, SDK installation and relocated consumer verification. The shared
[`native-sdk.cmake`](native-sdk.cmake) profile records ABI and SDK installation
options; it does not disable bindings or create a second VTK module build.
`RenderingExternal` is available on both platforms for native bridge consumers.
Optional modules retain the producer's platform-specific dependency requirements.
Consumers selecting those modules may also need their external development and
runtime dependencies; the core/rendering consumer check has a narrower boundary.

`build_installable.py` requests CMake File API metadata before configuration.
After the C# targets are built, it completes only remaining installed native
libraries and tools in that same build directory. Already compiled objects are
reused. It does not select uninstalled C++ test executables or configure another
VTK tree. `cmake --install` then supplies the SDK package inputs.

[`../workflows/native-sdk.yml`](../workflows/native-sdk.yml) is a reusable
publication workflow. It downloads the verified SDK artifacts from the producer
run and creates a distinct prerelease. It has no compiler jobs or independent
VTK configuration. Existing C# runtime artifact names and packaging remain intact.

## SDK archives and evidence

The archives are `vtk-sdk-win-x64.zip` and `vtk-sdk-osx-arm64.tar.gz`, each with a
`.sha256` file. `sdk-manifest.json` records the source revision/tree, VTK version,
ABI configuration and file digests. macOS targets arm64 and macOS 14.0; Windows
uses MSVC x64 and its shared CRT.

`package_sdk.py` packages installed files without regenerating development files
or rebuilding runtime libraries. `verify_sdk.py` validates and relocates the
archive, removes only the matching original SDK, then configures, links and runs
[`consumer`](consumer). Verification receipts preserve command exit codes and
archive/source identities. Both platform and unit checks gate publication.

The consumer checks version, 64-bit IDs, legacy boolean ABI, Sequential SMP,
required rendering/image APIs and the Windows Direct3D interoperability class.
It does not render or qualify a Unity player, GPU, headset or clinical workflow.

`run_guarded.py` monitors storage and runtime for owned SDK commands, records
receipts and stops only their process tree. Compiler caching remains bounded to
2 GB and preserves standard validation; no sloppiness flags ignore compiler or
header checks. Statistics are reset and reported verbosely for each build so
restored lifetime counters cannot be mistaken for current cache effectiveness.

## Consume an SDK

Verify the archive checksum and extract once into a reusable directory. A C++
consumer selects the required VTK components and configures the installed package:

```shell
cmake -S consumer -B consumer-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DVTK_DIR=/path/to/sdk/lib/cmake/vtk-9.7
cmake --build consumer-build
```

Windows requires an MSVC x64 environment and the SDK `bin` directory on the
consumer's process-local `PATH`. macOS selects arm64 and deployment target 14.0.
Keep matching headers, libraries and CMake files together.

## Unity activation boundary

SDK publication does not change Unity's plugin, packaged libraries or dependency
pins. Switching these consumers requires Denis's explicit permission after the
SDK is ready. Existing Unity runtime inputs remain the reference until then.

## Packaging tests

```shell
python -m unittest discover -s .github/sdk/tests -v
```
