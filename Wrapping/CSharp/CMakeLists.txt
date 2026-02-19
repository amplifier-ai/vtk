set(CMAKE_INSTALL_CSHARPLIBDIR ""
  CACHE STRING "C# native libraries (LIBDIR/csharp)")
mark_as_advanced(CMAKE_INSTALL_CSHARPLIBDIR)

if (NOT CMAKE_INSTALL_CSHARPLIBDIR)
  set(CMAKE_INSTALL_CSHARPLIBDIR
    "${CMAKE_INSTALL_LIBDIR}/csharp")
endif ()
if (IS_ABSOLUTE "${CMAKE_INSTALL_CSHARPLIBDIR}")
  message(FATAL_ERROR
    "The `CMAKE_INSTALL_CSHARPLIBDIR` must not be an absolute path.")
endif ()

include(vtkModuleWrapCSharp)
vtk_module_wrap_csharp(
  CSHARP_OUTPUT     "${CMAKE_CURRENT_BINARY_DIR}/generated"
  MODULES           ${vtk_modules}
  WRAPPED_MODULES   vtk_csharp_wrapped_modules
  UTILITY_TARGET    "VTK::vtkbuild"
  LIBRARY_DESTINATION "${CMAKE_INSTALL_LIBDIR}"
  NATIVELIB_DESTINATION  "${CMAKE_INSTALL_CSHARPLIBDIR}")

# Collect all generated .cs files from wrapped modules
set(vtk_csharp_all_cs_files)
foreach (_vtk_csharp_module IN LISTS vtk_csharp_wrapped_modules)
  get_property(_vtk_csharp_library_name GLOBAL
    PROPERTY "_vtk_module_${_vtk_csharp_module}_library_name")
  get_property(_vtk_module_cs_files
    TARGET    "${_vtk_csharp_library_name}CSharp"
    PROPERTY  "_vtk_module_csharp_files")
  list(APPEND vtk_csharp_all_cs_files
    ${_vtk_module_cs_files})
endforeach ()

# Copy hand-written runtime .cs files to the build directory
set(csharp_runtime_sources
  vtk/vtkObjectBase.cs
  vtk/VtkObjectManager.cs
  vtk/VtkGarbageCollector.cs
  vtk/VtkReferenceInformation.cs)

set(csharp_runtime_input_files)
foreach (cs_file IN LISTS csharp_runtime_sources)
  set(output_file "${CMAKE_CURRENT_BINARY_DIR}/runtime/${cs_file}")
  get_filename_component(output_dir "${output_file}" DIRECTORY)
  file(MAKE_DIRECTORY "${output_dir}")
  add_custom_command(
    OUTPUT  "${output_file}"
    DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/${cs_file}"
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/${cs_file}"
            "${output_file}"
    COMMENT "Copying ${cs_file} to the binary directory")
  list(APPEND csharp_runtime_input_files
    "${output_file}")
endforeach ()

# Configure VtkNativeLibrary.cs
set(VTK_CSHARP_NATIVE_LIB_DIR "${CMAKE_INSTALL_CSHARPLIBDIR}")
set(VTK_CSHARP_VERSION_SUFFIX "-${VTK_MAJOR_VERSION}.${VTK_MINOR_VERSION}")
set(VTK_CSHARP_BUILD_LIB_DIR "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}")
set(VTK_CSHARP_BUILD_NATIVELIB_DIR "${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_CSHARPLIBDIR}")
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/vtk/VtkNativeLibrary.cs.in"
  "${CMAKE_CURRENT_BINARY_DIR}/runtime/vtk/VtkNativeLibrary.cs"
  @ONLY)
list(APPEND csharp_runtime_input_files
  "${CMAKE_CURRENT_BINARY_DIR}/runtime/vtk/VtkNativeLibrary.cs")

# Generate .csproj file
set(VTK_CSHARP_PROJECT_DIR "${CMAKE_CURRENT_BINARY_DIR}")
file(MAKE_DIRECTORY "${VTK_CSHARP_PROJECT_DIR}")
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/VTK.CSharp.csproj.in"
  "${VTK_CSHARP_PROJECT_DIR}/VTK.CSharp.csproj"
  @ONLY)

# Custom target to build the C# assembly via dotnet
find_program(DOTNET_EXECUTABLE dotnet)
if (DOTNET_EXECUTABLE)
  # Create a target for all C# sources
  add_custom_target(vtk_csharp_sources ALL
    DEPENDS
      ${vtk_csharp_all_cs_files}
      ${csharp_runtime_input_files})

  add_custom_target(VTKCSharpAssembly ALL
    COMMAND "${DOTNET_EXECUTABLE}" build
            "${VTK_CSHARP_PROJECT_DIR}/VTK.CSharp.csproj"
            -c $<CONFIG>
            -o "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
    WORKING_DIRECTORY "${VTK_CSHARP_PROJECT_DIR}"
    COMMENT "Building VTK C# assembly"
    DEPENDS vtk_csharp_sources)

  if (CMAKE_INSTALL_CSHARPLIBDIR)
    install(
      FILES "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}/VTK.CSharp.dll"
      DESTINATION "${CMAKE_INSTALL_CSHARPLIBDIR}"
      COMPONENT "csharp"
      OPTIONAL)
  endif ()
else ()
  message(WARNING
    "dotnet executable not found. C# assembly will not be built. "
    "Install .NET SDK to enable C# assembly generation.")
endif ()

if (VTK_BUILD_TESTING)
  add_subdirectory(Testing)
endif ()
