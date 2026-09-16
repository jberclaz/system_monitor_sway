# Copyright (C) 2026 Jerome Berclaz
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Stacked area charts matching gnome-shell-system-monitor-applet Chart._draw."""

from __future__ import annotations

import math
from typing import Sequence


def parse_color(spec: str) -> tuple[float, float, float, float]:
    s = spec.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 8:
        r, g, b, a = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16)
        return r / 255, g / 255, b / 255, a / 255
    if len(s) == 6:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        return r / 255, g / 255, b / 255, 1.0
    raise ValueError(f"unsupported color: {spec!r}")


class StackedChart:
    def __init__(
        self,
        width: int,
        height: int,
        colors: Sequence[str],
        *,
        fixed_max: float | None = None,
        scale_factor: float = 1.0,
    ) -> None:
        self.width = width
        self.height = height
        self.colors = [parse_color(c) for c in colors]
        self.fixed_max = fixed_max
        self.scale_factor = scale_factor
        self._data: list[list[float]] = [[] for _ in colors]

    def push(self, vals: Sequence[float]) -> None:
        if len(vals) != len(self.colors):
            return
        acc: list[float] = []
        for layer, value in enumerate(vals):
            prev = acc[layer - 1] if layer else float(value)
            if layer:
                prev = acc[layer - 1] + (float(value) if value > 0 else 0.0)
            acc.append(prev)
            self._data[layer].append(prev)
            if len(self._data[layer]) > self.width:
                self._data[layer].pop(0)

    def draw(self, cr, bg_rgba: tuple[float, float, float, float]) -> None:
        width = self.width * self.scale_factor
        height = self.height * self.scale_factor
        cr.save()
        cr.scale(self.scale_factor, self.scale_factor)
        logical_w, logical_h = self.width, self.height

        if self.fixed_max is not None:
            ymax = self.fixed_max
        else:
            ymax = max(self._data[-1]) if self._data[-1] else 1.0
            ymax = max(1.0, 2 ** math.ceil(math.log(max(ymax, 1e-9)) / math.log(2)))

        cr.set_source_rgba(*bg_rgba)
        cr.rectangle(0, 0, logical_w, logical_h)
        cr.fill()

        # GNOME Chart._draw uses device pixels; cr.scale(sf) => subtract 0.25/0.5 in logical px.
        sf = self.scale_factor
        for i in range(len(self.colors) - 1, -1, -1):
            samples = len(self._data[i]) - 1
            if samples <= 0:
                continue
            cr.move_to(logical_w, logical_h)
            x = logical_w - 0.25
            cr.line_to(x, (1 - self._data[i][samples] / ymax) * logical_h)
            x -= 0.5
            for j in range(samples, -1, -1):
                y = (1 - self._data[i][j] / ymax) * logical_h
                cr.line_to(x, y)
                x -= 0.5
                cr.line_to(x, y)
                x -= 0.5
            x += 0.25
            cr.line_to(x, (1 - self._data[i][0] / ymax) * logical_h)
            cr.line_to(x, logical_h)
            cr.close_path()
            cr.set_source_rgba(*self.colors[i])
            cr.fill()
        cr.restore()


def _self_check() -> None:
    c = StackedChart(10, 10, ["#ff0000", "#00ff00"], fixed_max=100)
    c.push([10, 5])
    c.push([20, 0])
    assert len(c._data[0]) == 2
    rgba = parse_color("#ffffff16")
    assert rgba[3] < 0.2


if __name__ == "__main__":
    _self_check()
    print("chart self-check ok")
