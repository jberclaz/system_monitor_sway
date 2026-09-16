#!/bin/sh
# Copyright (C) 2026 Jerome Berclaz
# SPDX-License-Identifier: GPL-3.0-or-later
# Install under PREFIX (default /usr/local). Example: ./install.sh "$HOME/.local"
set -e
PREFIX="${1:-/usr/local}"
LIB="$PREFIX/lib/system-monitor-sway"
SHARE="$PREFIX/share/system-monitor-sway"
BINDIR="$PREFIX/bin"

mkdir -p "$LIB" "$SHARE" "$BINDIR"

install -m 644 chart.py collectors.py "$LIB/"
install -m 755 system_monitor_sway.py "$LIB/"
install -m 644 config.json "$SHARE/"

cat >"$BINDIR/system-monitor-sway" <<EOF
#!/bin/sh
exec python3 "$LIB/system_monitor_sway.py" "\$@"
EOF
chmod 755 "$BINDIR/system-monitor-sway"

echo "Installed $BINDIR/system-monitor-sway"
echo "Config template: $SHARE/config.json"
echo "  mkdir -p ~/.config/system-monitor-sway"
echo "  cp $SHARE/config.json ~/.config/system-monitor-sway/"
echo "Sway:  exec system-monitor-sway"
