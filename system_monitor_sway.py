#!/usr/bin/env python3
"""
GNOME system-monitor style graphs for Sway (Wayland).

Draws the same stacked area charts as gnome-shell-system-monitor-applet and anchors
them to the center of the top bar via gtk-layer-shell (over your Waybar strip).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

APP_NAME = "system-monitor-sway"

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell  # noqa: E402

    HAS_LAYER = True
    LAYER_IMPORT_ERROR = ""
except (ValueError, ImportError) as exc:
    HAS_LAYER = False
    GtkLayerShell = None  # type: ignore[misc, assignment]
    LAYER_IMPORT_ERROR = str(exc)

from chart import StackedChart, parse_color  # noqa: E402
from collectors import CpuCollector, MemoryCollector, NetCollector  # noqa: E402

CSS = """
window {
    background-color: transparent;
}
.sm-bar {
    background-color: transparent;
}
.sm-status-label {
    color: #bbbbbb;
    font-size: 10px;
    padding-top: 5px;
    font-family: monospace;
}
.sm-chart {
    padding: 0 2px;
}
"""


class ChartArea(Gtk.DrawingArea):
    def __init__(
        self,
        chart: StackedChart,
        bg: tuple[float, float, float, float],
        width: int,
        height: int,
    ) -> None:
        super().__init__()
        self._chart = chart
        self._bg = bg
        self.set_size_request(width, height)
        self.get_style_context().add_class("sm-chart")
        self.connect("draw", self._on_draw)

    def _on_draw(self, _widget, cr):
        self._chart.draw(cr, self._bg)
        return False

    def refresh(self) -> None:
        self.queue_draw()


class MonitorElement(Gtk.Box):
    def __init__(
        self,
        name: str,
        cfg: dict,
        graph_height: int,
        bg_rgba: tuple[float, float, float, float],
        scale: float,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.name = name
        self.cfg = cfg
        self._scale = scale
        style = cfg.get("style", "graph")
        show_label = cfg.get("show_label", True)
        width = int(cfg.get("graph_width", 100))

        if show_label:
            lbl = Gtk.Label(label=cfg.get("label", name))
            lbl.set_halign(Gtk.Align.CENTER)
            lbl.set_valign(Gtk.Align.CENTER)
            lbl.get_style_context().add_class("sm-status-label")
            self.pack_start(lbl, False, False, 0)

        fixed_max = None
        if name == "cpu":
            self._collector: CpuCollector | MemoryCollector | NetCollector = CpuCollector()
            fixed_max = self._collector.chart_max  # type: ignore[attr-defined]
        elif name == "memory":
            self._collector = MemoryCollector()
        elif name == "net":
            self._collector = NetCollector()
        else:
            self._collector = MemoryCollector()

        self._chart = StackedChart(
            width,
            graph_height,
            cfg.get("colors", ["#888888"]),
            fixed_max=fixed_max,
            scale_factor=scale,
        )
        self._chart_area = ChartArea(self._chart, bg_rgba, width, graph_height)
        if style in ("graph", "both"):
            self.pack_start(self._chart_area, False, False, 0)
        self._timeout_id = 0
        refresh = max(500, int(cfg.get("refresh_ms", 2000)))
        self._timeout_id = GLib.timeout_add(refresh, self._tick)

    def _tick(self) -> bool:
        if self.name == "cpu":
            result = self._collector.sample()  # type: ignore[union-attr]
            if result is None:
                return True
            vals, _pct = result
        elif self.name == "memory":
            vals = self._collector.sample()  # type: ignore[union-attr]
        else:
            vals = self._collector.sample()  # type: ignore[union-attr]
        self._chart.push(vals)
        self._chart_area.refresh()
        return True

    def destroy_element(self) -> None:
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)


def config_search_paths() -> list[Path]:
    """User override first, then system, then shipped default (FHS + XDG)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    user_base = Path(xdg) if xdg else Path.home() / ".config"
    lib_dir = Path(__file__).resolve().parent
    share_candidates = [
        Path(f"/usr/share/{APP_NAME}/config.json"),
        Path(f"/usr/local/share/{APP_NAME}/config.json"),
        lib_dir / "config.json",
    ]
    return [
        user_base / APP_NAME / "config.json",
        Path(f"/etc/{APP_NAME}/config.json"),
        *share_candidates,
    ]


