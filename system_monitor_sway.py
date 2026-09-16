#!/usr/bin/env python3
# Copyright (C) 2026 Jerome Berclaz
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
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

# gtk-layer-shell is Wayland-only. If GTK picks X11/XWayland, Sway treats the
# window as a normal client and places it in the workspace below Waybar.
os.environ.setdefault("GDK_BACKEND", "wayland")

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
from collectors import (  # noqa: E402
    FAN_SENSOR_DEFAULT,
    THERMAL_SENSOR_DEFAULT,
    BatteryCollector,
    CpuCollector,
    DiskCollector,
    FanCollector,
    FreqCollector,
    GpuCollector,
    MemoryCollector,
    NetCollector,
    SwapCollector,
    ThermalCollector,
    disk_rate,
    gpu_chart_vals,
    millidegree_c,
)

CSS = """
window {
    background-color: transparent;
    padding: 0;
    margin: 0;
}
.sm-bar {
    background-color: transparent;
    padding: 0;
    margin: 0;
}
.sm-status-label {
    color: #bbbbbb;
    font-size: 10px;
    padding: 0;
    margin: 0;
    font-family: monospace;
}
.sm-chart {
    padding: 0 2px;
}
.sm-row {
    padding: 0;
    margin: 0;
}
popover.sm-tooltip, popover.sm-tooltip > contents {
    background-color: rgba(10, 10, 10, 0.85);
    border: 1px solid #a5a5a5;
    border-radius: 5px;
    padding: 3px;
}
.sm-tooltip-label {
    color: rgba(255, 255, 255, 0.9);
    font-size: 11px;
    font-weight: bold;
    font-family: monospace;
    padding: 2px 6px;
}
"""


def _net_rate(kib_s: float) -> tuple[str, str]:
    v = float(kib_s)
    if v < 1024:
        return str(int(round(v))), "KiB/s"
    if v < 1048576:
        return f"{(v / 1024):.3g}", "MiB/s"
    return f"{(v / 1048576):.3g}", "GiB/s"


def format_cpu_tip(vals: list[float], _col=None) -> str:
    names = ("user", "system", "nice", "iowait", "other")
    return "\n".join(f"{n}  {int(round(v))} %" for n, v in zip(names, vals))


def format_mem_tip(vals: list[float], _col=None) -> str:
    names = ("program", "buffer", "cache")
    return "\n".join(f"{n}  {int(round(v * 100))} %" for n, v in zip(names, vals))


def format_net_tip(usage: list[float], _col=None) -> str:
    down, up = _net_rate(usage[0]), _net_rate(usage[2])
    return "\n".join(
        (
            f"down  {down[0]} {down[1]}",
            f"downerrors  {int(usage[1])} /s",
            f"up  {up[0]} {up[1]}",
            f"uperrors  {int(usage[3])} /s",
            f"collisions  {int(usage[4])} /s",
        )
    )


def format_swap_tip(vals: list[float], _col=None) -> str:
    return f"used  {int(round(vals[0] * 100))} %"


def _disk_mib(v: float) -> str:
    if v < 10:
        return str(round(10 * v) / 10)
    return str(int(round(v)))


def format_disk_tip(vals: list[float], _col=None) -> str:
    return f"read  {_disk_mib(vals[0])} MiB/s\nwrite  {_disk_mib(vals[1])} MiB/s"


def format_freq_tip(vals: list[float], _col=None) -> str:
    return f"{int(round(vals[0]))} MHz"


def format_thermal_tip(vals: list[float], col=None) -> str:
    t = vals[0]
    if col is not None and getattr(col, "fahrenheit_unit", False):
        t = round(t * 1.8 + 32)
        return f"{int(t)} °F"
    return f"{int(round(t))} °C"


def format_fan_tip(vals: list[float], col=None) -> str:
    rpm = getattr(col, "rpm", int(round(vals[0] * 10))) if col else int(round(vals[0] * 10))
    return f"{rpm} rpm"


def format_gpu_tip(vals: list[float], col=None) -> str:
    if col is None:
        return f"used  {int(round(vals[0]))} %"
    return f"used  {int(col.percentage)} %\nmemory  {int(col.mem)} / {int(col.total)} MiB"


