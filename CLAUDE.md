# VTK C# Bindings — Project Guide

## Branch & PR

- Branch: `feature/csharp-bindings`
- Fork: `git@github.com:amplifier-ai/vtk.git`
- PR: https://github.com/amplifier-ai/vtk/pull/1

## Architecture

```
vtkFoo.h ──► WrapCSharp  ──► vtkFooCSharp.cxx  (extern "C" exports)
         ──► ParseCSharp ──► vtkFoo.cs           (C# class with [DllImport])
```

Two code generators consume VTK::WrappingTools parser IR:
- `Wrapping/Tools/vtkWrapCSharp.c` — generates C-export wrappers (one per method)
- `Wrapping/Tools/vtkParseCSharp.c` — generates C# managed classes

Each VTK module produces a native shared library (`vtkFooCSharp.dll/.so/.dylib`).
All `.cs` files compile into a single `VTK.CSharp.dll` assembly.

## Key Files

| Path | Purpose |
|------|---------|
| `Wrapping/Tools/vtkWrapCSharp.c` | C export wrapper generator (~860 lines) |
| `Wrapping/Tools/vtkParseCSharp.c` | C# source generator (~910 lines) |
| `Utilities/CSharp/` | Native utility module (lifecycle, observers) |
| `Wrapping/CSharp/vtk/vtkObjectBase.cs` | Base class: IntPtr handle, IDisposable |
| `Wrapping/CSharp/vtk/VtkObjectManager.cs` | Object identity map (ConcurrentDictionary) |
| `Wrapping/CSharp/vtk/VtkGarbageCollector.cs` | Background timer sweeps dead WeakRefs |
| `Wrapping/CSharp/vtk/VtkNativeLibrary.cs.in` | CMake-configured native library resolver |
| `CMake/vtkModuleWrapCSharp.cmake` | Build orchestration (~400 lines) |
| `Wrapping/CSharp/CMakeLists.txt` | Assembly build + test registration |

## Build (macOS/Linux)

```bash
mkdir build && cd build
cmake -DVTK_WRAP_CSHARP=ON -DVTK_BUILD_TESTING=ON ..
cmake --build .
ctest -R vtkCSharpTests
```

## Tests

| Test | What it verifies |
|------|-----------------|
| CSharpDelete | Explicit Dispose lifecycle |
| CSharpGCAndDelete | Mixed GC + explicit Dispose |
| CSharpConcurrencyGC | Multi-threaded stress test (10s) |
| CSharpBindingCoverage | Instantiates 171 safe classes, verifies GetClassName |

---

## Build on Windows

### Prerequisites

- Visual Studio 2022 (C++ desktop workload)
- .NET 8 SDK or later
- CMake 3.27+
- Ninja (recommended) or MSBuild

### External Dependencies (install via vcpkg or manually)

| Dependency | For modules | Install |
|------------|-------------|---------|
| OpenXR SDK | RenderingOpenXR | `vcpkg install openxr-loader` |
| zSpace SDK | RenderingZSpace | Proprietary, download from zspace.com |
| ANARI SDK | RenderingAnari | `vcpkg install anari` |
| Dawn (WebGPU) | RenderingWebGPU | Build from source (Google) |
| FFmpeg | IOFFMPEG, RenderingFFMPEGOpenGL2 | `vcpkg install ffmpeg` |
| GDAL | IOGDAL, GeovisGDAL | `vcpkg install gdal` |
| OpenCASCADE | IOOCCT | `vcpkg install opencascade` |
| Alembic | IOAlembic | `vcpkg install alembic` |
| USD (Pixar) | IOUSD | Build from source |
| OpenVDB | IOOpenVDB | `vcpkg install openvdb` |
| HDF5 | IOH5part | `vcpkg install hdf5` |
| XDMF3 | IOXdmf3 | Bundled in VTK ThirdParty |
| OSPRay | RenderingRayTracing | Download from Intel |
| ANARI backends | RenderingAnari | OSPRay, VisRTX, or RadeonProRender |
| ONNX Runtime | FiltersONNX | `vcpkg install onnxruntime` |
| Boost | InfovisBoostGraphAlgorithms | `vcpkg install boost-graph` |

### CMake Configure (full build)

