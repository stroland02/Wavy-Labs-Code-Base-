@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  setup_carla.bat — Downloads Carla portable and extracts files needed for
REM  VST3/LV2/CLAP plugin hosting inside Wavy Labs.
REM
REM  Usage: scripts\setup_carla.bat
REM  Result: deps\carla\libcarla_native-plugin.dll + deps\carla\resources\
REM ─────────────────────────────────────────────────────────────────────────────

setlocal enabledelayedexpansion

set "CARLA_VERSION=2.5.10"
set "CARLA_ZIP=Carla-%CARLA_VERSION%-win64.zip"
set "CARLA_URL=https://github.com/falkTX/Carla/releases/download/v%CARLA_VERSION%/%CARLA_ZIP%"
REM Resolve PROJECT_DIR to an absolute path (no trailing ..)
pushd "%~dp0.."
set "PROJECT_DIR=%CD%"
popd
set "DEPS_DIR=%PROJECT_DIR%\deps\carla"
set "TEMP_DIR=%TEMP%\carla_setup"

echo.
echo ===== Wavy Labs — Carla VST3 Setup =====
echo.
echo Carla version : %CARLA_VERSION%
echo Target        : %DEPS_DIR%
echo.

REM Check if already set up
if exist "%DEPS_DIR%\libcarla_native-plugin.dll" (
    echo [OK] Carla library already present at %DEPS_DIR%
    echo      Delete deps\carla\ and re-run to force update.
    goto :done
)

REM Create directories
if not exist "%DEPS_DIR%" mkdir "%DEPS_DIR%"
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"

REM Download
echo [1/3] Downloading %CARLA_ZIP% ...
curl -L -o "%TEMP_DIR%\%CARLA_ZIP%" "%CARLA_URL%"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Download failed. Check your internet connection.
    goto :fail
)

REM Extract
echo [2/3] Extracting ...
powershell -Command "Expand-Archive -Force '%TEMP_DIR%\%CARLA_ZIP%' '%TEMP_DIR%\carla_extracted'"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Extraction failed.
    goto :fail
)

REM Find and copy the DLL
echo [3/3] Copying files to deps\carla\ ...
set "FOUND_DLL="

REM The portable zip extracts to Carla-<version>\ or Carla\ — search for the DLL
for /r "%TEMP_DIR%\carla_extracted" %%F in (libcarla_native-plugin.dll) do (
    if not defined FOUND_DLL (
        set "FOUND_DLL=%%F"
        set "CARLA_ROOT=%%~dpF"
        copy /Y "%%F" "%DEPS_DIR%\" >nul
        echo   Copied libcarla_native-plugin.dll
    )
)

if not defined FOUND_DLL (
    echo ERROR: libcarla_native-plugin.dll not found in the archive.
    echo        The Carla portable archive structure may have changed.
    goto :fail
)

REM Copy resources directory
if exist "!CARLA_ROOT!resources\" (
    if not exist "%DEPS_DIR%\resources\" mkdir "%DEPS_DIR%\resources\"
    xcopy /Y /E /Q "!CARLA_ROOT!resources\" "%DEPS_DIR%\resources\" >nul
    echo   Copied resources\ directory
)

REM Cleanup temp files
rd /s /q "%TEMP_DIR%" 2>nul

echo.
echo ===== Setup Complete =====
echo.
echo Carla library installed to: %DEPS_DIR%
echo.
echo Next steps:
echo   1. Rebuild: do_build_lmms.bat
echo   2. Launch lmms.exe
echo   3. Add "Carla Rack" or "Carla Patchbay" instrument to load VST3 plugins
echo.
goto :done

:fail
echo.
echo Setup failed. See errors above.
rd /s /q "%TEMP_DIR%" 2>nul
exit /b 1

:done
endlocal
exit /b 0