def format_battery_tip(vals: list[float], col=None) -> str:
    pct = int(round(vals[0]))
    extra = getattr(col, "time_string", "") if col else ""
    if extra and extra.strip() not in ("--", ""):
        return f"{pct} %\n{extra}"
    return f"{pct} %"


TIP_FORMATTERS = {
    "cpu": format_cpu_tip,
    "memory": format_mem_tip,
    "net": format_net_tip,
    "swap": format_swap_tip,
    "disk": format_disk_tip,
    "freq": format_freq_tip,
    "thermal": format_thermal_tip,
    "fan": format_fan_tip,
    "gpu": format_gpu_tip,
    "battery": format_battery_tip,
}

COLLECTOR_CLASSES = {
    "cpu": CpuCollector,
    "memory": MemoryCollector,
    "net": NetCollector,
    "swap": SwapCollector,
    "disk": DiskCollector,
    "freq": FreqCollector,
    "gpu": GpuCollector,
    "battery": BatteryCollector,
}


def make_collector(name: str, cfg: dict):
    if name == "thermal":
        return ThermalCollector(
            sensor_file=str(cfg.get("sensor_file", THERMAL_SENSOR_DEFAULT)),
            fahrenheit_unit=bool(cfg.get("fahrenheit_unit", False)),
        )
    if name == "fan":
        return FanCollector(sensor_file=str(cfg.get("sensor_file", FAN_SENSOR_DEFAULT)))
    return COLLECTOR_CLASSES[name]()


DEFAULT_ELEMENTS: dict = {
    "cpu": {
        "display": True,
        "label": "cpu",
        "show_label": True,
        "style": "graph",
        "refresh_ms": 1500,
        "position": 0,
        "colors": ["#0072b3", "#0092e6", "#00a3ff", "#002f3d", "#001d26"],
    },
    "freq": {
        "display": False,
        "label": "freq",
        "show_label": False,
        "style": "graph",
        "refresh_ms": 1500,
        "position": 1,
        "colors": ["#001d26"],
    },
    "memory": {
        "display": True,
        "label": "mem",
        "show_label": True,
        "style": "graph",
        "refresh_ms": 5000,
        "position": 2,
        "colors": ["#00b35b", "#00ff82", "#aaf5d0"],
    },
    "swap": {
        "display": False,
        "label": "swap",
        "show_label": True,
        "style": "graph",
        "refresh_ms": 5000,
        "position": 3,
        "colors": ["#8b00c3"],
    },
    "net": {
        "display": True,
        "label": "net",
        "show_label": True,
        "style": "graph",
        "refresh_ms": 1000,
        "position": 4,
        "colors": ["#fce94f", "#ff6e00", "#fb74fb", "#e0006e", "#ff0000"],
    },
    "disk": {
        "display": False,
        "label": "disk",
        "show_label": True,
        "style": "graph",
        "refresh_ms": 2000,
        "position": 5,
        "colors": ["#c65000", "#ff6700"],
    },
    "gpu": {
        "display": False,
        "label": "gpu",
        "show_label": True,
        "style": "graph",
        "refresh_ms": 5000,
        "position": 6,
        "colors": ["#00b35b", "#00ff82"],
    },
    "thermal": {
        "display": False,
        "label": "thermal",
        "show_label": True,
        "style": "graph",
        "refresh_ms": 5000,
        "position": 7,
        "colors": ["#f2002e"],
        "sensor_file": THERMAL_SENSOR_DEFAULT,
        "fahrenheit_unit": False,
    },
    "fan": {
        "display": False,
        "label": "fan",
        "show_label": True,
        "style": "graph",
        "refresh_ms": 5000,
        "position": 8,
        "colors": ["#f2002e"],
        "sensor_file": FAN_SENSOR_DEFAULT,
    },
    "battery": {
        "display": False,
        "label": "batt",
        "show_label": True,
        "style": "graph",
        "refresh_ms": 5000,
        "position": 9,
        "colors": ["#f2002e"],
    },
}


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