```bash
cmake -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake ^
  -DVTK_WRAP_CSHARP=ON ^
  -DVTK_BUILD_TESTING=ON ^
  ^
  # VR/XR (Windows + Linux only) ^
  -DVTK_MODULE_ENABLE_VTK_RenderingOpenXR=YES ^
  -DVTK_MODULE_ENABLE_VTK_RenderingOpenXRRemoting=YES ^
  -DVTK_MODULE_ENABLE_VTK_RenderingVR=YES ^
  -DVTK_MODULE_ENABLE_VTK_RenderingZSpace=YES ^
  ^
  # Ray tracing ^
  -DVTK_MODULE_ENABLE_VTK_RenderingRayTracing=YES ^
  -DVTK_MODULE_ENABLE_VTK_RenderingAnari=YES ^
  -DVTKm_ENABLE_OSPRAY=ON ^
  ^
  # Video ^
  -DVTK_MODULE_ENABLE_VTK_IOFFMPEG=YES ^
  -DVTK_MODULE_ENABLE_VTK_RenderingFFMPEGOpenGL2=YES ^
  ^
  # Geodata ^
  -DVTK_MODULE_ENABLE_VTK_IOGDAL=YES ^
  -DVTK_MODULE_ENABLE_VTK_GeovisGDAL=YES ^
  -DVTK_MODULE_ENABLE_VTK_IOGeoJSON=YES ^
  -DVTK_MODULE_ENABLE_VTK_IOLAS=YES ^
  ^
  # CAD / 3D formats ^
  -DVTK_MODULE_ENABLE_VTK_IOOCCT=YES ^
  -DVTK_MODULE_ENABLE_VTK_IOAlembic=YES ^
  -DVTK_MODULE_ENABLE_VTK_IOUSD=YES ^
  -DVTK_MODULE_ENABLE_VTK_IOOpenVDB=YES ^
  ^
  # Scientific data ^
  -DVTK_MODULE_ENABLE_VTK_IOH5part=YES ^
  -DVTK_MODULE_ENABLE_VTK_IOXdmf3=YES ^
  ^
  # GPU imaging & rendering ^
  -DVTK_MODULE_ENABLE_VTK_ImagingOpenGL2=YES ^
  -DVTK_MODULE_ENABLE_VTK_RenderingVolumeAMR=YES ^
  -DVTK_MODULE_ENABLE_VTK_RenderingExternal=YES ^
  -DVTK_MODULE_ENABLE_VTK_RenderingWebGPU=YES ^
  ^
  # Analytics / ML ^
  -DVTK_MODULE_ENABLE_VTK_FiltersReebGraph=YES ^
  -DVTK_MODULE_ENABLE_VTK_FiltersONNX=YES ^
  -DVTK_MODULE_ENABLE_VTK_InfovisBoostGraphAlgorithms=YES ^
  ^
  # Serialization & misc ^
  -DVTK_MODULE_ENABLE_VTK_SerializationManager=YES ^
  -DVTK_MODULE_ENABLE_VTK_CommonArchive=YES ^
  -DVTK_MODULE_ENABLE_VTK_DomainsMicroscopy=YES ^
  -DVTK_MODULE_ENABLE_VTK_IOOMF=YES ^
  -DVTK_MODULE_ENABLE_VTK_WebGLExporter=YES ^
  -DVTK_MODULE_ENABLE_VTK_TestingSerialization=YES ^
  ^
  ..
```

### CMake Configure (minimal — no external deps)

```bash
cmake -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DVTK_WRAP_CSHARP=ON ^
  -DVTK_BUILD_TESTING=ON ^
  -DVTK_MODULE_ENABLE_VTK_RenderingVolumeAMR=YES ^
  -DVTK_MODULE_ENABLE_VTK_RenderingExternal=YES ^
  -DVTK_MODULE_ENABLE_VTK_RenderingVR=YES ^
  -DVTK_MODULE_ENABLE_VTK_ImagingOpenGL2=YES ^
  -DVTK_MODULE_ENABLE_VTK_FiltersReebGraph=YES ^
  -DVTK_MODULE_ENABLE_VTK_SerializationManager=YES ^
  -DVTK_MODULE_ENABLE_VTK_CommonArchive=YES ^
  -DVTK_MODULE_ENABLE_VTK_DomainsMicroscopy=YES ^
  -DVTK_MODULE_ENABLE_VTK_IOGeoJSON=YES ^
  -DVTK_MODULE_ENABLE_VTK_IOLAS=YES ^
  -DVTK_MODULE_ENABLE_VTK_IOOMF=YES ^
  -DVTK_MODULE_ENABLE_VTK_WebGLExporter=YES ^
  -DVTK_MODULE_ENABLE_VTK_TestingSerialization=YES ^
  ..
```

### CMake Configure (HPC cluster — add MPI modules)

