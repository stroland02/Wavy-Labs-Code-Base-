@echo off
:: Bootstrap all vendor submodules required to build Wavy Labs.
:: Run once after cloning: vendor\bootstrap.bat

setlocal
set ROOT=%~dp0..

echo Initialising git submodules ...
cd /d "%ROOT%"
git submodule update --init --recursive

echo.
echo Checking Python AI backend deps ...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   WARNING: python not found. Install Python 3.10+ and re-run.
) else (
    python -m pip install --upgrade pip
    python -m pip install -r wavy-ai\requirements.txt
    echo   Python deps installed.
)

echo.
echo Checking ACE-Step ...
if not exist "%ROOT%\vendor\ACE-Step" (
    git clone https://github.com/ace-step/ACE-Step.git vendor\ACE-Step
    pip install -e vendor\ACE-Step
    echo   ACE-Step installed.
) else (
    echo   ACE-Step already present.
)

echo.
echo Checking DiffRhythm ...
if not exist "%ROOT%\vendor\DiffRhythm" (
    git clone https://github.com/ASLP-lab/DiffRhythm.git vendor\DiffRhythm
    pip install -e vendor\DiffRhythm
    echo   DiffRhythm installed.
) else (
    echo   DiffRhythm already present.
)

echo.
echo Bootstrap complete. Next steps:
echo   mkdir build ^&^& cd build
echo   cmake .. -G Ninja -DCMAKE_BUILD_TYPE=Release -DWANT_QT6=ON
echo   ninja
endlocal
