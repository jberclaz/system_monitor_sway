#!/bin/sh
# Install application files under FHS paths (default: /usr/local).
set -e
PREFIX="${1:-/usr/local}"
LIB="$PREFIX/lib/system-monitor-sway"
SHARE="$PREFIX/share/system-monitor-sway"
BINDIR="$PREFIX/bin"
ETC="/etc/system-monitor-sway"

mkdir -p "$LIB" "$SHARE" "$BINDIR"

install -m 644 chart.py collectors.py "$LIB/"
install -m 755 system_monitor_sway.py "$LIB/"
install -m 644 config.json "$SHARE/"
install -m 644 share/waybar-transparent-center.css "$SHARE/"

cat >"$BINDIR/system-monitor-sway" <<EOF
#!/bin/sh
exec python3 "$LIB/system_monitor_sway.py" "\$@"
EOF
chmod 755 "$BINDIR/system-monitor-sway"

echo "Installed to:"
echo "  $BINDIR/system-monitor-sway"
echo "  $LIB/*.py"
echo "  $SHARE/config.json"
echo "  $SHARE/waybar-transparent-center.css"
echo ""
echo "Optional user config (edit this, not the share copy):"
echo "  mkdir -p ~/.config/system-monitor-sway"
echo "  cp $SHARE/config.json ~/.config/system-monitor-sway/"
echo ""
echo "Optional system-wide config:"
echo "  sudo mkdir -p $ETC && sudo cp $SHARE/config.json $ETC/"
