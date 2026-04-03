; Wavy Labs — NSIS Windows Installer
; Build: makensis windows.nsi
; Requires: NSIS 3.08+, EnVar plugin, AccessControl plugin

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

; ── App metadata ─────────────────────────────────────────────────────────────
!define APP_NAME        "Wavy Labs"
!define APP_VERSION     "0.15.0"
!define APP_PUBLISHER   "Wavy Labs"
!define APP_URL         "https://github.com/stroland02/Wavy-Labs-Code-Base-"
!define APP_EXE         "wavy-labs.exe"
!define INSTALL_DIR     "$PROGRAMFILES64\${APP_NAME}"
!define UNINSTALL_KEY   "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
!define VCREDIST_URL    "https://aka.ms/vs/17/release/vc_redist.x64.exe"

; ── MUI settings ─────────────────────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_ICON        "..\data\icons\wavy-labs.ico"
!define MUI_UNICON      "..\data\icons\wavy-labs.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "..\data\icons\installer-banner.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "..\data\icons\installer-header.bmp"
!define MUI_HEADERIMAGE_RIGHT
!define MUI_BGCOLOR     "0D0D14"
!define MUI_TEXTCOLOR   "E8E8F0"

Name          "${APP_NAME} ${APP_VERSION}"
OutFile       "WavyLabs-${APP_VERSION}-Setup.exe"
InstallDir    "${INSTALL_DIR}"
RequestExecutionLevel admin

; ── Finish page ───────────────────────────────────────────────────────────────
!define MUI_FINISHPAGE_TEXT "Wavy Labs has been installed.$\r$\n$\r$\nTo enable AI features, open Wavy Labs and go to Edit → Settings to configure your API keys (Anthropic, Groq, ElevenLabs).$\r$\n$\r$\nAll AI features are included — no subscription required."
!define MUI_FINISHPAGE_RUN         "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT    "Launch Wavy Labs"

; ── Pages ─────────────────────────────────────────────────────────────────────
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ── Components ────────────────────────────────────────────────────────────────
Section "Wavy Labs (required)" SecCore
    SectionIn RO
    SetOutPath "$INSTDIR"

    ; Main executable + Qt DLLs + plugins (Ninja single-config: no Release subdir)
    File /r "..\build\*.exe"
    File /r "..\build\*.dll"

    ; Plugin directories
    File /r "..\build\plugins"

    ; Data files (themes, icons, resources)
    SetOutPath "$INSTDIR\themes\wavy-dark"
    File "..\data\themes\wavy-dark\style.qss"
    SetOutPath "$INSTDIR\data"
    File /r "..\data\icons"
    SetOutPath "$INSTDIR"

    ; General MIDI soundfont — installed to AppLocalData so the app auto-detects it
    SetOutPath "$LOCALAPPDATA\WavyLabs\WavyLabs"
    File "..\wavy-installer\soundfonts\GeneralUser_GS.sf2"
    SetOutPath "$INSTDIR"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; Registry
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "DisplayName"     "${APP_NAME}"
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "DisplayVersion"  "${APP_VERSION}"
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "Publisher"       "${APP_PUBLISHER}"
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "URLInfoAbout"    "${APP_URL}"
    WriteRegStr   HKLM "${UNINSTALL_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoModify"        1
    WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoRepair"        1

    ; File association .wavy
    WriteRegStr HKCR ".wavy"                ""    "WavyLabs.Project"
    WriteRegStr HKCR "WavyLabs.Project"     ""    "Wavy Labs Project"
    WriteRegStr HKCR "WavyLabs.Project\DefaultIcon" "" "$INSTDIR\${APP_EXE},0"
    WriteRegStr HKCR "WavyLabs.Project\shell\open\command" "" '"$INSTDIR\${APP_EXE}" "%1"'

    ; Start Menu shortcut
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortcut  "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"   "$INSTDIR\uninstall.exe"
SectionEnd

