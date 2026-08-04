#!/usr/bin/env bash
# Download official Debian libxkbcommon .debs and extract into your home directory (no sudo).
# Run once, then use ../run_blender.sh for bundled Blender.

set -euo pipefail

TARGET="${HOME}/.local/share/BlenderObjects-bundled-libs"
TMP="${TMPDIR:-/tmp}/blender-libxkb-$$"
BASE="https://deb.debian.org/debian/pool/main/libx/libxkbcommon"
VER="1.5.0-1"

case "$(uname -m)" in
  x86_64)  DEB_ARCH="amd64" ;;
  aarch64) DEB_ARCH="arm64" ;;
  *)
    echo "Unsupported machine: $(uname -m). Install libxkbcommon via your distro or conda."
    exit 1
    ;;
esac

mkdir -p "$TMP" "$TARGET"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

fetch() {
  local url="$1" name="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "$TMP/$name" "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "$TMP/$name" "$url"
  else
    echo "Need curl or wget."
    exit 1
  fi
}

echo "Fetching Debian bookworm ${DEB_ARCH} packages..."
fetch "${BASE}/libxkbcommon0_${VER}_${DEB_ARCH}.deb" "libxkbcommon0.deb"
fetch "${BASE}/libxkbcommon-x11-0_${VER}_${DEB_ARCH}.deb" "libxkbcommon-x11-0.deb"

dpkg-deb -x "$TMP/libxkbcommon0.deb" "$TARGET"
dpkg-deb -x "$TMP/libxkbcommon-x11-0.deb" "$TARGET"

echo "Extracted to: $TARGET"
echo "Run Blender with: $(dirname "$0")/../run_blender.sh -b -P animate_alice_stl.py"