class MonitorElement(Gtk.EventBox):
    def __init__(
        self,
        name: str,
        cfg: dict,
        chart_height: int,
        bg_rgba: tuple[float, float, float, float],
        scale: float,
        *,
        show_tooltip: bool = True,
        tooltip_delay_ms: int = 1000,
    ) -> None:
        super().__init__()
        self.set_visible_window(False)
        self.set_above_child(True)
        self.get_style_context().add_class("sm-row")
        self.set_valign(Gtk.Align.CENTER)
        self.name = name
        self.cfg = cfg
        self._scale = scale
        self._tip_text = ""
        self._tooltip_delay_ms = max(0, int(tooltip_delay_ms))
        self._show_id = 0
        style = cfg.get("style", "graph")
        show_label = cfg.get("show_label", True)
        width = int(cfg.get("graph_width", 100))

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add(row)

        if show_label:
            lbl = Gtk.Label(label=cfg.get("label", name))
            lbl.set_halign(Gtk.Align.CENTER)
            lbl.set_valign(Gtk.Align.CENTER)
            lbl.get_style_context().add_class("sm-status-label")
            row.pack_start(lbl, False, False, 0)

        self._collector = make_collector(name, cfg)
        self._format_tip = TIP_FORMATTERS[name]
        fixed_max = getattr(self._collector, "chart_max", None)

        self._chart = StackedChart(
            width,
            chart_height,
            cfg.get("colors", ["#888888"]),
            fixed_max=fixed_max,
            scale_factor=scale,
        )
        self._chart_area = ChartArea(self._chart, bg_rgba, width, chart_height)
        if style in ("graph", "both"):
            row.pack_start(self._chart_area, False, False, 0)

        self._pop = None
        if show_tooltip:
            self._tip_label = Gtk.Label(label="")
            self._tip_label.set_xalign(0.0)
            self._tip_label.get_style_context().add_class("sm-tooltip-label")
            self._pop = Gtk.Popover.new(self)
            self._pop.set_modal(False)
            # Default constrain-to-window flips the popover above a 30px bar
            # (off-screen). Let it hang below the strip into the workspace.
            try:
                self._pop.set_constrain_to(Gtk.PopoverConstraint.NONE)
            except (AttributeError, TypeError):
                pass
            self._pop.set_position(Gtk.PositionType.BOTTOM)
            self._pop.get_style_context().add_class("sm-tooltip")
            self._pop.add(self._tip_label)
            self._tip_label.show()
            self._poll_id = 0
            self._miss = 0
            self.add_events(
                Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
            )
            self.connect("enter-notify-event", self._on_enter)
            self.connect("leave-notify-event", self._on_leave)

        self._timeout_id = 0
        refresh = max(500, int(cfg.get("refresh_ms", 2000)))
        self._timeout_id = GLib.timeout_add(refresh, self._tick)

    def _set_tip(self, text: str) -> None:
        self._tip_text = text
        if self._pop is not None:
            self._tip_label.set_text(text)

    def _on_enter(self, _widget, event) -> bool:
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        self._miss = 0
        if self._pop is None or not self._tip_text:
            return False
        if self._pop.get_mapped():
            return False
        if self._show_id:
            return False
        delay = self._tooltip_delay_ms
        if delay <= 0:
            self._popup_tip()
        else:
            self._show_id = GLib.timeout_add(delay, self._popup_tip)
        return False

    def _popup_tip(self) -> bool:
        self._show_id = 0
        if self._pop is None or not self._tip_text:
            return False
        if not self._pointer_on_graph_or_tip():
            return False
        self._pop.set_position(Gtk.PositionType.BOTTOM)
        self._pop.popup()
        self._start_poll()
        return False

    def _cancel_show(self) -> None:
        if self._show_id:
            GLib.source_remove(self._show_id)
            self._show_id = 0

    def _on_leave(self, _widget, event) -> bool:
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        if event.mode == Gdk.CrossingMode.GRAB:
            return False
        self._cancel_show()
        self._miss = 2
        return False

    def _start_poll(self) -> None:
        if not getattr(self, "_poll_id", 0):
            self._miss = 0
            self._poll_id = GLib.timeout_add(80, self._poll_pointer)

    def _poll_pointer(self) -> bool:
        if self._pop is None or not self._pop.get_mapped():
            self._poll_id = 0
            return False
        if self._pointer_on_graph_or_tip():
            self._miss = 0
            return True
        self._miss += 1
        if self._miss >= 3:
            self._pop.popdown()
            self._poll_id = 0
            self._miss = 0
            return False
        return True

    def _pointer_on_graph_or_tip(self) -> bool:
        display = self.get_display()
        seat = display.get_default_seat() if display else None
        if seat is None:
            return False
        try:
            at = seat.get_pointer().get_window_at_position()
        except TypeError:
            return False
        win, x, y = self._split_window_at(at)
        if win is None:
            return False
        if self._window_in_widget(win, self._pop) or self._window_in_widget(
            win, self._tip_label
        ):
            return True
        top = self.get_toplevel()
        if not self._window_in_widget(win, top):
            return False
        tx, ty = self._to_toplevel_xy(win, x, y, top)
        if tx is None:
            return False
        origin = self.translate_coordinates(top, 0, 0)
        if origin is None:
            return False
        ox, oy = int(origin[0]), int(origin[1])
        alloc = self.get_allocation()
        return ox <= tx < ox + alloc.width and oy <= ty < oy + alloc.height

    def _split_window_at(self, at):
        if not at:
            return None, 0, 0
        if not isinstance(at, tuple):
            return at, 0, 0
        if len(at) >= 3:
            return at[0], int(at[1]), int(at[2])
        if len(at) == 2:
            return at[0], int(at[1]), 0
        return at[0], 0, 0

    def _to_toplevel_xy(self, gdk_win, x: int, y: int, top) -> tuple[int | None, int | None]:
        topw = top.get_window() if top else None
        if topw is None:
            return None, None
        tx, ty = x, y
        cur = gdk_win
        while cur is not None and cur != topw:
            get_pos = getattr(cur, "get_position", None)
            if get_pos is not None:
                try:
                    pos = get_pos()
                    tx += int(pos[0])
                    ty += int(pos[1])
                except (TypeError, IndexError, ValueError):
                    pass
            parent = getattr(cur, "get_parent", None)
            cur = parent() if parent else None
        if cur != topw:
            return None, None
        return tx, ty

    def _window_in_widget(self, gdk_win, widget) -> bool:
        if widget is None or not widget.get_realized():
            return False
        root = widget.get_window()
        if root is None:
            return False
        cur = gdk_win
        while cur is not None:
            if cur == root:
                return True
            parent = getattr(cur, "get_parent", None)
            cur = parent() if parent else None
        return False

    def _tick(self) -> bool:
        result = self._collector.sample()
        if result is None:
            return True
        vals = result[0] if isinstance(result, tuple) else result
        self._set_tip(self._format_tip(vals, self._collector))
        self._chart.push(vals)
        self._chart_area.refresh()
        return True

    def destroy_element(self) -> None:
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = 0
        if getattr(self, "_show_id", 0):
            GLib.source_remove(self._show_id)
            self._show_id = 0
        if getattr(self, "_poll_id", 0):
            GLib.source_remove(self._poll_id)
            self._poll_id = 0


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


