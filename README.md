# system-monitor-sway

Stacked CPU, memory, and network graphs for **Sway**, matching the look and chart algorithm of [gnome-shell-system-monitor-applet](https://github.com/paradoxxxzero/gnome-shell-system-monitor-applet) (same colors, graph width, and libgtop sampling).

The widget is a thin **gtk-layer-shell** strip anchored to the **top center** of the screen. It sits over the middle of **Waybar**, similar to enabling `center-display` in the GNOME extension. **GNOME Shell is not required** on the Sway machine—only Python, libgtop, and gtk-layer-shell.

## Architecture: this app vs a “Waybar plugin”

**Waybar does not load Python (or other) plugins that draw inside the bar.** A normal Waybar setup looks like this:

| Approach | What it is | GNOME-style stacked graphs? |
|----------|------------|-----------------------------|
| **`custom/` module** | Shell/Python script prints text or JSON; Waybar shows labels/icons | No—unless you fake it with Braille/block characters (different look) |
| **`custom-graph/` module** (upstream work in progress) | C++ module; script returns a **percentage**; Waybar draws line/bar/gauge | Close for a **single** series per module; not the extension’s **multi-layer stacked areas** (CPU user/sys/nice/…, mem program/buffer/cache, net up/down/errors) in one chart |
| **Built-in `cpu` / `memory` / `network`** | Text and icons in the bar | Different UI entirely |
| **This project (gtk-layer-shell)** | Separate small GTK process; same Cairo stacking as the GNOME extension | **Yes**—that is why it is implemented this way |

So the current layout (`lib/system-monitor-sway/` + `system-monitor-sway` on `PATH`) is the usual pattern for a **standalone bar widget**, not a Waybar plugin. It is still standard on Sway stacks that already use Waybar: one process for the bar, one for overlays (polkit agents, notifications, etc.).

**If you want everything inside Waybar’s config only:** you trade away “looks exactly like the GNOME applet.” Reasonable compromises:

1. Use Waybar’s built-in modules (simplest, different appearance).
2. Use `custom-graph/*` when your Waybar build includes it—one graph per metric, fed by small scripts (good graphs, not identical to the extension).
3. Keep **system-monitor-sway** for pixel-level parity with the GNOME extension (recommended for your original goal).

A future middle ground would be a **`system-monitor-sway print-json`** mode for `custom-graph` scripts that reuses the same libgtop collectors—but Waybar would still need stacked-area support in C++ to match the applet fully.

## Where files go (standard layout)

Do **not** install only `system_monitor_sway.py`. It imports `chart.py` and `collectors.py`; those three modules must live in the **same directory**.

| What | Standard path | Notes |
|------|----------------|--------|
| Python modules | `/usr/local/lib/system-monitor-sway/` | `system_monitor_sway.py`, `chart.py`, `collectors.py` |
| Command on `PATH` | `/usr/local/bin/system-monitor-sway` | Small wrapper; runs the module above |
| Shipped default config | `/usr/local/share/system-monitor-sway/config.json` | Template; safe to overwrite on upgrade |
| **Your** config (preferred) | `~/.config/system-monitor-sway/config.json` | XDG; edit this |
| Optional system config | `/etc/system-monitor-sway/config.json` | Overrides share, not user home |

**Config lookup order** (when you do not pass `-c`):

1. `~/.config/system-monitor-sway/config.json` (or `$XDG_CONFIG_HOME/system-monitor-sway/config.json`)
2. `/etc/system-monitor-sway/config.json`
3. `/usr/share/system-monitor-sway/config.json` or `/usr/local/share/system-monitor-sway/config.json`
4. `config.json` next to the scripts (git checkout / dev only)

Use `-c /path/to/config.json` to force a specific file.

### Install from a git checkout

```bash
cd system_monitor_sway
sudo ./install.sh              # installs under /usr/local
# or: sudo ./install.sh /usr    # prefix /usr instead
mkdir -p ~/.config/system-monitor-sway
cp /usr/local/share/system-monitor-sway/config.json ~/.config/system-monitor-sway/
```

### Run from a checkout without installing

Keep the whole directory together and point Sway at the script, with `config.json` in that same folder:

```bash
exec python3 /path/to/system_monitor_sway/system_monitor_sway.py
```

Or put config only under XDG:

```bash
mkdir -p ~/.config/system-monitor-sway
cp /path/to/system_monitor_sway/config.json ~/.config/system-monitor-sway/
exec python3 /path/to/system_monitor_sway/system_monitor_sway.py
```

---

## Installation (Sway)

### 1. Dependencies

**Arch Linux**:

```bash
sudo pacman -S python python-gobject libgtop gtk-layer-shell
```

**Debian / Ubuntu**:

```bash
sudo apt install python3 python3-gi gir1.2-gtop-2.0 libgtk-layer-shell0 gir1.2-gtklayershell-0.1
```

`libgtk-layer-shell0` is the C library; **Python also needs** `gir1.2-gtklayershell-0.1` (GObject introspection). Without the GIR package, `from gi.repository import GtkLayerShell` fails even when the `.so` is installed.

**Fedora**:

```bash
sudo dnf install python3-gobject libgtop gtk-layer-shell
```

**RHEL / CentOS Stream**: `gtk-layer-shell` may require EPEL or a source build; see [gtk-layer-shell](https://github.com/wmww/gtk-layer-shell).

Verify:

```bash
python3 -c "import gi; gi.require_version('GTop','2.0'); from gi.repository import GTop; print('gtop ok')"
python3 -c "import gi; gi.require_version('GtkLayerShell','0.1'); from gi.repository import GtkLayerShell; print('layer-shell ok')"
```

### 2. Install the application

Use `./install.sh` (above) **or** copy the three `.py` files into `/usr/local/lib/system-monitor-sway/`, `config.json` into `/usr/local/share/system-monitor-sway/`, and add a `system-monitor-sway` wrapper in `/usr/local/bin/` that runs `python3 …/system_monitor_sway.py`.

### 3. Verify (optional)

```bash
python3 verify_graphs.py
system-monitor-sway --self-check
```

(`verify_graphs.py` stays in the source tree; not required on the Sway machine at runtime.)

### 4. Waybar

**`bar_height` must equal Waybar’s `"height"`**. Leave **`modules-center`** empty.

The monitor must be a **layer-shell** surface overlapping the bar. Sway insets that surface by Waybar’s exclusive zone; the app applies a top margin of **`-bar_height`** automatically. You do not need `layer_shell_margin_top` in config unless Waybar’s reserved height differs from `bar_height`.

```jsonc
"position": "top",
"layer": "top",
"height": 30,
"modules-center": []
```

Monitor: `"layer_shell_layer": "overlay"`, `"bar_height": 30`.

On start, stderr should show `debug: layer_window=True screen=(…,0)`. If `layer_window=False` or screen y is about 30, it is still a normal window.

No Waybar CSS changes are required for this Y-position bug.

### 5. Sway autostart

In `~/.config/sway/config`:

```bash
exec_always waybar
exec system-monitor-sway
```

Reload: `swaymsg reload`.

### Testing from a terminal

Run the same command Sway will use (from a **Sway** session, not SSH without `WAYLAND_DISPLAY`):

```bash
system-monitor-sway
# or, from a checkout:
python3 /path/to/system_monitor_sway/system_monitor_sway.py -c ~/.config/system-monitor-sway/config.json
```

Watch stderr for `bar_height=… layer=top` and the path to `waybar-transparent-center.css`. Stop with **Ctrl+C** before starting another copy (only one instance should run). When it looks right, add the `exec` line to `sway/config` and drop the manual terminal start.

---

## Configuration

Edit `~/.config/system-monitor-sway/config.json` (after copying from share). Defaults mirror the GNOME extension:

| Element | Default | Graph colors |
|---------|---------|--------------|
| cpu | on, 1500 ms | blues |
| memory | on, 5000 ms | greens |
| net | on, 1000 ms | yellow / magenta stack |

Keys: per-element `display`, `label`, `show_label`, `style`, `refresh_ms`, `position`, `colors`, `graph_width`; global `bar_height` (match Waybar height; top margin is `-bar_height` unless you set `layer_shell_margin_top`), `background`, `element_spacing`, `layer_shell_layer` (`overlay`), `show_tooltip` (hover details like the GNOME applet; default true), `tooltip_delay_ms` (wait before showing; default 1000).

## Verify (development)

Headless parity check against the GNOME extension chart code:

```bash
python3 verify_graphs.py
```

## Notes

- Pop-up menu, disk pie/bar, battery, and thermal are not ported yet.
- Tune CSS in `system_monitor_sway.py` to match your Waybar font if needed.

## License

Chart logic derived from gnome-shell-system-monitor-applet (GPL-3.0).
