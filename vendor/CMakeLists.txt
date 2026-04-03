# vendor/CMakeLists.txt
# Header-only libraries bundled as git submodules.
# This file is included automatically by the root CMakeLists via vendor discovery.

# ── cppzmq ────────────────────────────────────────────────────────────────────
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/cppzmq/zmq.hpp")
    add_library(cppzmq INTERFACE)
    target_include_directories(cppzmq INTERFACE
        "${CMAKE_CURRENT_SOURCE_DIR}/cppzmq")
    message(STATUS "Found bundled cppzmq")
endif()

# ── nlohmann/json ─────────────────────────────────────────────────────────────
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/json/include/nlohmann/json.hpp")
    if(NOT TARGET nlohmann_json)
        add_library(nlohmann_json INTERFACE)
        target_include_directories(nlohmann_json INTERFACE
            "${CMAKE_CURRENT_SOURCE_DIR}/json/include")
        message(STATUS "Found bundled nlohmann/json")
    endif()
endif()
