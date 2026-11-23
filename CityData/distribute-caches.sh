#!/bin/bash
# FastWeather City Cache Distribution Script
# Run from the CityData/ directory.
# Copies canonical cache files to all platform locations: iOS, webapp, windows.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "FastWeather Cache Distribution"
echo "========================================"
echo ""
echo "Source: $SCRIPT_DIR"
echo ""

# Check if cached files exist
if [ ! -f "$SCRIPT_DIR/international-cities-cached.json" ]; then
    echo "ERROR: international-cities-cached.json not found in CityData/"
    echo "Run build-international-cache.py first."
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/us-cities-cached.json" ]; then
    echo "ERROR: us-cities-cached.json not found in CityData/"
    echo "Run build-city-cache.py first."
    exit 1
fi

copy_files() {
    local dest="$1"
    local label="$2"
    if [ ! -d "$dest" ]; then
        echo "  ⊘ SKIPPED: $dest not found"
        return
    fi
    cp "$SCRIPT_DIR/international-cities-cached.json" "$dest/"
    cp "$SCRIPT_DIR/us-cities-cached.json" "$dest/"
    echo "  ✓ $label"
}

echo "[1/3] iOS..."
copy_files "$ROOT_DIR/iOS/FastWeather/Resources" "iOS/FastWeather/Resources/"
# Places of the World is iOS-only for now; add web/ and windows/ copies when they get the UI
if [ -f "$SCRIPT_DIR/places-of-the-world.json" ]; then
    cp "$SCRIPT_DIR/places-of-the-world.json" "$ROOT_DIR/iOS/FastWeather/Resources/"
    echo "  ✓ places-of-the-world.json"
fi
echo ""

echo "[2/3] Web/PWA..."
copy_files "$ROOT_DIR/webapp" "webapp/"
echo ""

echo "[3/3] Windows..."
copy_files "$ROOT_DIR/windows" "windows/"
echo ""

echo "========================================"
echo "Distribution Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  - iOS: rebuild in Xcode"
echo "  - Web: hard refresh (Ctrl+Shift+R)"
echo "  - Windows: run build.py to rebuild .exe"
echo ""
