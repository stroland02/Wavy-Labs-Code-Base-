@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x64
cmake -G Ninja -B "C:/Users/Willow/Desktop/WL/build" -S "C:/Users/Willow/Desktop/WL" ^
    -DCMAKE_TOOLCHAIN_FILE=C:/tmp/vcpkg/scripts/buildsystems/vcpkg.cmake ^
    -DVCPKG_TARGET_TRIPLET=x64-windows ^
    -DLMMS_MINIMAL=ON ^
    "-DPLUGIN_LIST=ReverbSC VstBase Vestige VstEffect CarlaBase CarlaRack CarlaPatchbay Xpressive" ^
    -DCMAKE_BUILD_TYPE=Release ^
    "-DCMAKE_INSTALL_PREFIX=C:/Program Files (x86)/WavyLabs" ^
    -DCMAKE_PREFIX_PATH=C:/Qt/6.9.1/msvc2022_64
echo Configure exit code: %ERRORLEVEL%
exit /b %ERRORLEVEL%
