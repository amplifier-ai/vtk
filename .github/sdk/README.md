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
run and creates a stable SDK release only after a successful push build of
`master`. SDK releases use unique run/attempt tags and include archives, checksums
and qualification evidence. Pull requests build and test both products and retain
their packages and evidence as Actions artifacts for 30 days; they do not publish
GitHub releases. SDK releases do not replace the latest C# runtime release. The
publisher has no compiler jobs or independent VTK configuration. Public C# runtime
asset names remain unchanged; the archives now come from installed, relocated
libraries and include their non-system dependency closure.

Both release jobs require successful platform builds and the shared `sdk_unit`
job. Native SDK publication also uploads and verifies Sentry debug files before
creating a release. C# release creation depends on that publication job. A failed
or skipped prerequisite blocks both releases.

Download PR candidates from the producer run's Artifacts section:

```shell
gh run download {run-id} --repo amplifier-ai/vtk \
  --name vtk-sdk-package-win-x64 --dir {destination}
```

SDK packages include their checksum files. Native consumer receipts and logs are
in the separate `vtk-sdk-evidence-{platform}` artifacts. The `vtk-csharp-{platform}`
artifacts contain `vtk-csharp-{platform}.zip` or `.tar.gz`; extraction supplies
`native/` libraries, `managed/VTK.CSharp.dll`, dependency license evidence and
`runtime-manifest.json`.
The SDK evidence also retains `csharp-tests.log`, including the actual binding
coverage counts that successful CTest output normally hides.
PR builds still use Release configuration and run all existing build and SDK
checks; GitHub Release publication is a separate master-only operation.

## SDK archives and evidence

The archives are `vtk-sdk-win-x64.zip` and `vtk-sdk-osx-arm64.tar.gz`, each with a
`.sha256` file. `sdk-manifest.json` records the source revision/tree, VTK version,
ABI configuration and file digests. macOS targets arm64 and macOS 26.0; Windows
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
The compilation cache is saved after a successful native build, independently
of subsequent SDK packaging. Packaging failures still fail the job and block
publication; they do not discard valid cached compiler objects.

`build_with_retry.py` streams native build output and retains per-attempt command,
exit code and failed-command receipts in SDK evidence. On Windows, it permits one
incremental retry per build command only when every Ninja failure is a DLL/executable link command
reporting exactly `Access is denied.` without another diagnostic. Both native build
entry points use the same helper inside the unchanged storage/time guard. The
retry preserves command arguments, working directory, environment and targets;
permanent access failures and ordinary compilation/linker errors still fail CI.
This is a bounded mitigation for transient link-command access denials. A recovered
attempt does not identify the denied process or establish its underlying cause.

Cache lookup prefers the exact build profile, then the shared cache for the same
platform, before legacy caches. Publication-only workflow edits can change the
outer cache key without changing native compilation. The shared fallback lets
ccache validate and reuse compatible objects; compiler, flag and header checks
remain enabled. GitHub scopes PR caches to that PR's merge ref. A warm PR rerun
does not establish that `master` or a sibling PR can access those objects. Compare
the restored key, ref and per-run statistics when qualifying cache performance.

## C# runtime qualification

`package_csharp.py` consumes the same installed SDK after `package_sdk.py` writes
its manifest. It preserves library aliases and collects non-system native
dependencies recursively. macOS imports and loader paths are made relative to the
package, and edited arm64 libraries receive ad hoc signatures. Windows VC runtime
imports are resolved from the MSVC redistributable directory. The runtime manifest
records source/file identities, dependency and license evidence, and prerequisites:
.NET 8, macOS 26 or newer on Apple Silicon, or Windows 10 or newer with UCRT.

`verify_csharp.py` extracts the exact runtime archive, hides the original build,
removes native search-path overrides, and runs a .NET consumer that exercises core,
archive and FFmpeg wrappers, plus ONNX on macOS. The original build is restored in
`finally`. Failed required wrapper construction or native loading fails the check;
the separate coverage regression verifies that these failures cannot become skips.
Both archives are uploaded only after their consumer checks pass. Release jobs
upload the verified archive bytes unchanged, preserving aliases across the Actions
artifact boundary.