```bash
  # Add to any config above:
  -DVTK_MODULE_ENABLE_VTK_ParallelMPI=YES ^
  -DVTK_MODULE_ENABLE_VTK_FiltersParallelMPI=YES ^
  -DVTK_MODULE_ENABLE_VTK_FiltersParallelFlowPaths=YES ^
  -DVTK_MODULE_ENABLE_VTK_FiltersParallelGeometry=YES ^
  -DVTK_MODULE_ENABLE_VTK_IOMPIImage=YES ^
  -DVTK_MODULE_ENABLE_VTK_IOMPIParallel=YES ^
```

### Build & Test

```bash
cmake --build . --config Release
ctest -C Release -R vtkCSharpTests
```

---

## Module Reference

All modules below are automatically wrapped when enabled in CMake. No code changes needed.

### Currently Wrapped (126 modules)

These are wrapped in the default build with `-DVTK_WRAP_CSHARP=ON`:

Core: CommonCore, CommonColor, CommonComputationalGeometry, CommonDataModel,
CommonExecutionModel, CommonMath, CommonMisc, CommonSystem, CommonTransforms

Filters: AMR, CellGrid, Core, Extraction, FlowPaths, General, Generic, Geometry,
GeometryPreview, Hybrid, HyperTree, Imaging, Modeling, Parallel, ParallelDIY2,
ParallelImaging, Points, Programmable, Reduction, Selection, SMP, Sources,
Statistics, Temporal, Tensor, Texture, Topology, Verdict

Imaging: Color, Core, Fourier, General, Hybrid, Math, Morphological, Sources,
Statistics, Stencil

IO: AMR, Asynchronous, Avmesh, CellGrid, Cesium3DTiles, CGNSReader, Chemistry,
CityGML, CONVERGECFD, Core, Engys, EnSight, ERF, Exodus, Export, ExportGL2PS,
ExportPDF, FDS, FLUENTCFF, Geometry, HDF, Image, Import, Infovis, IOSS, LANLX3D,
Legacy, LSDyna, MINC, MotionFX, Movie, NetCDF, OggTheora, Parallel, ParallelExodus,
ParallelXML, PLY, SegY, SQL, TecplotTable, VeraOut, Video, XML, XMLParser

Rendering: Annotation, CellGrid, Context2D, ContextOpenGL2, Core, FreeType,
GL2PSOpenGL2, GridAxes, HyperTreeGrid, Image, Label, LICOpenGL2, LOD, OpenGL2,
Parallel, SceneGraph, UI, Volume, VolumeOpenGL2, VRModels, VtkJS

Interaction: Image, Style, Widgets
Infovis: Core, Layout
Charts: Core
Views: Context2D, Core, Infovis
Domains: Chemistry, ChemistryOpenGL2
Geovis: Core
Parallel: Core
Testing: Rendering

### Optional YES Modules (31) — wrap when dependency available

#### VR / XR

| Module | Description | Dependency | Platforms |
|--------|-------------|------------|-----------|
| **RenderingOpenXR** | OpenXR-based VR/AR rendering. Supports head-mounted displays via the OpenXR standard (Meta Quest, Valve Index, HoloLens, etc.) | OpenXR SDK | Win/Linux |
| **RenderingOpenXRRemoting** | Holographic remoting for HoloLens 2. Streams rendered frames to a HoloLens over the network | OpenXR SDK + Remoting | Win |
| **RenderingVR** | Base VR rendering framework. Provides VR-specific render window, camera, and interaction classes shared by OpenXR backends | none | Win/Linux |
| **RenderingZSpace** | Stereoscopic zSpace display support. Head-tracked 3D visualization with stylus interaction for engineering, medical training, and oil & gas | zSpace SDK (proprietary) | Win |

#### Ray Tracing

| Module | Description | Dependency | Platforms |
|--------|-------------|------------|-----------|
| **RenderingRayTracing** | Photo-realistic ray-traced rendering via Intel OSPRay or NVIDIA OptiX. Produces high-quality images with global illumination, ambient occlusion, and path tracing | OSPRay or OptiX | Win/Linux/macOS |
| **RenderingAnari** | Rendering via ANARI (Khronos standard). Unified API to plug in any ray-tracing backend (OSPRay, VisRTX, RadeonProRender) without recompilation. Future replacement for RenderingRayTracing | ANARI SDK | Win/Linux/macOS |

#### Video / Media

