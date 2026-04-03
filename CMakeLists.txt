cmake_minimum_required(VERSION 3.22)
project(WavyLabs VERSION 1.0.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── MSVC: parallel file compilation within each target ───────────────────────
if(MSVC)
    add_compile_options(/MP)
endif()
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

# ── Options ──────────────────────────────────────────────────────────────────
option(WAVY_BUILD_LMMS_CORE  "Build the bundled LMMS core submodule"  ON)
option(WAVY_BUILD_INSTALLER  "Generate installer targets"              OFF)
option(WAVY_WANT_QT6         "Force Qt6 (required)"                   ON)

# ── Qt6 ───────────────────────────────────────────────────────────────────────
find_package(Qt6 REQUIRED COMPONENTS
    Core Widgets Gui Network Svg SvgWidgets Sql Xml
    Quick QuickWidgets QuickControls2)

# WebEngineWidgets is optional — required only for Studio tier Code-to-Music panel
find_package(Qt6 QUIET OPTIONAL_COMPONENTS WebEngineWidgets)

# ShaderTools is optional — required only to (re-)compile data/shaders/*.frag → .qsb
# If not installed, the pre-compiled .qsb files (when present) are used as-is via QRC.
find_package(Qt6 QUIET OPTIONAL_COMPONENTS ShaderTools)
if(Qt6ShaderTools_FOUND)
    message(STATUS "Qt6ShaderTools found — GLSL shader compilation enabled")
else()
    message(STATUS "Qt6ShaderTools NOT found — using pre-compiled .qsb assets if available")
endif()
if(Qt6WebEngineWidgets_FOUND)
    message(STATUS "Qt6WebEngineWidgets found — Code-to-Music Monaco editor enabled")
else()
    message(STATUS "Qt6WebEngineWidgets NOT found — Code-to-Music Monaco editor disabled")
endif()

# ── ZeroMQ ───────────────────────────────────────────────────────────────────
# Use IMPORTED_TARGET so cmake creates a target with the full library path;
# bare variable names from pkg_check_modules omit the lib dir on Windows.
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
    pkg_check_modules(ZMQ IMPORTED_TARGET libzmq)
    if(ZMQ_FOUND)
        set(ZMQ_LIBRARIES    PkgConfig::ZMQ)
        set(ZMQ_INCLUDE_DIRS "")   # already handled by PkgConfig::ZMQ target
    endif()
endif()
if(NOT ZMQ_FOUND)
    find_library(ZMQ_LIB NAMES libzmq zmq
        HINTS "${CMAKE_PREFIX_PATH}"
              "C:/tmp/vcpkg/installed/x64-windows/lib"
              "C:/tmp/vcpkg/installed/x64-windows/debug/lib")
    if(NOT ZMQ_LIB)
        message(FATAL_ERROR "ZeroMQ library not found")
    endif()
    add_library(ZMQ::zmq UNKNOWN IMPORTED)
    set_target_properties(ZMQ::zmq PROPERTIES IMPORTED_LOCATION "${ZMQ_LIB}")
    set(ZMQ_LIBRARIES    ZMQ::zmq)
    set(ZMQ_INCLUDE_DIRS "")
endif()

# cppzmq header-only wrapper (bundled or via find_package)
find_path(CPPZMQ_INCLUDE_DIR zmq.hpp
    HINTS ${CMAKE_CURRENT_SOURCE_DIR}/vendor/cppzmq)

# ── nlohmann/json (header-only) ───────────────────────────────────────────────
find_package(nlohmann_json QUIET)
if(NOT nlohmann_json_FOUND)
    find_path(NLOHMANN_JSON_INCLUDE_DIR nlohmann/json.hpp
        HINTS ${CMAKE_CURRENT_SOURCE_DIR}/vendor/json/include)
    if(NLOHMANN_JSON_INCLUDE_DIR)
        add_library(nlohmann_json INTERFACE)
        target_include_directories(nlohmann_json INTERFACE ${NLOHMANN_JSON_INCLUDE_DIR})
    else()
        message(FATAL_ERROR "nlohmann/json not found. "
            "Run: git submodule add https://github.com/nlohmann/json vendor/json")
    endif()
endif()

# ── Vendor (header-only: cppzmq, nlohmann/json) ───────────────────────────────
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/vendor/CMakeLists.txt")
    add_subdirectory(vendor)
endif()

# ── wavy-ui library ───────────────────────────────────────────────────────────
add_subdirectory(wavy-ui)

# ── LMMS core submodule ───────────────────────────────────────────────────────
if(WAVY_BUILD_LMMS_CORE)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/lmms-core/CMakeLists.txt")
        set(WANT_QT6 ON CACHE BOOL "" FORCE)
        # LMMS uses CMAKE_SOURCE_DIR (not CMAKE_CURRENT_SOURCE_DIR) throughout,
        # which breaks when included as a subdirectory.
        # Prepend the correct path here so INCLUDE(PluginList) etc. resolve.
        list(INSERT CMAKE_MODULE_PATH 0
            "${CMAKE_CURRENT_SOURCE_DIR}/lmms-core/cmake/modules")
        # LMMS's src/CMakeLists.txt uses ${CMAKE_SOURCE_DIR} for include dirs, but
        # since CMAKE_SOURCE_DIR = our root (not lmms-core/), the paths resolve wrong.
        # Add the real LMMS dirs globally so all lmms headers are found.
        include_directories("${CMAKE_CURRENT_SOURCE_DIR}/lmms-core")          # for #include "plugins/Foo/Foo.h"
        include_directories("${CMAKE_CURRENT_SOURCE_DIR}/lmms-core/include")  # for #include "InstrumentTrack.h"
        include_directories("${CMAKE_CURRENT_SOURCE_DIR}/lmms-core/src")      # for #include "gui/MainWindow.h"
        # LMMS's only .ui file (about_dialog.ui) is #included from a public header
        # (AboutDialog.h), not from a .cpp source, so AUTOUIC never triggers.
        # Generate ui_about_dialog.h at configure time using execute_process so the
        # file exists before any compilation step. Output goes to CMAKE_BINARY_DIR
        # which is already in lmmsobjs's include path.
        # Locate uic from the same Qt installation we're building against
        get_target_property(_qt6_core_loc Qt6::Core LOCATION)
        get_filename_component(_qt6_bin_dir "${_qt6_core_loc}" DIRECTORY)
        find_program(QT6_UIC_EXE NAMES uic uic6
            HINTS "${_qt6_bin_dir}"
                  "${Qt6Core_DIR}/../../../bin"
                  "${Qt6Core_DIR}/../../../libexec")
        file(GLOB_RECURSE LMMS_UI_FILES
            "${CMAKE_CURRENT_SOURCE_DIR}/lmms-core/src/*.ui")
        foreach(_ui_file ${LMMS_UI_FILES})
            get_filename_component(_ui_base ${_ui_file} NAME_WE)
            set(_ui_out "${CMAKE_BINARY_DIR}/ui_${_ui_base}.h")
            if(QT6_UIC_EXE AND NOT EXISTS "${_ui_out}")
                execute_process(
                    COMMAND "${QT6_UIC_EXE}" -o "${_ui_out}" "${_ui_file}"
                    RESULT_VARIABLE _uic_result)
                if(_uic_result EQUAL 0)
                    message(STATUS "Pre-generated ${_ui_out}")
                else()
                    message(WARNING "uic failed for ${_ui_file} (${_uic_result})")
                endif()
            endif()
        endforeach()
        include_directories("${CMAKE_BINARY_DIR}")
        # On Windows, lmms-core/CMakeLists.txt globs headers via
        # ${CMAKE_SOURCE_DIR}/include/ (= WL root), so AUTOMOC needs an
        # include/ junction pointing at lmms-core/include/ to exist before
        # configure time.  Create it automatically if missing.
        if(WIN32)
            set(_inc_junction "${CMAKE_CURRENT_SOURCE_DIR}/include")
            set(_inc_target   "${CMAKE_CURRENT_SOURCE_DIR}/lmms-core/include")
            if(NOT EXISTS "${_inc_junction}")
                execute_process(
                    COMMAND cmd /c mklink /J "${_inc_junction}" "${_inc_target}"
                    RESULT_VARIABLE _junc_rc
                    OUTPUT_QUIET ERROR_QUIET)
                if(_junc_rc EQUAL 0)
                    message(STATUS "Created include junction -> lmms-core/include")
                else()
                    message(WARNING "Could not create include junction (rc=${_junc_rc}). "
                        "Run: mklink /J \"${_inc_junction}\" \"${_inc_target}\"")
                endif()
            endif()
        endif()
        add_subdirectory(lmms-core)
        # ringbuffer_export.h.in (inside lmms-core/src/3rdparty) is generated with:
        #   #include "${CMAKE_BINARY_DIR}/src/lmms_export.h"
        # but GENERATE_EXPORT_HEADER puts the real file at:
        #   ${CMAKE_BINARY_DIR}/lmms-core/src/lmms_export.h
        # Create a forwarding stub at the expected path so ringbuffer can compile.
        file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/src")
        file(WRITE "${CMAKE_BINARY_DIR}/src/lmms_export.h"
            "#pragma once\n#include \"${CMAKE_BINARY_DIR}/lmms-core/src/lmms_export.h\"\n")
    else()
        message(WARNING
            "lmms-core submodule not initialised.\n"
            "Run: git submodule update --init --recursive\n"
            "Or:  git clone https://github.com/LMMS/lmms lmms-core")
    endif()
endif()

# ── Qt resources ─────────────────────────────────────────────────────────────
qt_add_resources(WAVY_RESOURCES data/resources.qrc)

# ── wavy-labs executable (standalone launcher / dev harness) ──────────────────
add_executable(wavy-labs
    src/main.cpp
    ${WAVY_RESOURCES}
)
# Compile GLSL shaders → QSB when ShaderTools is available
if(Qt6ShaderTools_FOUND)
    qt6_add_shaders(wavy-labs "wavy_shaders"
        BATCHABLE
        PRECOMPILE
        OPTIMIZED
        PREFIX "/wavy/shaders"
        FILES
            "data/shaders/wavy_bg.frag"
    )
endif()

target_link_libraries(wavy-labs PRIVATE
    wavy_ui
    Qt6::Core
    Qt6::Widgets
    Qt6::Gui
    Qt6::Network
    Qt6::Quick
    Qt6::QuickWidgets
    Qt6::QuickControls2
)
if(WIN32)
    target_link_libraries(wavy-labs PRIVATE winmm)
endif()
target_compile_definitions(wavy-labs PRIVATE
    WAVY_VERSION="${PROJECT_VERSION}"
    WAVY_APP_NAME="Wavy Labs"
)

# When lmms-core is present:
#   - wavy_ui gets the WAVY_LMMS_CORE define and LMMS include paths
#   - wavy-labs links against lmmsobjs (all LMMS code except lmms-core/src/core/main.cpp)
#     so that src/main.cpp can call GuiApplication, ConfigManager, Engine directly.
if(WAVY_BUILD_LMMS_CORE AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/lmms-core/CMakeLists.txt")
    target_compile_definitions(wavy_ui PUBLIC WAVY_LMMS_CORE LMMS_STATIC_DEFINE)
    target_include_directories(wavy_ui PUBLIC
        "${CMAKE_CURRENT_SOURCE_DIR}/lmms-core/include"
        "${CMAKE_CURRENT_SOURCE_DIR}/lmms-core/src"
        "${CMAKE_BINARY_DIR}"           # lmmsconfig.h, lmmsversion.h (generated at CMAKE_BINARY_DIR)
        "${CMAKE_BINARY_DIR}/lmms-core/src"  # lmms_export.h
    )
    # Link wavy-labs against lmmsobjs so LMMS symbols are available in our main()
    target_link_libraries(wavy-labs PRIVATE lmmsobjs)
    # ringbuffer is an OBJECT lib linked into lmmsobjs but not auto-propagated;
    # link it explicitly so Lv2Worker and friends resolve their symbols.
    target_link_libraries(wavy-labs PRIVATE ringbuffer)
    # wavy-labs also needs the same WAVY_LMMS_CORE define for the #ifdef in src/main.cpp
    target_compile_definitions(wavy-labs PRIVATE WAVY_LMMS_CORE)
    # LMMS_STATIC_DEFINE disables __declspec(dllimport) in lmms_export.h so symbols
    # resolve against the OBJECT files we link directly (not a separate DLL).
    target_compile_definitions(wavy-labs PRIVATE LMMS_STATIC_DEFINE)
    # LMMS's ADD_DEFINITIONS(-DNOMINMAX) is directory-scoped to lmms-core and does
    # not propagate to wavy-labs/wavy_ui. Add it here so std::min/max in LMMS headers
    # (SampleFrame.h, TimePos.h, etc.) don't clash with Windows.h min/max macros.
    target_compile_definitions(wavy-labs PRIVATE NOMINMAX)
    target_compile_definitions(wavy_ui  PUBLIC  NOMINMAX)
    # Export symbols so dynamically-loaded LMMS plugins can resolve them at runtime
    set_target_properties(wavy-labs PROPERTIES ENABLE_EXPORTS ON)
    # ── Plugin import fix ──────────────────────────────────────────────────────
    # LMMS plugins are built with `target_link_libraries(plugin lmms ...)` which
    # makes them import symbols from "lmms.exe".  If our process is named
    # "wavy-labs.exe", Windows loads lmms.exe as a SEPARATE module → duplicate
    # globals → heap corruption → crash ~8 s after createNewProject().
    # Fix: rename our output to "lmms" so the running process IS lmms.exe,
    # and move the original LMMS standalone exe out of the way.
    set_target_properties(wavy-labs PROPERTIES OUTPUT_NAME "lmms")
    set_target_properties(lmms PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lmms-standalone"
        # Plugins link against the `lmms` CMake target; ENABLE_EXPORTS generates
        # lmms.lib so the link succeeds. At runtime our wavy-labs.exe IS lmms.exe
        # (same OUTPUT_NAME) so plugin symbol resolution works correctly.
        ENABLE_EXPORTS ON)

    # ── Build plugins as part of wavy-labs ----------------------------------
    # do_build_lmms.bat uses --target wavy-labs so plugin targets are skipped
    # unless we explicitly add them as dependencies of wavy-labs here.
    get_property(_wavy_plugins GLOBAL PROPERTY PLUGINS_BUILT)
    if(_wavy_plugins)
        add_dependencies(wavy-labs ${_wavy_plugins})
    endif()
    if(WIN32)
        set_target_properties(wavy-labs PROPERTIES WIN32_EXECUTABLE
            $<NOT:$<CONFIG:Debug>>)
    endif()

    # ── Post-build: deploy plugins + Qt DLLs + CRT ───────────────────────────
    # Plugins build to build/lmms-core/plugins/ but PluginFactory looks in
    # {exe_dir}/plugins/ at runtime.  Copy them + run windeployqt after build.
    find_program(_WINDEPLOYQT windeployqt6 windeployqt
        HINTS "${_qt6_bin_dir}"
              "${Qt6Core_DIR}/../../../bin")
    add_custom_command(TARGET wavy-labs POST_BUILD
        # 1. Create plugins/ next to exe and copy all plugin DLLs/SOs there
        COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_BINARY_DIR}/plugins"
        COMMAND ${CMAKE_COMMAND}
            -DSRC_DIR="${CMAKE_BINARY_DIR}/lmms-core/plugins"
            -DDST_DIR="${CMAKE_BINARY_DIR}/plugins"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/scripts/CopyPlugins.cmake"
        COMMENT "Deploying LMMS plugins to build/plugins/"
    )
    if(_WINDEPLOYQT)
        # 2. Deploy Qt runtime DLLs + QML modules next to the exe
        add_custom_command(TARGET wavy-labs POST_BUILD
            COMMAND "${_WINDEPLOYQT}" --no-translations --no-compiler-runtime
                --qmldir "${CMAKE_CURRENT_SOURCE_DIR}/data/qml"
                "$<TARGET_FILE:wavy-labs>"
            COMMENT "Running windeployqt6..."
        )
    endif()
endif()

# Optional: embed version info on Windows
if(WIN32)
    configure_file(
        "${CMAKE_CURRENT_SOURCE_DIR}/wavy-installer/version.rc.in"
        "${CMAKE_CURRENT_BINARY_DIR}/version.rc"
        @ONLY
    )
    target_sources(wavy-labs PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/version.rc")
endif()

# ── Installer ─────────────────────────────────────────────────────────────────
if(WAVY_BUILD_INSTALLER)
    add_subdirectory(wavy-installer)
endif()

# ── Install rules ────────────────────────────────────────────────────────────
install(TARGETS wavy-labs RUNTIME DESTINATION bin)
install(DIRECTORY data/ DESTINATION share/wavy-labs)
