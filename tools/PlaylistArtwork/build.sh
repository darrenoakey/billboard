#!/bin/bash
# builds and signs PlaylistArtwork.app next to this script
set -euo pipefail
cd "$(dirname "$0")"
APP=PlaylistArtwork.app
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS"
cp Info.plist "$APP/Contents/Info.plist"
swiftc -O -o "$APP/Contents/MacOS/PlaylistArtwork" Sources/main.swift -framework ScriptingBridge -framework AppKit
IDENTITY=$(security find-identity -v -p codesigning 2>/dev/null | awk -F'"' '/Apple Development|Developer ID Application/{print $2; exit}')
codesign --force --sign "${IDENTITY:--}" "$APP"
echo "built $APP signed with ${IDENTITY:-ad-hoc}"
