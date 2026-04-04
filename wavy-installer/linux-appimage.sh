#!/usr/bin/env bash
# Wavy Labs — Linux AppImage builder
# Requires: linuxdeployqt, appimagetool

set -euo pipefail

APP_NAME="wavy-labs"
APP_VERSION="1.0.0"
BUILD_DIR="../build/Release"
APPDIR="./AppDir"

echo "──────────────────────────────────────────"
echo " Building ${APP_NAME} ${APP_VERSION} AppImage"
echo "──────────────────────────────────────────"

rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

cp "${BUILD_DIR}/wavy-labs" "${APPDIR}/usr/bin/wavy-labs"
cp -r "../data"             "${APPDIR}/usr/share/wavy-labs/"
cp -r "../wavy-ai"          "${APPDIR}/usr/share/wavy-labs/"

# Desktop entry
cat > "${APPDIR}/usr/share/applications/wavy-labs.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=Wavy Labs
GenericName=AI-powered DAW
Comment=AI-powered Digital Audio Workstation
Exec=wavy-labs %f
Icon=wavy-labs
Categories=AudioVideo;Audio;
MimeType=application/x-wavy-project;
Keywords=music;daw;production;ai;
DESKTOP

cp "${APPDIR}/usr/share/applications/wavy-labs.desktop" "${APPDIR}/"

# App icon (placeholder; replace with real 256×256 PNG)
if [ -f "../data/icons/wavy-labs-256.png" ]; then
    cp "../data/icons/wavy-labs-256.png" \
       "${APPDIR}/usr/share/icons/hicolor/256x256/apps/wavy-labs.png"
    cp "../data/icons/wavy-labs-256.png" "${APPDIR}/wavy-labs.png"
fi

# Bundle Qt + system libs
linuxdeployqt "${APPDIR}/usr/bin/wavy-labs" \
    -qmake="${QT_DIR:-/usr/lib/qt6}/bin/qmake" \
    -appimage \
    -no-strip \
    -extra-plugins=iconengines,platformthemes/libqgtk3.so

# Rename
mv *.AppImage "WavyLabs-${APP_VERSION}-x86_64.AppImage" 2>/dev/null || true
echo "✅  WavyLabs-${APP_VERSION}-x86_64.AppImage created."
