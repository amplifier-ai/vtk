# Native VTK SDK releases

The native SDK is an additional release product for C++ consumers on Windows x64
and Apple Silicon. The existing C# bindings workflow and runtime archives retain
their own packaging. This SDK includes the development headers, CMake package,
shared libraries, import libraries on Windows, and installed diagnostic tools
from one native build of the Amplifier VTK fork.

The module profile is owned by [`native-sdk.cmake`](native-sdk.cmake). It includes
the Unity bridge's rendering, volume-rendering and image-I/O module closure,
including `RenderingExternal` on both platforms. Optional C# and Python bindings,
Qt, video and VTK XR modules are outside this profile. Windows Unity XR does not
depend on VTK XR modules in this SDK.

## Build and publication

[`../workflows/native-sdk.yml`](../workflows/native-sdk.yml) builds and installs
the native profile on both platforms. macOS targets arm64 and macOS 14.0;
Windows uses MSVC x64 and the shared CRT. SDK archives are published only after
the packaging unit tests and both relocated consumer checks succeed.

The archive names are `vtk-sdk-win-x64.zip` and `vtk-sdk-osx-arm64.tar.gz`.
Each has a corresponding `.sha256` file. `sdk-manifest.json` inside the archive
records the source revision/tree, VTK version, ABI options and file digests.
Internal pull requests publish a distinct SDK prerelease with a unique run tag;
fork pull requests retain Actions artifacts without publishing a release.

`package_sdk.py` packages the result of `cmake --install`. It neither regenerates
development files nor rebuilds published runtime libraries. `verify_sdk.py`
validates and relocates the archive, removes only the matching original SDK,
then configures, links and executes [`consumer`](consumer). Its receipt records
the actual command exits. The consumer checks the version, 64-bit IDs, legacy
VTK boolean ABI, Sequential SMP backend, required rendering/image APIs and
Windows Direct3D interoperability class. It does not render or qualify a Unity
player, GPU driver, headset or clinical workflow.

`run_guarded.py` monitors the owned command's free space and runtime. It stops
only that command's process tree and retains command receipts in `.sdk-evidence`.
Release archives contain the installed SDK, excluding the build tree and caches.

## Consume an SDK

Verify the published archive checksum, then extract it once into a reusable SDK
directory. Configure a C++ project using the extracted CMake package:

```shell
cmake -S consumer -B consumer-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DVTK_DIR=/path/to/sdk/lib/cmake/vtk-9.7
cmake --build consumer-build
```

Windows builds require an MSVC x64 environment. Add the SDK `bin` directory to
the consumer's process-local `PATH` when running it. macOS consumers must select
arm64 and the supported deployment target. Keep the SDK libraries, headers and
CMake package together; do not mix them with another VTK build.

## Unity activation boundary

Publishing an SDK does not change Unity's plugin, packaged libraries or dependency
pins. Switching those consumers requires Denis's explicit authorization after
the SDK is ready. Existing runtime inputs remain the reference until that step.

## Packaging tests

```shell
python -m unittest discover -s .github/sdk/tests -v
```
