@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM prepare_installer.bat — stage embedded Python 3.12 for NSIS bundling
REM
REM Run this ONCE before building the installer.
REM Output: wavy-installer\python-embed\  (ready for NSIS File /r)
REM
REM Requirements: PowerShell 5+, internet connection
REM ─────────────────────────────────────────────────────────────────────────────

setlocal EnableDelayedExpansion

set PY_VER=3.12.10
set PY_ARCH=amd64
set PY_ZIP=python-%PY_VER%-embed-%PY_ARCH%.zip
set PY_URL=https://www.python.org/ftp/python/%PY_VER%/%PY_ZIP%
set PY_DIR=%~dp0python-embed
set GET_PIP_URL=https://bootstrap.pypa.io/get-pip.py

echo [prepare_installer] Python version: %PY_VER% (%PY_ARCH%)
echo [prepare_installer] Output dir:     %PY_DIR%
echo.

REM ── Clean previous build ─────────────────────────────────────────────────────
if exist "%PY_DIR%" (
    echo Removing previous python-embed ...
    rmdir /s /q "%PY_DIR%"
)
mkdir "%PY_DIR%"

REM ── Download embeddable Python ────────────────────────────────────────────────
if not exist "%~dp0%PY_ZIP%" (
    echo Downloading %PY_ZIP% ...
    powershell -Command "Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%~dp0%PY_ZIP%' -UseBasicParsing"
    if errorlevel 1 (
        echo ERROR: Failed to download Python embeddable package.
        exit /b 1
    )
) else (
    echo Found cached %PY_ZIP%
)

REM ── Extract ───────────────────────────────────────────────────────────────────
echo Extracting to %PY_DIR% ...
powershell -Command "Expand-Archive -Path '%~dp0%PY_ZIP%' -DestinationPath '%PY_DIR%' -Force"
if errorlevel 1 (
    echo ERROR: Extraction failed.
    exit /b 1
)

REM ── Enable site-packages (required for pip to work) ──────────────────────────
REM The embeddable zip ships with "import site" commented out in python3xx._pth
for %%F in ("%PY_DIR%\python3*._pth") do (
    echo Patching %%~nxF to enable site-packages ...
    powershell -Command "(Get-Content '%%F') -replace '#import site','import site' | Set-Content '%%F'"
)

REM ── Bootstrap pip ────────────────────────────────────────────────────────────
echo Downloading get-pip.py ...
powershell -Command "Invoke-WebRequest -Uri '%GET_PIP_URL%' -OutFile '%PY_DIR%\get-pip.py' -UseBasicParsing"
if errorlevel 1 (
    echo ERROR: Failed to download get-pip.py.
    exit /b 1
)

echo Installing pip into embedded Python ...
"%PY_DIR%\python.exe" "%PY_DIR%\get-pip.py" --no-warn-script-location
if errorlevel 1 (
    echo ERROR: pip bootstrap failed.
    exit /b 1
)
del "%PY_DIR%\get-pip.py"

REM ── Verify ───────────────────────────────────────────────────────────────────
echo Verifying pip installation ...
"%PY_DIR%\python.exe" -m pip --version
if errorlevel 1 (
    echo ERROR: pip not working in embedded Python.
    exit /b 1
)

REM ── Stage General MIDI soundfont ─────────────────────────────────────────────
echo Staging GeneralUser GS soundfont...
if not exist "%~dp0soundfonts" mkdir "%~dp0soundfonts"
copy /y "%LOCALAPPDATA%\WavyLabs\WavyLabs\GeneralUser_GS.sf2" "%~dp0soundfonts\GeneralUser_GS.sf2"
if errorlevel 1 (
    echo WARNING: Could not stage soundfont from %LOCALAPPDATA%\WavyLabs\WavyLabs\GeneralUser_GS.sf2
    echo          Download GeneralUser GS.sf2 and place it there before running this script.
)

echo.
echo [prepare_installer] Done! python-embed\ is ready for NSIS bundling.
echo [prepare_installer] Size:
powershell -Command "(Get-ChildItem '%PY_DIR%' -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB | ForEach-Object { '{0:N1} MB' -f $_ }"
echo.
endlocal