Section "Python AI Backend" SecPython
    ; ── Embedded Python runtime ───────────────────────────────────────────────
    ; python-embed\ is staged by wavy-installer\prepare_installer.bat before build.
    SetOutPath "$INSTDIR\python"
    File /r "python-embed\*.*"

    ; ── AI backend source ─────────────────────────────────────────────────────
    ; Exclude dev .env files, caches, and compiled bytecode to prevent API key leakage.
    SetOutPath "$INSTDIR\wavy-ai"
    File /r /x ".env" /x ".env.*" /x "__pycache__" /x "*.pyc" /x "*.db" "..\wavy-ai\*.*"

    ; ── Write the backend launcher script ─────────────────────────────────────
    FileOpen  $0 "$INSTDIR\start-ai-backend.bat" w
    FileWrite $0 "@echo off$\r$\n"
    FileWrite $0 "cd /d $\"$INSTDIR\wavy-ai$\"$\r$\n"
    FileWrite $0 "$\"$INSTDIR\python\python.exe$\" server.py$\r$\n"
    FileClose $0

    ; ── Install Python dependencies ───────────────────────────────────────────
    ; This downloads ~500MB–2GB from PyPI (torch, transformers, demucs, etc.).
    ; A progress window is shown; internet connection is required.
    DetailPrint "Installing Python AI dependencies (this may take several minutes)..."
    ExecWait '"$INSTDIR\python\python.exe" -m pip install \
        --quiet --no-warn-script-location \
        -r "$INSTDIR\wavy-ai\requirements.txt"' $1
    ${If} $1 != 0
        MessageBox MB_ICONEXCLAMATION|MB_OK \
            "Python dependency installation failed (exit code $1).$\n$\n\
             You can retry manually by running:$\n\
             $INSTDIR\python\python.exe -m pip install -r $INSTDIR\wavy-ai\requirements.txt"
    ${EndIf}
SectionEnd

Section "Desktop Shortcut" SecDesktop
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

SectionGroup /e "GPU Support (optional)" SecGPUGroup
Section "CUDA 12.6 (NVIDIA RTX)" SecGPU
    DetailPrint "Installing CUDA-enabled PyTorch (requires NVIDIA GPU + internet)..."
    ExecWait '"$INSTDIR\python\python.exe" -m pip install torch torchaudio \
        --index-url https://download.pytorch.org/whl/cu126 \
        --quiet --no-warn-script-location' $2
    ${If} $2 != 0
        MessageBox MB_ICONEXCLAMATION|MB_OK \
            "CUDA torch installation failed (exit code $2).$\n\
             The app will work with CPU-only torch.$\n\
             Retry: $INSTDIR\python\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu126"
    ${EndIf}
SectionEnd
SectionGroupEnd

; ── Section descriptions ──────────────────────────────────────────────────────
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecCore}    "Core DAW and UI files (required)."
    !insertmacro MUI_DESCRIPTION_TEXT ${SecPython}  "Python AI backend for music generation, stem splitting, and more."
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Create a shortcut on the Desktop."
    !insertmacro MUI_DESCRIPTION_TEXT ${SecGPUGroup} "Optional: install CUDA-enabled PyTorch for GPU acceleration (stem splitting, local models)."
    !insertmacro MUI_DESCRIPTION_TEXT ${SecGPU}     "NVIDIA CUDA 12.6 torch — requires an RTX GPU and downloads ~2.5GB."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ── Uninstaller ───────────────────────────────────────────────────────────────
Section "Uninstall"
    RMDir /r "$INSTDIR"
    RMDir /r "$SMPROGRAMS\${APP_NAME}"
    Delete "$DESKTOP\${APP_NAME}.lnk"
    DeleteRegKey HKLM "${UNINSTALL_KEY}"
    DeleteRegKey HKCR ".wavy"
    DeleteRegKey HKCR "WavyLabs.Project"
SectionEnd
