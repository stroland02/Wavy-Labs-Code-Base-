cmake_minimum_required(VERSION 3.22)

set(WAVY_UI_SOURCES
    EngineAPI/EngineAPI.cpp
    EngineAPI/LmmsEngine.cpp
    EngineAPI/StubEngine.cpp
    Shell/WavyShell.cpp
    Transport/TransportBar.cpp
    Transport/GenreConfigPopup.cpp
    Mixer/VUMeter.cpp
    Mixer/ChannelStrip.cpp
    Mixer/WavyMixerView.cpp
    Arrangement/WavyArrangementView.cpp
    Arrangement/WavyPianoRollBar.cpp
    QML/AIBackend.cpp
    QML/GenerationListModel.cpp
    QML/ChatMessageModel.cpp
    IPC/AIClient.cpp
    IPC/BackendLauncher.cpp
    ThemeManager/ThemeManager.cpp
    ThemeManager/WavyTheme.cpp
    AIPanel/AIPanel.cpp
    AIPanel/GenerationHistoryWidget.cpp
    StemSplitter/StemSplitterPanel.cpp
    PromptBar/PromptBar.cpp
    ModelManager/ModelManager.cpp
    ModelManager/ModelDownloader.cpp
    ModelManager/ModelManagerPanel.cpp
    LicenseGate/LicenseManager.cpp
    LicenseGate/LoginDialog.cpp
    LicenseGate/UsageTracker.cpp
    LicenseGate/ApiKeySettings.cpp
    Dialogs/AboutDialog.cpp
    Dialogs/OnboardingWizard.cpp
)

set(WAVY_UI_HEADERS
    EngineAPI/EngineAPI.h
    EngineAPI/LmmsEngine.h
    EngineAPI/StubEngine.h
    Shell/WavyShell.h
    Transport/TransportBar.h
    Transport/GenreConfigPopup.h
    Mixer/VUMeter.h
    Mixer/ChannelStrip.h
    Mixer/WavyMixerView.h
    Arrangement/WavyArrangementView.h
    Arrangement/WavyPianoRollBar.h
    QML/AIBackend.h
    QML/GenerationListModel.h
    QML/ChatMessageModel.h
    IPC/AIClient.h
    IPC/BackendLauncher.h
    ThemeManager/ThemeManager.h
    ThemeManager/WavyTheme.h
    AIPanel/AIPanel.h
    AIPanel/GenerationHistoryWidget.h
    StemSplitter/StemSplitterPanel.h
    PromptBar/PromptBar.h
    ModelManager/ModelManager.h
    ModelManager/ModelDownloader.h
    ModelManager/ModelManagerPanel.h
    LicenseGate/LicenseManager.h
    LicenseGate/LoginDialog.h
    LicenseGate/UsageTracker.h
    LicenseGate/ApiKeySettings.h
    Dialogs/AboutDialog.h
    Dialogs/OnboardingWizard.h
)

# WebEngineWidgets optional — only for Studio Code-to-Music Monaco editor
if(Qt6WebEngineWidgets_FOUND)
    list(APPEND WAVY_UI_SOURCES CodeToMusic/CodeEditor.cpp)
    list(APPEND WAVY_UI_HEADERS CodeToMusic/CodeEditor.h)
endif()

add_library(wavy_ui STATIC
    ${WAVY_UI_SOURCES}
    ${WAVY_UI_HEADERS}
)

target_include_directories(wavy_ui
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}
        ${CPPZMQ_INCLUDE_DIR}
        ${ZMQ_INCLUDE_DIRS}
)

target_link_libraries(wavy_ui
    PUBLIC
        Qt6::Core
        Qt6::Widgets
        Qt6::Gui
        Qt6::Network
        Qt6::Svg
        Qt6::SvgWidgets
        Qt6::Sql
        Qt6::Xml
        Qt6::Quick
        Qt6::QuickWidgets
        Qt6::QuickControls2
        nlohmann_json
        ${ZMQ_LIBRARIES}
)

if(Qt6WebEngineWidgets_FOUND)
    target_link_libraries(wavy_ui PUBLIC Qt6::WebEngineWidgets)
    target_compile_definitions(wavy_ui PUBLIC WAVY_WEBENGINE)
endif()

target_compile_definitions(wavy_ui PUBLIC
    WAVY_AI_HOST="127.0.0.1"
    WAVY_AI_PORT=5555
)

# ── Optional: OS keychain support via qt6keychain ────────────────────────────
# Enable with:  cmake -DWAVY_USE_KEYCHAIN=ON ..
option(WAVY_USE_KEYCHAIN "Store license key in OS credential store (requires qtkeychain)" OFF)

if(WAVY_USE_KEYCHAIN)
    find_package(Qt6Keychain QUIET)
    if(NOT Qt6Keychain_FOUND)
        # Try the older package name used by some distros
        find_package(qtkeychain QUIET)
        if(qtkeychain_FOUND)
            set(Qt6Keychain_FOUND TRUE)
            set(Qt6Keychain_LIBRARIES qt5keychain)  # runtime lib name varies
        endif()
    endif()

    if(Qt6Keychain_FOUND)
        target_compile_definitions(wavy_ui PUBLIC WAVY_USE_KEYCHAIN)
        target_link_libraries(wavy_ui PUBLIC ${Qt6Keychain_LIBRARIES})
        message(STATUS "qtkeychain found — OS keychain storage enabled")
    else()
        message(WARNING "WAVY_USE_KEYCHAIN=ON but qtkeychain not found; "
                        "falling back to QSettings storage")
    endif()
endif()
