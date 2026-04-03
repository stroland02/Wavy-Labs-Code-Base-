cmake_minimum_required(VERSION 3.22)
project(wavy-installer NONE)

# ── Version info ─────────────────────────────────────────────────────────────
set(WAVY_VERSION_MAJOR 1)
set(WAVY_VERSION_MINOR 0)
set(WAVY_VERSION_PATCH 0)
set(WAVY_VERSION "${WAVY_VERSION_MAJOR}.${WAVY_VERSION_MINOR}.${WAVY_VERSION_PATCH}")

configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/version.rc.in"
    "${CMAKE_CURRENT_BINARY_DIR}/version.rc"
    @ONLY
)

# ── Platform-specific installer targets ──────────────────────────────────────

if(WIN32)
    # Windows — NSIS installer
    find_program(MAKENSIS_EXECUTABLE makensis
        HINTS "C:/Program Files (x86)/NSIS" "C:/Program Files/NSIS"
        DOC "NSIS compiler")

    if(MAKENSIS_EXECUTABLE)
        add_custom_target(installer
            COMMAND "${MAKENSIS_EXECUTABLE}"
                /DVERSION=${WAVY_VERSION}
                /DOUT_DIR=${CMAKE_BINARY_DIR}
                "${CMAKE_CURRENT_SOURCE_DIR}/windows.nsi"
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
            COMMENT "Building Windows NSIS installer (v${WAVY_VERSION})"
            VERBATIM
        )
        message(STATUS "Installer target: makensis found at ${MAKENSIS_EXECUTABLE}")
    else()
        message(STATUS "makensis not found — 'installer' target unavailable on this machine")
    endif()

elseif(APPLE)
    # macOS — DMG via shell script
    find_program(BASH_EXECUTABLE bash)
    if(BASH_EXECUTABLE)
        add_custom_target(installer
            COMMAND "${BASH_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/macos.sh"
                ${WAVY_VERSION}
                "${CMAKE_BINARY_DIR}"
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
            COMMENT "Building macOS DMG (v${WAVY_VERSION})"
            VERBATIM
        )
    endif()

elseif(UNIX)
    # Linux — AppImage via shell script
    find_program(BASH_EXECUTABLE bash)
    if(BASH_EXECUTABLE)
        add_custom_target(installer
            COMMAND "${BASH_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/linux-appimage.sh"
                ${WAVY_VERSION}
                "${CMAKE_BINARY_DIR}"
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
            COMMENT "Building Linux AppImage (v${WAVY_VERSION})"
            VERBATIM
        )
    endif()
endif()

# ── Install rule: copy installer artifacts to CMAKE_INSTALL_PREFIX ────────────
install(
    DIRECTORY "${CMAKE_BINARY_DIR}/"
    DESTINATION installers
    FILES_MATCHING
        PATTERN "*.exe"
        PATTERN "*.dmg"
        PATTERN "*.AppImage"
)
