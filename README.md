# system-monitor-sway

Stacked CPU, memory, and network graphs for **Sway**, matching [gnome-shell-system-monitor-applet](https://github.com/paradoxxxzero/gnome-shell-system-monitor-applet). A small overlay sits in the **center of Waybar**. GNOME is not required.

## Install

### 1. Packages

Ubuntu / Debian:

```bash
sudo apt install python3 python3-gi gir1.2-gtop-2.0 libgtk-layer-shell0 gir1.2-gtklayershell-0.1
```

Install **both** `libgtk-layer-shell0` and `gir1.2-gtklayershell-0.1` (Python needs the GIR package).

Arch: `sudo pacman -S python python-gobject libgtop gtk-layer-shell`  
Fedora: `sudo dnf install python3-gobject libgtop gtk-layer-shell`

### 2. Program

```bash
sudo ./install.sh
mkdir -p ~/.config/system-monitor-sway
cp /usr/local/share/system-monitor-sway/config.json ~/.config/system-monitor-sway/
```

No root: `./install.sh "$HOME/.local"` and copy from `~/.local/share/system-monitor-sway/config.json` (keep `~/.local/bin` on `PATH`).

Match `bar_height` in that config to Waybar’s `"height"` (both default `30`). Leave Waybar `"modules-center"` empty.

### 3. Autostart

Put this in `~/.config/sway/config` in the **autostart / `exec` section** (same place as Waybar, mako, etc.). Not inside a `bar { }` block.

Use a **full path** (Sway’s `PATH` is often shorter than your terminal’s):

```bash
exec waybar
exec /usr/local/bin/system-monitor-sway
```

If you installed with `./install.sh "$HOME/.local"`:

```bash
exec /home/YOU/.local/bin/system-monitor-sway
```

`exec` runs **once at login**, not on `swaymsg reload`. After adding the line, either log out/in or:

```bash
swaymsg exec /usr/local/bin/system-monitor-sway
```

Do **not** use `exec_always` for the monitor unless you `pkill` it first — reload would start a second copy. `exec_always waybar` for Waybar is fine.

## Configure

Edit `~/.config/system-monitor-sway/config.json`.

| Key | Role |
|-----|------|
| `bar_height` | Must match Waybar `height` |
| `show_tooltip` / `tooltip_delay_ms` | Hover details (default 1s delay) |
| `elements.*.display` | Show cpu / memory / net |
| `layer_shell_margin_top` | Optional; default is `-bar_height` so the strip overlaps Waybar |

Lookup: `~/.config/system-monitor-sway/config.json`, then `/etc/…`, then `/usr/local/share/…`. Override with `-c path`.

## Development

```bash
python3 verify_graphs.py
python3 system_monitor_sway.py --self-check
```

Not ported: applet popup menu, disk, battery, thermal, GPU.

## License

Chart logic derived from gnome-shell-system-monitor-applet (GPL-3.0).
