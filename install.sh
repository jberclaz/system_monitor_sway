#!/bin/sh
# Copyright (C) 2026 Jerome Berclaz
# SPDX-License-Identifier: GPL-3.0-or-later
# Install under PREFIX (default /usr/local). Example: ./install.sh "$HOME/.local"
# For distro packaging, set DESTDIR for staging:
#   DESTDIR="$pkgdir" ./install.sh /usr
# Requires: gcc, make, pkg-config, gtk+-3.0 dev headers.
set -e
PREFIX="${1:-/usr/local}"
DESTDIR="${DESTDIR:-}"
LIB="$PREFIX/lib/system-monitor-sway"
SHARE="$PREFIX/share/system-monitor-sway"
MANDIR="$PREFIX/share/man/man1"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

mkdir -p "$DESTDIR$LIB" "$DESTDIR$SHARE"

command -v gcc >/dev/null 2>&1 || { echo "error: gcc not found" >&2; exit 1; }
command -v make >/dev/null 2>&1 || { echo "error: make not found" >&2; exit 1; }
command -v pkg-config >/dev/null 2>&1 || { echo "error: pkg-config not found" >&2; exit 1; }
pkg-config --exists gtk+-3.0 2>/dev/null || {
  echo "error: gtk+-3.0 dev headers not found (Debian/Ubuntu: libgtk-3-dev, Fedora: gtk3-devel, Arch: gtk3)" >&2
  exit 1
}

make -C "$SCRIPT_DIR/cffi"
install -m 644 "$SCRIPT_DIR/cffi/build/waybar_sysmon.so" "$DESTDIR$LIB/"
install -m 644 "$SCRIPT_DIR/waybar-config-example.jsonc" "$DESTDIR$SHARE/"
if [ -f "$SCRIPT_DIR/waybar-sysmon.1" ]; then
  mkdir -p "$DESTDIR$MANDIR"
  install -m 644 "$SCRIPT_DIR/waybar-sysmon.1" "$DESTDIR$MANDIR/"
fi

echo "Installed $LIB/waybar_sysmon.so"
echo "Waybar config example: $SHARE/waybar-config-example.jsonc"
echo "  add the cffi/sysmon block to ~/.config/waybar/config.jsonc"
echo "  (set module_path to $LIB/waybar_sysmon.so)"