def merge_elements(cfg: dict) -> dict:
    user = cfg.get("elements") or {}
    merged: dict = {}
    for name, defaults in DEFAULT_ELEMENTS.items():
        merged[name] = {**defaults, **(user.get(name) or {})}
    for name, el in user.items():
        if name not in merged:
            merged[name] = el
    out = dict(cfg)
    out["elements"] = merged
    return out


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return merge_elements(json.load(f))


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


def estimate_content_width(
    enabled: list[tuple[str, dict]], spacing: int, *, label_px: int = 22
) -> int:
    total = 0
    for i, (_name, el_cfg) in enumerate(enabled):
        if i:
            total += spacing
        if el_cfg.get("show_label", True):
            total += label_px
        total += int(el_cfg.get("graph_width", 100))
    return total


def output_width() -> int:
    display = Gdk.Display.get_default()
    if not display:
        return 1920
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    return monitor.get_geometry().width if monitor else 1920


def output_scale() -> int:
    display = Gdk.Display.get_default()
    if not display:
        return 1
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    return int(monitor.get_scale_factor()) if monitor else 1


def screen_origin(gdk_win) -> tuple[int, int]:
    """GTK3 get_origin() is (ok, x, y); some bindings return (x, y)."""
    if gdk_win is None:
        return -1, -1
    result = gdk_win.get_origin()
    if len(result) == 3:
        _ok, x, y = result
        return int(x), int(y)
    if len(result) == 2:
        return int(result[0]), int(result[1])
    return -1, -1