| Module | Description | Dependency | Platforms |
|--------|-------------|------------|-----------|
| **IOFFMPEG** | Read/write video files (MP4, AVI, MKV) using FFmpeg. Used for loading video as image sequences and encoding animation output | FFmpeg 4+ | Win/Linux/macOS |
| **RenderingFFMPEGOpenGL2** | Capture OpenGL render window output directly to video files. Records viewport to MP4/AVI without intermediate frame dumps | FFmpeg 4+ | Win/Linux/macOS |

#### Geodata

| Module | Description | Dependency | Platforms |
|--------|-------------|------------|-----------|
| **IOGDAL** | Read geospatial raster data via GDAL: GeoTIFF, DEM, ECW, MrSID, DTED, and 100+ other formats. Essential for GIS applications | GDAL 3+ | Win/Linux/macOS |
| **GeovisGDAL** | Geospatial visualization helpers built on GDAL. Provides map projections and coordinate transformations for geographic rendering | GDAL 3+ | Win/Linux/macOS |
| **IOGeoJSON** | Read/write GeoJSON files — the standard web interchange format for geographic features (points, lines, polygons with attributes) | jsoncpp (bundled) | Win/Linux/macOS |
| **IOLAS** | Read LAS/LAZ LiDAR point cloud files. Widely used for terrain scanning, forestry, urban modeling, and autonomous driving data | none | Win/Linux/macOS |

#### CAD / 3D Interchange

| Module | Description | Dependency | Platforms |
|--------|-------------|------------|-----------|
| **IOOCCT** | Read CAD files via OpenCASCADE: STEP, IGES, BREP. Converts boundary-representation solids to VTK meshes for visualization | OpenCASCADE 7.6+ | Win/Linux/macOS |
| **IOAlembic** | Read/write Alembic (.abc) files — the industry standard for baked animation and VFX data exchange between DCC tools (Maya, Houdini, Blender) | Alembic 1.8+ | Win/Linux/macOS |
| **IOUSD** | Read/write Pixar Universal Scene Description (.usd/.usda/.usdc) files — the emerging standard for 3D asset interchange across film, games, and simulation | USD 23+ | Win/Linux/macOS |
| **IOOpenVDB** | Read/write OpenVDB (.vdb) files — the industry standard for sparse volumetric data (fog, fire, clouds, signed distance fields) used in VFX | OpenVDB 9+ | Win/Linux/macOS |

#### Scientific Data

| Module | Description | Dependency | Platforms |
|--------|-------------|------------|-----------|
| **IOH5part** | Read H5Part particle datasets stored in HDF5 files. Used in particle physics, astrophysics, and molecular dynamics simulations | HDF5 1.12+ | Win/Linux/macOS |
| **IOXdmf3** | Read/write XDMF3 (eXtensible Data Model and Format) files — XML metadata referencing HDF5 binary arrays. Standard for sharing large computational datasets | XDMF3 (bundled) | Win/Linux/macOS |

#### GPU / Rendering

| Module | Description | Dependency | Platforms |
|--------|-------------|------------|-----------|
| **ImagingOpenGL2** | GPU-accelerated image processing using OpenGL compute shaders. Fast convolution, FFT, and image filtering on the GPU | OpenGL 3.2+ | Win/Linux/macOS |
| **RenderingVolumeAMR** | Volume rendering for Adaptive Mesh Refinement (AMR) datasets. Renders multi-resolution volumetric data from simulations (astrophysics, combustion) | none | Win/Linux/macOS |
| **RenderingExternal** | Render VTK objects into an existing OpenGL context owned by another framework (Unity, Unreal, WPF/OpenTK, Qt). Essential for embedding VTK in C# desktop apps | none | Win/Linux/macOS |
| **RenderingWebGPU** | Rendering via WebGPU API (Dawn). Modern cross-platform graphics: Vulkan (Linux/Win), Metal (macOS), D3D12 (Win). Future primary backend replacing deprecated OpenGL on macOS | Dawn (WebGPU) | Win/Linux/macOS |

#### Analytics / ML

| Module | Description | Dependency | Platforms |
|--------|-------------|------------|-----------|
| **FiltersReebGraph** | Compute Reeb graphs for topological analysis of scalar fields. Identifies connected components, loops, and topological features in meshes | none | Win/Linux/macOS |
| **FiltersONNX** | Run ONNX neural network models inside VTK pipelines. Apply ML inference (segmentation, classification) directly on VTK datasets | ONNX Runtime 1.14+ | Win/Linux |
| **InfovisBoostGraphAlgorithms** | Graph algorithms from Boost Graph Library: shortest paths (Dijkstra), spanning trees (Prim/Kruskal), connected components, centrality, page rank. Useful for vascular tree analysis and network visualization | Boost 1.74+ | Win/Linux/macOS |