def resolve_config_path(explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            sys.stderr.write(f"Config not found: {explicit}\n")
            sys.exit(1)
        return explicit
    for path in config_search_paths():
        if path.is_file():
            return path
    sys.stderr.write(
        f"No config found. Create one at ~/.config/{APP_NAME}/config.json\n"
        f"(copy from config.json in the source tree or from "
        f"/usr/share/{APP_NAME}/config.json after install).\n"
    )
    sys.exit(1)


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def layer_shell_install_help() -> str:
    detail = f"\nImport error: {LAYER_IMPORT_ERROR}\n" if LAYER_IMPORT_ERROR else ""
    return (
        "Python needs GObject introspection for gtk-layer-shell (not just the .so).\n"
        "\n"
        "  Debian / Ubuntu:\n"
        "    sudo apt install gir1.2-gtklayershell-0.1 libgtk-layer-shell0 "
        "python3-gi gir1.2-gtop-2.0\n"
        "    (libgtk-layer-shell0 alone is not enough — add gir1.2-gtklayershell-0.1)\n"
        "\n"
        "  Fedora:\n"
        "    sudo dnf install gtk-layer-shell python3-gobject libgtop\n"
        "\n"
        "  Arch:\n"
        "    sudo pacman -S gtk-layer-shell python-gobject libgtop\n"
        + detail
    )


def build_window(cfg: dict) -> Gtk.Window:
    if not HAS_LAYER:
        sys.stderr.write(layer_shell_install_help())
        sys.exit(1)

    bar_height = int(cfg.get("bar_height", 30))
    graph_height = int(cfg.get("graph_height", 22))
    spacing = int(cfg.get("element_spacing", 4))
    bg = parse_color(cfg.get("background", "#ffffff16"))

    win = Gtk.Window()
    win.set_title("system-monitor-sway")
    win.set_decorated(False)
    win.set_resizable(False)
    win.set_app_paintable(True)

    GtkLayerShell.init_for_window(win)
    layer_name = str(cfg.get("layer_shell_layer", "overlay")).lower()
    layer = {
        "background": GtkLayerShell.Layer.BACKGROUND,
        "bottom": GtkLayerShell.Layer.BOTTOM,
        "top": GtkLayerShell.Layer.TOP,
        "overlay": GtkLayerShell.Layer.OVERLAY,
    }.get(layer_name, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_layer(win, layer)
    GtkLayerShell.set_namespace(win, "system-monitor-sway")
    GtkLayerShell.set_exclusive_zone(win, 0)
    for edge in (
        GtkLayerShell.Edge.TOP,
        GtkLayerShell.Edge.LEFT,
        GtkLayerShell.Edge.RIGHT,
    ):
        GtkLayerShell.set_anchor(win, edge, True)

    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )

    scale = win.get_scale_factor()
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    outer.get_style_context().add_class("sm-bar")
    inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)
    inner.set_halign(Gtk.Align.CENTER)
    inner.set_valign(Gtk.Align.CENTER)
    outer.pack_start(inner, True, True, 0)
    win.add(outer)

    elements_cfg = cfg.get("elements", {})
    enabled = [
        (name, elements_cfg[name])
        for name in sorted(
            elements_cfg,
            key=lambda n: int(elements_cfg[n].get("position", 99)),
        )
        if elements_cfg[name].get("display", True)
    ]

    for name, el_cfg in enabled:
        el = MonitorElement(name, el_cfg, graph_height, bg, float(scale))
        inner.pack_start(el, False, False, 0)

    win.show_all()
    win.set_size_request(-1, bar_height)
    return win


def main() -> None:
    parser = argparse.ArgumentParser(description="GNOME-style system monitor for Sway")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Config file (default: first found in XDG /etc /usr/share; see README)",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Run lightweight sanity checks and exit",
    )
    args = parser.parse_args()
    if args.self_check:
        from chart import _self_check

        _self_check()
        CpuCollector()
        print("self-check ok")
        return

    cfg_path = resolve_config_path(args.config)
    cfg = load_config(cfg_path)
    win = build_window(cfg)
    Gtk.main()


if __name__ == "__main__":
    main()
