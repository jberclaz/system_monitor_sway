# system-monitor-sway

Stacked CPU, memory and network graphs for **Sway**, drawn directly inside
**Waybar** as a native module — matching
[gnome-shell-system-monitor-applet](https://github.com/paradoxxxzero/gnome-shell-system-monitor-applet).
No overlay window, no image file, no scripting runtime: Waybar owns the
pixels, so placement, fullscreen behavior and stacking just work (a
fullscreen video covers the bar, graphs included).

## Install

### 1. Packages

Build tools plus gtk3 headers (Debian/Ubuntu):

```bash
sudo apt install gcc make pkg-config libgtk-3-dev
```

Arch: `sudo pacman -S gcc make pkgconf gtk3`
Fedora: `sudo dnf install gcc make pkgconf-pkg-config gtk3-devel`

Runtime needs only gtk3 (Waybar already links it). No Python, no libgtop.

Packaged installs (Arch AUR, Fedora COPR) are described in
[packaging/README.md](packaging/README.md). Manual install:

### 2. Build and install

```bash
sudo ./install.sh
```

No root: `./install.sh "$HOME/.local"`.

### 3. Waybar config

Merge `waybar-config-example.jsonc` (installed to
`/usr/local/share/system-monitor-sway/` or `/usr/share/…`) into
`~/.config/waybar/config.json`:

```json
"modules-center": ["cffi/sysmon"],
"cffi/sysmon": {
  "module_path": "/usr/lib/system-monitor-sway/waybar_sysmon.so",
  "graph_width": 100,
  "height": 30,
  "spacing": 4,
  "interval_ms": 1000,
  "background": "#ffffff16",
  "graphs": ["cpu", "memory", "net"]
}
```

Set `module_path` to the installed location
(`$HOME/.local/lib/…` for unprivileged installs). Reload Waybar
(`swaymsg reload` or restart it) to pick up the change.

## Configure

Keys after `module_path` are optional (defaults shown above):

| Key | Default | Role |
|-----|---------|------|
| `graph_width` | `100` | Chart width in px |
| `height` | `30` | Strip height in px. Match Waybar's `height` |
| `spacing` | `4` | Gap between graphs in px |
| `interval_ms` | `1000` | Repaint/sample tick in ms (minimum `250`) |
| `background` | `#ffffff16` | Chart background (`#rrggbb` or `#rrggbbaa`) |
| `graphs` | cpu, memory, net | Subset to display, in canonical order |
| `refresh_cpu_ms` | `1500` | CPU sample period (minimum `250`) |
| `refresh_memory_ms` | `5000` | Memory sample period |
| `refresh_net_ms` | `1000` | Network sample period |
| `colors_cpu` | GNOME default (5 layers) | One `#rrggbb` per layer, exactly 5 entries |
| `colors_memory` | GNOME default (3 layers) | Exactly 3 entries |
| `colors_net` | GNOME default (5 layers) | Exactly 5 entries |

Wrong-sized color arrays keep the defaults. CPU colors (bottom to top):
user, system, nice, iowait, other (`#0072b3` `#0092e6` `#00a3ff`
`#002f3d` `#001d26`). Memory: program, buffer, cache (`#00b35b`
`#00ff82` `#aaf5d0`). Net: down, downerrors, up, uperrors, collisions
(`#fce94f` `#ff6e00` `#fb74fb` `#e0006e` `#ff0000`).

CPU and network sample `/proc` differentially (first tick primes, graphs
fill right-to-left); memory is stateless. On startup the module samples
at 100 ms for ~6 s so the charts arrive populated, then settles into the
configured periods.

Debug with `WAYBAR_SYSMON_DEBUG=1 waybar` (sampling + paint diagnostics
on stderr).

## Development

```bash
make -C cffi        # build/waybar_sysmon.so, warning-free (-Wall -Wextra -Wpedantic)
make -C cffi test   # chart/collector unit tests, incl. bit-exact check vs the GNOME math
```

`make -C cffi visualtest` builds a standalone GTK window harness rendering
the same charts (useful where screenshots cannot see layer-shell).

Current limits: cpu / memory / net only, graphs without labels or
tooltips, no HiDPI scaling yet. The module targets Waybar's CFFI ABI v2
(header vendored in `cffi/waybar_cffi_module.h`); if Waybar ever requires
a newer ABI, the module refuses to load with an error instead of
misrendering.

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).

Chart logic derived from gnome-shell-system-monitor-applet (GPL-3.0).