#### Serialization / Export / Misc

| Module | Description | Dependency | Platforms |
|--------|-------------|------------|-----------|
| **SerializationManager** | Serialize/deserialize VTK scene state to JSON. Save and restore complete pipeline configurations including actor properties, mapper settings, and camera state | none | Win/Linux/macOS |
| **CommonArchive** | Read/write VTK data archives (compressed bundles of multiple datasets). Useful for packaging related datasets into a single transferable file | none | Win/Linux/macOS |
| **DomainsMicroscopy** | Visualization filters for microscopy data. Handle tiled multi-resolution images, z-stacks, and microscopy-specific metadata (OpenMicroscopy/OME) | none | Win/Linux/macOS |
| **IOOMF** | Read Open Mining Format (.omf) files — the open standard for mining and geological data (drill holes, block models, surfaces) | jsoncpp (bundled) | Win/Linux/macOS |
| **WebGLExporter** | Export VTK scene to WebGL format (JSON + binary buffers) for display in browsers via three.js/vtk.js. Useful for C# server apps serving 3D content to web clients | none | Win/Linux/macOS |
| **TestingSerialization** | Test utilities for verifying serialization/deserialization round-trips of VTK objects. Extends test coverage for SerializationManager | none | Win/Linux/macOS |

### HPC Modules (6) — MPI-dependent, for cluster builds only

| Module | Description |
|--------|-------------|
| **ParallelMPI** | Base MPI communication layer for distributed-memory parallel VTK. Process groups, inter-communicator support |
| **FiltersParallelMPI** | Distributed versions of core filters: parallel decimate, parallel streamlines, ghost-cell generation across MPI ranks |
| **FiltersParallelFlowPaths** | Parallel streamline and particle tracing across distributed datasets. Essential for large-scale CFD post-processing |
| **FiltersParallelGeometry** | Parallel surface extraction and geometry filters. Distributed marching cubes, parallel threshold |
| **IOMPIImage** | Parallel image I/O using MPI-IO. Read/write large image datasets across multiple processes |
| **IOMPIParallel** | Parallel file I/O for distributed VTK datasets. MPI-based collective read/write operations |

### Excluded Modules (24) — do NOT wrap

| Module | Reason |
|--------|--------|
| RenderingOpenVR | Deprecated — replaced by OpenXR |
| IOPDAL | IOLAS reader is sufficient for point clouds |
| IOXdmf2 | Deprecated — replaced by IOXdmf3 |
| IOH5Rage | LANL-specific HDF5 format |
| IOPIO | LANL-specific particle format |
| IOTRUCTAS | LANL-specific casting simulation format |
| IOVPIC | LANL-specific plasma physics format |
| IOADIOS2 | HPC-niche (ORNL streaming I/O) |
| IOFides | HPC-niche (ADIOS2-based reader) |
| IOCatalystConduit | In-situ analysis only (Catalyst framework) |
| FiltersParallelStatistics | MPI niche |
| FiltersParallelVerdict | MPI niche |
| IOParallelLSDyna | MPI niche |
| IOParallelNetCDF | MPI niche |
| IOParallelXdmf3 | MPI niche |
| DomainsParallelChemistry | MPI niche |
| RenderingParallelLIC | MPI niche |
| FiltersOpenTURNS | Niche (uncertainty quantification, heavy OpenTURNS dep) |
| IOMySQL | Use .NET MySQL connector instead |
| IOPostgreSQL | Use .NET Npgsql instead |
| IOODBC | Use .NET System.Data.Odbc instead |
| WebAssembly/Async/Session | Emscripten/Wasm-only |
| WebCore | Python web server |

### Never Wrappable (37 modules)

EXCLUDE_WRAP (27): CSharp, Java, WrappingTools, WrappingPythonCore, WrappingJavaScript,
Python, PythonInterpreter, WebPython, GUISupportMFC, GUISupportQt, GUISupportQtQuick,
GUISupportQtSQL, ViewsQt, RenderingQt, RenderingTk, TestingCore, TestingDataModel,
TestingGenericBridge, TestingIOSQL, UtilitiesBenchmarks, DICOMParser, IOHDFTools,
octree, ParallelDIY, x11, RenderingFreeTypeFontConfig, InfovisBoost

THIRD_PARTY (4): catalyst, kwiml, metaio, vtksys

Python-only (6): CommonPython, FiltersPython, PythonContext2D, ParallelMPI4Py,
RenderingMatplotlib, WebPython