def apply_layer_placement(
    win: Gtk.Window,
    cfg: dict,
    *,
    bar_height: int,
    content_width: int,
) -> None:
    """Must run before the window is realized (gtk-layer-shell requirement)."""
    # Sway insets top-anchored layer surfaces by Waybar's exclusive zone.
    # Default: pull up by bar_height. Optional override for padding mismatch.
    if "layer_shell_margin_top" in cfg:
        margin_top = int(cfg["layer_shell_margin_top"])
        if margin_top == 0:
            margin_top = -bar_height
    else:
        margin_top = -bar_height
    margin_h = max(0, (output_width() - content_width) // 2)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.BOTTOM, False)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, True)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.RIGHT, True)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, margin_top)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.BOTTOM, 0)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, margin_h)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.RIGHT, margin_h)
    win.set_size_request(content_width, bar_height)


def log_window_placement(win: Gtk.Window) -> bool:
    if not os.environ.get("SYSTEM_MONITOR_SWAY_DEBUG"):
        return False
    alloc = win.get_allocation()
    ox, oy = screen_origin(win.get_window())
    is_layer = bool(GtkLayerShell and GtkLayerShell.is_layer_window(win))
    sys.stderr.write(
        f"debug: layer_window={is_layer} screen=({ox},{oy}) "
        f"size={alloc.width}x{alloc.height}\n"
    )
    if not is_layer:
        sys.stderr.write(
            "debug: not a layer-shell surface — Sway treats it as a normal window "
            "and places it below Waybar (top of the workspace).\n"
        )
    elif oy > 5:
        sys.stderr.write(
            f"debug: screen y={oy} should be 0 for a top-anchored layer surface.\n"
        )
    return False


def build_window(cfg: dict) -> Gtk.Window:
    if not HAS_LAYER:
        sys.stderr.write(layer_shell_install_help())
        sys.exit(1)

    bar_height = int(cfg.get("bar_height", 30))
    chart_height = bar_height
    spacing = int(cfg.get("element_spacing", 4))
    default_width = int(cfg.get("graph_width", 100))
    bg = parse_color(cfg.get("background", "#ffffff16"))
    elements_cfg = cfg.get("elements", {})
    known = set(COLLECTOR_CLASSES) | {"thermal", "fan"}
    enabled = [
        (
            name,
            {
                **elements_cfg[name],
                "graph_width": int(elements_cfg[name].get("graph_width", default_width)),
            },
        )
        for name in sorted(
            elements_cfg,
            key=lambda n: int(elements_cfg[n].get("position", 99)),
        )
        if elements_cfg[name].get("display", True) and name in known
    ]
    content_width = estimate_content_width(enabled, spacing)

    supported = getattr(GtkLayerShell, "is_supported", lambda: True)()
    if not supported:
        sys.stderr.write(
            "gtk-layer-shell is not supported in this session "
            "(need Wayland + wlr-layer-shell). The window would appear in the "
            "workspace below Waybar.\n"
        )
        sys.exit(1)

    win = Gtk.Window()
    win.set_title("system-monitor-sway")
    win.set_decorated(False)
    win.set_resizable(False)
    win.set_app_paintable(True)

    # gtk-layer-shell: init + anchors before realize/show, or GTK maps an
    # xdg-toplevel and Sway puts it in the usable area (below Waybar).
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
    try:
        GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
    except (AttributeError, TypeError):
        try:
            GtkLayerShell.set_keyboard_interactivity(win, False)
        except (AttributeError, TypeError):
            pass

    apply_layer_placement(win, cfg, bar_height=bar_height, content_width=content_width)
    if os.environ.get("SYSTEM_MONITOR_SWAY_DEBUG"):
        margin = getattr(GtkLayerShell, "get_margin", lambda *_: "?")(
            win, GtkLayerShell.Edge.TOP
        )
        sys.stderr.write(
            f"debug: after init layer_window={GtkLayerShell.is_layer_window(win)} "
            f"GDK_BACKEND={os.environ.get('GDK_BACKEND')!r} margin_top={margin}\n"
        )

    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )

    scale = output_scale()
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    outer.get_style_context().add_class("sm-bar")
    outer.set_size_request(-1, bar_height)
    outer.set_vexpand(False)
    inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)
    inner.set_halign(Gtk.Align.CENTER)
    inner.set_valign(Gtk.Align.CENTER)
    inner.set_vexpand(False)
    outer.pack_start(inner, False, False, 0)
    win.add(outer)

    show_tooltip = bool(cfg.get("show_tooltip", True))
    tooltip_delay_ms = int(cfg.get("tooltip_delay_ms", 1000))
    for name, el_cfg in enabled:
        el = MonitorElement(
            name,
            el_cfg,
            chart_height,
            bg,
            float(scale),
            show_tooltip=show_tooltip,
            tooltip_delay_ms=tooltip_delay_ms,
        )
        inner.pack_start(el, False, False, 0)

    outer.set_size_request(content_width, bar_height)

    win.connect("map-event", lambda *_: GLib.idle_add(log_window_placement, win))
    win.show_all()
    sys.stderr.write(
        f"system-monitor-sway: bar_height={bar_height} width={content_width} "
        f"layer={layer_name}\n"
    )
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
        cpu_tip = format_cpu_tip([10.0, 5.0, 0.0, 2.0, 3.0])
        assert "user  10 %" in cpu_tip and "iowait  2 %" in cpu_tip
        mem_tip = format_mem_tip([0.35, 0.05, 0.2])
        assert "program  35 %" in mem_tip
        net_tip = format_net_tip([512.0, 0.0, 2048.0, 0.0, 0.0])
        assert "KiB/s" in net_tip and "MiB/s" in net_tip
        assert "used  40 %" in format_swap_tip([0.4])
        assert "MiB/s" in format_disk_tip([1.2, 8.0])
        assert format_freq_tip([2400.0]) == "2400 MHz"
        assert format_thermal_tip([45.0]) == "45 °C"
        hot = ThermalCollector(fahrenheit_unit=True)
        assert format_thermal_tip([45.0], hot) == "113 °F"
        fan = FanCollector()
        fan.rpm = 2100
        assert format_fan_tip([210.0], fan) == "2100 rpm"
        gpu = GpuCollector()
        gpu.percentage, gpu.mem, gpu.total = 20, 1024, 4096
        gpu_tip = format_gpu_tip([], gpu)
        assert "used  20 %" in gpu_tip and "1024 / 4096" in gpu_tip
        batt = BatteryCollector()
        batt.time_string = "1:05"
        batt_tip = format_battery_tip([87.0], batt)
        assert "87 %" in batt_tip and "1:05" in batt_tip
        assert millidegree_c(45000) == 45
        assert abs(disk_rate(8192, 1.0) - 1.0) < 1e-9
        assert gpu_chart_vals(20, 1024, 4096) == [20.0, 5.0]
        assert gpu_chart_vals(0, 0, 0) == [0.0, 0.0]
        swap_s = SwapCollector().sample()
        assert len(swap_s) == 1 and 0 <= swap_s[0] <= 1
        disk_s = DiskCollector().sample()
        assert len(disk_s) == 2
        freq_s = FreqCollector().sample()
        assert len(freq_s) == 1 and freq_s[0] >= 0
        therm_s = ThermalCollector().sample()
        assert len(therm_s) == 1
        fan_s = FanCollector().sample()
        assert len(fan_s) == 1 and fan_s[0] >= 0
        gpu_s = GpuCollector().sample()
        assert len(gpu_s) == 2
        batt_s = BatteryCollector().sample()
        assert len(batt_s) == 1 and 0 <= batt_s[0] <= 100
        old = merge_elements({"elements": {"cpu": {"display": True}}})
        assert old["elements"]["disk"]["display"] is False
        assert old["elements"]["cpu"]["display"] is True
        print("self-check ok")
        return

    cfg_path = resolve_config_path(args.config)
    cfg = load_config(cfg_path)
    win = build_window(cfg)
    Gtk.main()


if __name__ == "__main__":
    main()
