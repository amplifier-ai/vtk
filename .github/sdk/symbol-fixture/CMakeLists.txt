# Match VTK's policy range so the preload must enable CMP0141 before project().
cmake_minimum_required(VERSION 3.12...3.21)
project(NativeSymbolFixture LANGUAGES C CXX)

set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")

add_library(owned SHARED owned.c owned.cxx)
add_library(fixture_static STATIC static.c)
add_subdirectory(third-party)

configure_file(wrapper.cxx.in generated/wrapper.cxx @ONLY)
add_library(wrapper SHARED "${CMAKE_CURRENT_BINARY_DIR}/generated/wrapper.cxx")
add_library(helper SHARED helper.cxx)
target_link_libraries(wrapper PRIVATE owned)
target_link_libraries(helper PRIVATE owned)
set_target_properties(wrapper PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib/csharp"
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib/csharp")
set_target_properties(helper PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib/csharp")

add_executable(installed_tool tool.c)
add_executable(uninstalled_test tool.c)
target_link_libraries(installed_tool PRIVATE owned)
target_link_libraries(uninstalled_test PRIVATE owned)
install(TARGETS owned fixture_static installed_tool
  RUNTIME DESTINATION bin LIBRARY DESTINATION lib ARCHIVE DESTINATION lib)
install(TARGETS wrapper helper
  RUNTIME DESTINATION lib/csharp LIBRARY DESTINATION lib/csharp ARCHIVE DESTINATION lib)

foreach(target owned wrapper helper vendor installed_tool)
  file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/artifacts/${target}.path"
    CONTENT "$<TARGET_FILE:${target}>\n")
  if(MSVC)
    file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/artifacts/${target}.pdb-path"
      CONTENT "$<TARGET_PDB_FILE:${target}>\n")
  endif()
endforeach()
