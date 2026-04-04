@echo off
echo Installing LMMS required dependencies via vcpkg...
set VCPKG=C:\tmp\vcpkg\vcpkg.exe

echo.
echo [1/3] Installing libsndfile...
"%VCPKG%" install libsndfile:x64-windows
if %ERRORLEVEL% NEQ 0 echo WARNING: libsndfile install failed with code %ERRORLEVEL%

echo.
echo [2/3] Installing fftw3...
"%VCPKG%" install fftw3:x64-windows
if %ERRORLEVEL% NEQ 0 echo WARNING: fftw3 install failed with code %ERRORLEVEL%

echo.
echo [3/3] Installing libsamplerate...
"%VCPKG%" install libsamplerate:x64-windows
if %ERRORLEVEL% NEQ 0 echo WARNING: libsamplerate install failed with code %ERRORLEVEL%

echo.
echo [optional] Installing sdl2 (LMMS Windows audio backend)...
"%VCPKG%" install sdl2:x64-windows
if %ERRORLEVEL% NEQ 0 echo WARNING: sdl2 install failed with code %ERRORLEVEL%

echo.
echo All done. Exit.
exit /b 0