The native SDK publisher additionally verifies each receipt's success, exact
source/platform/archive identity and successful configure/build/CTest commands.
C# and SDK release tags target the compiled source and use unique run/attempt
identities; publishers refuse unexpected tag reuse or asset replacement.
The macOS build additionally runs the packaging unit suite with real Mach-O tools
to check loader-path edits and repeated rewriting of already portable libraries.

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
consumer's process-local `PATH`. macOS selects arm64 and deployment target 26.0.
Keep matching headers, libraries and CMake files together.

## Unity activation boundary

SDK publication does not change Unity's plugin, packaged libraries or dependency
pins. Switching these consumers requires Denis's explicit permission after the
SDK is ready. Existing Unity runtime inputs remain the reference until then.

## Native Sentry symbols and source context

`native-sdk.cmake` adds debug generation to the existing optimized Release build:
MSVC embeds object debug information with `/Z7` and emits full linker PDBs;
Apple Clang emits DWARF with `-g`. The ABI, module selection and optimization
remain the SDK profile's existing values. No second VTK build supplies symbols.

`sentry_symbols.py` intersects CMake File API native targets with both final
package inventories. It checks each producer module's binary/debug identity and
architecture, including internal ThirdParty libraries and native C# wrappers.
Mac dSYMs are generated while the build objects still exist. Packaged libraries
edited or signed for relocation must retain matching debug and code IDs.
External supplier modules are recorded separately; this pipeline does not invent
missing supplier debug information or claim their source-level coverage.

Source bundles are generated on the original builder, before relocation tests
remove or hide its inputs. Referenced VTK source and generated files must appear
with their exact bytes. Common/Core's generated `.cxx.inc` template instantiation
fragments are C++ source inputs and follow the same required coverage and byte
checks. Xdmf's compiled `.tpp` template definitions are required headers too.
Vendored Eigen's extensionless module headers, such as `Core` and `Dense`,
are required source files under its tracked include directory. The tracked
octree facade and libxml2's two compiled C include fragments follow those same
checks; arbitrary extensionless files and NASM fragments are not exempted.
Tracked source
links use the immutable VTK commit; generated files are
embedded without a fictitious GitHub path. The frozen
manifest records identities, source coverage, compiler settings and package
digests. Individual compiler/runtime-generated assembly files without a supported
source-language extension are outside the source-context coverage boundary.

`IO/Import/mtlsyntax.inl` keeps the checked-in generated MTL parser's code and
tables. Obsolete Ragel `#line` directives are removed so compiler debug records
name that materialized source and its physical lines, rather than nonexistent
historical `vtk3` files or `NONE`. The source-context regression guards that
boundary; parser regeneration is outside this publication workflow.

The CLI installer pins Sentry CLI 3.8.0 and verifies its platform asset SHA256
before execution. PRs perform only offline preparation/checks and retain native
debug/source artifacts for seven days. `.sdk-sentry/` and `*.src.zip` are temporary
build output and must never enter Git. No auth token is supplied to PR builders.

`publish_sentry.py` owns authenticated publication to `amplifier-ai/unity-plugin`
after master platform and package checks. It binds the SDK's own release to the
`amplifier-ai/vtk` source commit, configures VTK source-root mappings without
replacing VR mappings, waits for debug processing, and verifies exact debug IDs
and source/debug files through the Sentry API. Its receipt is included in the SDK
release and retained as an Actions artifact. `qualify_sentry_frame.py` then sends
two clearly labeled native INFO events in `ci-symbol-qualification`, using actual
addresses and module hashes recorded by the relocated SDK consumer. Sentry must
return the function, file, line, matching source context and immutable Git link
before a GitHub release is created. Event IDs are persisted before sending;
retries poll those IDs and do not blindly resend uncertain submissions.
These synthetic frames qualify symbol/source processing, not an actual Unity
crash or end-to-end crash capture.

VTK owns its native module symbols and sources. VR owns the plugin's symbols and
its application release; these SDK references do not automatically set the VR
event's commit metadata or activate a new SDK in Unity.

## Packaging tests

```shell
python -m unittest discover -s .github/sdk/tests -v
```
