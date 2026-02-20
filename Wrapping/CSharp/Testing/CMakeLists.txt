if (NOT DOTNET_EXECUTABLE)
  return ()
endif ()

set(csharp_test_names
  CSharpDelete
  CSharpGCAndDelete
  CSharpConcurrencyGC
  CSharpBindingCoverage
  CSharpRegression)

set(csharp_test_extra_sources
  Program)

# Configure test project
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/VTK.CSharp.Tests.csproj.in"
  "${CMAKE_CURRENT_BINARY_DIR}/VTK.CSharp.Tests.csproj"
  @ONLY)

# Copy test source files
set(csharp_test_files)
foreach (test_name IN LISTS csharp_test_names csharp_test_extra_sources)
  set(output_file "${CMAKE_CURRENT_BINARY_DIR}/${test_name}.cs")
  add_custom_command(
    OUTPUT  "${output_file}"
    DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/${test_name}.cs"
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/${test_name}.cs"
            "${output_file}"
    COMMENT "Copying ${test_name}.cs to test binary directory")
  list(APPEND csharp_test_files "${output_file}")
endforeach ()

# Build the test project (produces the executable that --no-build expects)
set(_vtk_csharp_test_stamp "${CMAKE_CURRENT_BINARY_DIR}/.test_build_stamp")
add_custom_command(
  OUTPUT  "${_vtk_csharp_test_stamp}"
  DEPENDS ${csharp_test_files}
          "${CMAKE_CURRENT_BINARY_DIR}/VTK.CSharp.Tests.csproj"
  COMMAND "${DOTNET_EXECUTABLE}" build
          "${CMAKE_CURRENT_BINARY_DIR}/VTK.CSharp.Tests.csproj"
  COMMAND "${CMAKE_COMMAND}" -E touch "${_vtk_csharp_test_stamp}"
  WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
  COMMENT "Building C# test project")

add_custom_target(VTKCSharpTests ALL
  DEPENDS "${_vtk_csharp_test_stamp}")
add_dependencies(VTKCSharpTests VTKCSharpAssembly)

# Set up native library path for tests
if (WIN32)
  set(_vtk_csharp_native_path "${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_CSHARPLIBDIR}")
  set(_vtk_csharp_lib_path "${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_BINDIR}")
elseif (APPLE)
  set(_vtk_csharp_native_path "${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_CSHARPLIBDIR}")
  set(_vtk_csharp_lib_path "${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_LIBDIR}")
else ()
  set(_vtk_csharp_native_path "${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_CSHARPLIBDIR}")
  set(_vtk_csharp_lib_path "${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_LIBDIR}")
endif ()

foreach (test_name IN LISTS csharp_test_names)
  add_test(
    NAME    "vtkCSharpTests-${test_name}"
    COMMAND "${DOTNET_EXECUTABLE}" run
            --project "${CMAKE_CURRENT_BINARY_DIR}/VTK.CSharp.Tests.csproj"
            --no-build
            -- "${test_name}"
    WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
  set_property(TEST "vtkCSharpTests-${test_name}" APPEND
    PROPERTY
      REQUIRED_FILES "${CMAKE_CURRENT_BINARY_DIR}/VTK.CSharp.Tests.csproj")
  if (WIN32)
    set_property(TEST "vtkCSharpTests-${test_name}" APPEND
      PROPERTY
        ENVIRONMENT_MODIFICATION
          "PATH=path_list_prepend:${_vtk_csharp_native_path}"
          "PATH=path_list_prepend:${_vtk_csharp_lib_path}")
  elseif (APPLE)
    set_property(TEST "vtkCSharpTests-${test_name}" APPEND
      PROPERTY
        ENVIRONMENT_MODIFICATION
          "DYLD_LIBRARY_PATH=path_list_append:${_vtk_csharp_native_path}"
          "DYLD_LIBRARY_PATH=path_list_append:${_vtk_csharp_lib_path}")
  else ()
    set_property(TEST "vtkCSharpTests-${test_name}" APPEND
      PROPERTY
        ENVIRONMENT_MODIFICATION
          "LD_LIBRARY_PATH=path_list_append:${_vtk_csharp_native_path}"
          "LD_LIBRARY_PATH=path_list_append:${_vtk_csharp_lib_path}")
  endif ()
endforeach ()
