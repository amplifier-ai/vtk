cmake_minimum_required(VERSION 3.12...3.21)
project(EmbeddedDependency LANGUAGES C)
add_library(vendor SHARED vendor.c)
install(TARGETS vendor
  RUNTIME DESTINATION bin LIBRARY DESTINATION lib ARCHIVE DESTINATION lib)
