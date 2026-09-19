#!/bin/sh
# Copyright (C) 2026 Jerome Berclaz
# SPDX-License-Identifier: GPL-3.0-or-later
# Install under PREFIX (default /usr/local). Example: ./install.sh "$HOME/.local"
# For distro packaging, set DESTDIR for staging:
#   DESTDIR="$pkgdir" ./install.sh /usr
set -e
PREFIX="${1:-/usr/local}"
DESTDIR="${DESTDIR:-}"
LIB="$PREFIX/lib/system-monitor-sway"
SHARE="$PREFIX/share/system-monitor-sway"
BINDIR="$PREFIX/bin"
MANDIR="$PREFIX/share/man/man1"

mkdir -p "$DESTDIR$LIB" "$DESTDIR$SHARE" "$DESTDIR$BINDIR"

install -m 644 chart.py collectors.py "$DESTDIR$LIB/"
install -m 755 system_monitor_sway.py "$DESTDIR$LIB/"
install -m 644 config.json "$DESTDIR$SHARE/"
if [ -f system-monitor-sway.1 ]; then
  mkdir -p "$DESTDIR$MANDIR"
  install -m 644 system-monitor-sway.1 "$DESTDIR$MANDIR/"
fi

cat >"$DESTDIR$BINDIR/system-monitor-sway" <<EOF
#!/bin/sh
exec python3 "$LIB/system_monitor_sway.py" "\$@"
EOF
chmod 755 "$DESTDIR$BINDIR/system-monitor-sway"

echo "Installed $BINDIR/system-monitor-sway"
echo "Config template: $SHARE/config.json"
echo "  mkdir -p ~/.config/system-monitor-sway"
echo "  cp $SHARE/config.json ~/.config/system-monitor-sway/"
echo "Sway:  exec system-monitor-sway"
