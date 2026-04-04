@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x64
cmake --build "C:\Users\Willow\Desktop\WL\build" --config Release --target wavy-labs -- -j%NUMBER_OF_PROCESSORS%
echo Build exit code: %ERRORLEVEL%
if %ERRORLEVEL% EQU 0 (
    REM Copy remote plugin executables to plugins dir so LMMS can find them
    if exist "C:\Users\Willow\Desktop\WL\build\lmms-core\plugins\RemoteVstPlugin64.exe" (
        copy /Y "C:\Users\Willow\Desktop\WL\build\lmms-core\plugins\RemoteVstPlugin64.exe" "C:\Users\Willow\Desktop\WL\build\plugins\" >nul
    )
    if exist "C:\Users\Willow\Desktop\WL\build\lmms-core\plugins\RemoteZynAddSubFx.exe" (
        copy /Y "C:\Users\Willow\Desktop\WL\build\lmms-core\plugins\RemoteZynAddSubFx.exe" "C:\Users\Willow\Desktop\WL\build\plugins\" >nul
    )
    REM Copy Carla weak-link DLL to plugins dir (dummy fallback)
    if exist "C:\Users\Willow\Desktop\WL\build\lmms-core\plugins\CarlaBase\libcarla_native-plugin.dll" (
        copy /Y "C:\Users\Willow\Desktop\WL\build\lmms-core\plugins\CarlaBase\libcarla_native-plugin.dll" "C:\Users\Willow\Desktop\WL\build\plugins\" >nul
    )
    REM Overwrite with full Carla runtime if available (enables VST3/LV2/CLAP hosting)
    if exist "C:\Users\Willow\Desktop\WL\deps\carla\libcarla_native-plugin.dll" (
        REM Copy all top-level DLLs and EXEs from Carla portable
        copy /Y "C:\Users\Willow\Desktop\WL\deps\carla\*.dll" "C:\Users\Willow\Desktop\WL\build\plugins\" >nul
        copy /Y "C:\Users\Willow\Desktop\WL\deps\carla\*.exe" "C:\Users\Willow\Desktop\WL\build\plugins\" >nul 2>nul
        REM Copy Carla subdirectories (lib/, resources/, styles/, platforms/, iconengines/, imageformats/)
        for %%D in (lib resources styles platforms iconengines imageformats) do (
            if exist "C:\Users\Willow\Desktop\WL\deps\carla\%%D\" (
                xcopy /Y /E /Q /I "C:\Users\Willow\Desktop\WL\deps\carla\%%D" "C:\Users\Willow\Desktop\WL\build\plugins\%%D" >nul
            )
        )
        REM Also copy key DLLs next to lmms.exe and into resources/ (child processes need them)
        for %%P in ("C:\Users\Willow\Desktop\WL\build" "C:\Users\Willow\Desktop\WL\build\plugins\resources") do (
            copy /Y "C:\Users\Willow\Desktop\WL\deps\carla\libpython3.8.dll" %%P\ >nul
            copy /Y "C:\Users\Willow\Desktop\WL\deps\carla\libcarla_utils.dll" %%P\ >nul
        )
        echo Real Carla runtime copied — VST3/LV2/CLAP hosting enabled
    )
)
exit /b %ERRORLEVEL%
