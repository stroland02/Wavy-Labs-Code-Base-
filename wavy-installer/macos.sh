#!/usr/bin/env bash
# Wavy Labs — macOS DMG builder
# Requires: create-dmg (brew install create-dmg), Xcode command line tools

set -euo pipefail

APP_NAME="Wavy Labs"
APP_VERSION="1.0.0"
BUILD_DIR="../build/Release"
DIST_DIR="./dist/macos"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"
DMG_NAME="WavyLabs-${APP_VERSION}-macOS.dmg"

echo "──────────────────────────────────────"
echo " Building ${APP_NAME} ${APP_VERSION} DMG"
echo "──────────────────────────────────────"

# Clean
rm -rf "${DIST_DIR}"
mkdir -p "${APP_BUNDLE}/Contents/MacOS"
mkdir -p "${APP_BUNDLE}/Contents/Resources"
mkdir -p "${APP_BUNDLE}/Contents/Frameworks"

# Copy binary
cp "${BUILD_DIR}/wavy-labs" "${APP_BUNDLE}/Contents/MacOS/wavy-labs"
chmod +x "${APP_BUNDLE}/Contents/MacOS/wavy-labs"

# Copy resources
cp -r "../data"             "${APP_BUNDLE}/Contents/Resources/"
cp "../data/icons/wavy-labs.icns" "${APP_BUNDLE}/Contents/Resources/AppIcon.icns"

# Copy Python AI backend
mkdir -p "${APP_BUNDLE}/Contents/Resources/wavy-ai"
cp -r "../wavy-ai" "${APP_BUNDLE}/Contents/Resources/"

# Info.plist
cat > "${APP_BUNDLE}/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>             <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>      <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>       <string>io.wavylabs.app</string>
    <key>CFBundleVersion</key>          <string>${APP_VERSION}</string>
    <key>CFBundleShortVersionString</key><string>${APP_VERSION}</string>
    <key>CFBundleExecutable</key>       <string>wavy-labs</string>
    <key>CFBundleIconFile</key>         <string>AppIcon</string>
    <key>CFBundlePackageType</key>      <string>APPL</string>
    <key>CFBundleSignature</key>        <string>WVLY</string>
    <key>NSHighResolutionCapable</key>  <true/>
    <key>NSPrincipalClass</key>         <string>NSApplication</string>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeExtensions</key>
            <array><string>wavy</string></array>
            <key>CFBundleTypeName</key>
            <string>Wavy Labs Project</string>
            <key>CFBundleTypeRole</key>
            <string>Editor</string>
        </dict>
    </array>
</plist>
PLIST

# macdeployqt
echo "Running macdeployqt …"
macdeployqt "${APP_BUNDLE}" \
    -qmldir="../src" \
    -webengine-path="${APP_BUNDLE}" \
    -always-overwrite

# Code sign (requires a valid Developer ID cert)
if [ -n "${APPLE_DEVELOPER_ID:-}" ]; then
    echo "Code signing with ${APPLE_DEVELOPER_ID} …"
    codesign --deep --force --options runtime \
        --sign "${APPLE_DEVELOPER_ID}" \
        "${APP_BUNDLE}"
fi

# Create DMG
echo "Creating DMG …"
create-dmg \
    --volname "${APP_NAME} ${APP_VERSION}" \
    --volicon "../data/icons/wavy-labs.icns" \
    --background "../data/icons/dmg-background.png" \
    --window-pos 200 120 \
    --window-size 800 400 \
    --icon-size 100 \
    --icon "${APP_NAME}.app" 200 190 \
    --hide-extension "${APP_NAME}.app" \
    --app-drop-link 600 185 \
    "${DMG_NAME}" \
    "${DIST_DIR}/"

echo "✅  ${DMG_NAME} created."
