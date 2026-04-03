#!/usr/bin/env bash
# deploy.sh — Stage runtime DLLs and Qt plugins for Windows distribution
#
# Run from an MSYS2 MinGW 64-bit shell AFTER building:
#   ./deploy.sh [build_dir]
#
# What it does:
#   1. Copies all MSYS2/MinGW DLL dependencies (resolved via ldd)
#   2. Copies required Qt6 plugins (platforms, imageformats, iconengines,
#      styles, tls, sqldrivers)
#   3. Creates qt.conf so Qt finds plugins relative to the exe
#
# After running this, build/ is self-contained and the NSIS installer
# can be built with: makensis wavy-installer/windows.nsi
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${1:-${SCRIPT_DIR}/build}"
MSYS2_BIN="/c/msys64/mingw64/bin"
QT_PLUGINS="/c/msys64/mingw64/share/qt6/plugins"

if [ ! -f "${BUILD_DIR}/wavy-labs.exe" ]; then
    echo "ERROR: ${BUILD_DIR}/wavy-labs.exe not found. Run ./build.sh first."
    exit 1
fi

echo "==> Staging runtime DLLs into ${BUILD_DIR}"

# ── 1. Copy all MSYS2/MinGW DLL dependencies via ldd ─────────────────────────
copy_deps() {
    local exe="$1"
    local count=0
    while IFS= read -r line; do
        # ldd line: "  libfoo.dll => /mingw64/bin/libfoo.dll (0xaddr)"
        if [[ "$line" =~ (\/mingw64\/bin\/[^[:space:]]+\.dll) ]]; then
            src="${BASH_REMATCH[1]}"
            # Map /mingw64 → /c/msys64/mingw64
            src="${src/\/mingw64\//\/c\/msys64\/mingw64\/}"
            dest="${BUILD_DIR}/$(basename "$src")"
            if [ -f "$src" ] && [ ! -f "$dest" ]; then
                cp "$src" "$dest"
                (( count++ )) || true
            fi
        fi
    done < <(ldd "$exe" 2>/dev/null)
    echo "$count"
}

total=0
n=$(copy_deps "${BUILD_DIR}/wavy-labs.exe")
total=$(( total + n ))
if [ -f "${BUILD_DIR}/lmms.exe" ]; then
    n=$(copy_deps "${BUILD_DIR}/lmms.exe")
    total=$(( total + n ))
fi
echo "    Copied ${total} new runtime DLLs"

# ── 2. Qt6 plugins ────────────────────────────────────────────────────────────
PLUGIN_DIRS=(
    platforms
    imageformats
    iconengines
    styles
    tls
    sqldrivers
    networkinformation
)

plugin_count=0
for dir in "${PLUGIN_DIRS[@]}"; do
    src="${QT_PLUGINS}/${dir}"
    [ -d "$src" ] || continue
    mkdir -p "${BUILD_DIR}/${dir}"
    for dll in "${src}"/*.dll; do
        [ -f "$dll" ] || continue
        dest="${BUILD_DIR}/${dir}/$(basename "$dll")"
        if [ ! -f "$dest" ]; then
            cp "$dll" "$dest"
            (( plugin_count++ )) || true
        fi
    done
done
echo "    Copied ${plugin_count} new Qt plugin DLLs"

# ── 3. qt.conf — tells Qt6 where to find plugins relative to the exe ─────────
cat > "${BUILD_DIR}/qt.conf" << 'EOF'
[Paths]
Plugins = .
EOF
echo "    Wrote qt.conf"

# ── 4. Report plugin dirs that were built ─────────────────────────────────────
for plugdir in "${BUILD_DIR}/plugins" "${BUILD_DIR}/ladspa" "${BUILD_DIR}/lv2"; do
    [ -d "$plugdir" ] && echo "    LMMS plugin dir: ${plugdir}"
done

echo ""
echo "==> Deploy complete. ${BUILD_DIR} is ready for packaging."
total_dlls=$(ls "${BUILD_DIR}"/*.dll 2>/dev/null | wc -l)
echo "    ${total_dlls} DLLs total in ${BUILD_DIR}"
echo ""
echo "    To test:    cd build && ./wavy-labs.exe"
echo "    To package: makensis wavy-installer/windows.nsi"
