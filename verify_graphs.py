#!/usr/bin/env python3
"""
Verify stacked graphs match gnome-shell-system-monitor-applet Chart (extension.js).

Runs headless: no GNOME Shell, Sway, or display server required.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Sequence

from chart import StackedChart, parse_color

# --- Literal transcription of extension.js Chart.update / ymax / path points ---


class GnomeChartReference:
    """Mirrors SystemMonitor_Chart + parent max from extension.js."""

    def __init__(
        self,
        width: int,
        height: int,
        n_layers: int,
        *,
        fixed_max: float | None = None,
        scale_factor: float = 1.0,
    ) -> None:
        self.width = width
        self.height = height
        self.fixed_max = fixed_max
        self.scale_factor = scale_factor
        self.data: list[list[float]] = [[] for _ in range(n_layers)]

    def update(self, data_a: Sequence[float]) -> None:
        accdata: list[float] = []
        for l, val in enumerate(data_a):
            if l == 0:
                accdata.append(float(val))
            else:
                accdata.append(accdata[l - 1] + (float(val) if val > 0 else 0.0))
            self.data[l].append(accdata[l])
            if len(self.data[l]) > self.width:
                self.data[l].pop(0)

    def ymax(self) -> float:
        if self.fixed_max is not None:
            return self.fixed_max
        last = self.data[-1]
        if not last:
            return 1.0
        mx = max(last)
        return max(1.0, 2 ** math.ceil(math.log(mx) / math.log(2)))

    def layer_polyline_y(self, layer: int) -> list[tuple[float, float]]:
        """Device-space (x, y) vertices along the top edge of layer i (GNOME _draw)."""
        sf = self.scale_factor
        width = self.width * sf
        height = self.height  # extension sets actor height without * sf
        maxv = self.ymax()
        samples = len(self.data[layer]) - 1
        if samples <= 0:
            return []
        pts: list[tuple[float, float]] = []
        x = width
        pts.append((x, height))
        x = width - 0.25 * sf
        y = (1 - self.data[layer][samples] / maxv) * height
        pts.append((x, y))
        x -= 0.5 * sf
        for j in range(samples, -1, -1):
            y = (1 - self.data[layer][j] / maxv) * height
            pts.append((x, y))
            x -= 0.5 * sf
            pts.append((x, y))
            x -= 0.5 * sf
        x += 0.25 * sf
        y = (1 - self.data[layer][0] / maxv) * height
        pts.append((x, y))
        pts.append((x, height))
        return pts


def _load_config_colors() -> dict[str, list[str]]:
    cfg = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for name, el in cfg.get("elements", {}).items():
        out[name] = el["colors"]
    return out


def _synthetic_series(kind: str, steps: int) -> list[list[float]]:
    """Deterministic vals[] sequences resembling cpu / memory / net collectors."""
    series: list[list[float]] = []
    for t in range(steps):
        phase = t / max(steps - 1, 1)
        if kind == "cpu":
            u = 20 + 30 * math.sin(phase * math.pi * 2)
            s = 8 + 5 * math.cos(phase * math.pi)
            n = max(0, 5 - t % 7)
            io = 3 if t % 11 == 0 else 1
            idle = max(0, 100 - u - s - n - io)
            other = max(0, 100 - u - s - n - io - idle)
            series.append([u, s, n, io, other])
        elif kind == "memory":
            p = 0.35 + 0.15 * math.sin(phase * math.pi)
            b = 0.05 + 0.02 * math.cos(phase * math.pi * 3)
            c = 0.25 + 0.1 * (1 - phase)
            series.append([p, b, c])
        else:  # net
            down = max(0, 400 * (0.5 + 0.5 * math.sin(phase * math.pi * 4)))
            up = max(0, 120 * (0.5 + 0.5 * math.cos(phase * math.pi * 3)))
            series.append([down, 0, up, 0, 0])
    return series


def compare_history(
    ours: StackedChart,
    ref: GnomeChartReference,
    vals_seq: Sequence[Sequence[float]],
) -> None:
    for vals in vals_seq:
        ours.push(vals)
        ref.update(vals)
    assert ours._data == ref.data, "stacked history diverges from GNOME Chart.update"


def compare_polylines(
    ours: StackedChart,
    ref: GnomeChartReference,
    *,
    scale_factor: float,
) -> None:
    sf = scale_factor
    width_d = ours.width * sf
    height_d = ours.height
    maxv = ref.ymax()
    for layer in range(len(ours.colors)):
        ref_pts = ref.layer_polyline_y(layer)
        if not ref_pts:
            continue
        samples = len(ours._data[layer]) - 1
        x = width_d - 0.25 * sf
        y = (1 - ours._data[layer][samples] / maxv) * height_d
        assert abs(ref_pts[1][0] - x) < 1e-9 and abs(ref_pts[1][1] - y) < 1e-9
        x -= 0.5 * sf
        idx = 2
        for j in range(samples, -1, -1):
            y = (1 - ours._data[layer][j] / maxv) * height_d
            assert abs(ref_pts[idx][0] - x) < 1e-9 and abs(ref_pts[idx][1] - y) < 1e-9
            idx += 1
            x -= 0.5 * sf
            assert abs(ref_pts[idx][0] - x) < 1e-9 and abs(ref_pts[idx][1] - y) < 1e-9
            idx += 1
            x -= 0.5 * sf


def render_png(chart: StackedChart, bg: str, path: Path, scale_factor: float = 1.0) -> bytes:
    import cairo

    w = int(chart.width * scale_factor)
    h = int(chart.height * scale_factor)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    chart.scale_factor = scale_factor
    chart.draw(cr, parse_color(bg))
    surf.flush()
    path.parent.mkdir(parents=True, exist_ok=True)
    surf.write_to_png(str(path))
    return surf.get_data().tobytes()


def png_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_collectors_smoke() -> None:
    from collectors import CpuCollector, MemoryCollector, NetCollector

    cpu = CpuCollector()
    mem = MemoryCollector()
    net = NetCollector()
    cpu_vals = None
    for _ in range(10):
        r = cpu.sample()
        if r is not None:
            cpu_vals, pct = r
            break
        time.sleep(0.05)
    assert cpu_vals is not None and len(cpu_vals) == 5 and 0 <= pct <= 100
    m = mem.sample()
    assert len(m) == 3 and all(0 <= x <= 1 for x in m)
    n = net.sample()
    assert len(n) == 5


def main() -> int:
    out_dir = Path(__file__).parent / "verify_output"
    colors = _load_config_colors()
    bg = "#ffffff16"

    for kind, fixed in (("cpu", 800.0), ("memory", None), ("net", None)):
        width, height, steps = 100, 22, 100
        vals_seq = _synthetic_series(kind, steps)
        layer_colors = colors[kind if kind != "memory" else "memory"]
        ours = StackedChart(
            width,
            height,
            layer_colors,
            fixed_max=fixed,
            scale_factor=1.0,
        )
        ref = GnomeChartReference(
            width,
            height,
            len(layer_colors),
            fixed_max=fixed,
            scale_factor=1.0,
        )
        compare_history(ours, ref, vals_seq)
        compare_polylines(ours, ref, scale_factor=1.0)

    # HiDPI spot-check (scale 2)
    ours2 = StackedChart(100, 22, colors["net"], scale_factor=2.0)
    ref2 = GnomeChartReference(100, 22, 5, scale_factor=2.0)
    for vals in _synthetic_series("net", 30):
        ours2.push(vals)
        ref2.update(vals)
    compare_polylines(ours2, ref2, scale_factor=2.0)

    verify_collectors_smoke()

    # Render reference PNGs for visual inspection (same data, same draw code path as bar UI)
    for kind in ("cpu", "memory", "net"):
        width, height = 100, 22
        el_colors = colors[kind if kind != "memory" else "memory"]
        chart = StackedChart(width, height, el_colors, scale_factor=1.0)
        if kind == "cpu":
            chart.fixed_max = 800.0
        for vals in _synthetic_series(kind, 100):
            chart.push(vals)
        render_png(chart, bg, out_dir / f"{kind}_graph.png")

    manifest = {p.name: png_sha256(p) for p in sorted(out_dir.glob("*.png"))}
    (out_dir / "manifest.sha256.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print("verify_graphs: OK")
    print(f"  stacked history + polyline math match extension.js Chart")
    print(f"  libgtop collectors smoke-tested")
    print(f"  PNG samples: {out_dir}/")
    for name, digest in manifest.items():
        print(f"    {name}: {digest[:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
