# Copyright (C) 2026 Jerome Berclaz
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Sample system stats using the same sources as the GNOME extension (libgtop + /proc)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import gi

gi.require_version("GTop", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import GLib, GTop


def _monotonic_ms() -> float:
    return GLib.get_monotonic_time() * 0.001024


def _active_net_ifaces() -> list[str]:
    ifaces: list[str] = []
    try:
        with open("/proc/net/dev", encoding="utf-8") as f:
            lines = f.readlines()[2:]
        for line in lines:
            if ":" not in line:
                continue
            name = line.split(":", 1)[0].strip()
            if name.startswith("lo") or name.startswith("br"):
                continue
            oper = f"/sys/class/net/{name}/operstate"
            if os.path.isfile(oper):
                with open(oper, encoding="utf-8") as op:
                    if op.read().strip() != "up":
                        continue
            ifaces.append(name)
    except OSError:
        pass
    return ifaces


@dataclass
class CpuCollector:
    total_cores: int = field(init=False)
    _gtop: object = field(default_factory=GTop.glibtop_cpu, init=False)
    _last: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0], init=False)
    usage: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0], init=False)
    _have_last: bool = False

    def __post_init__(self) -> None:
        try:
            self.total_cores = GTop.glibtop_get_sysinfo().ncpu
        except Exception:
            self.total_cores = 1

    def _read_counters(self) -> list[int]:
        GTop.glibtop_get_cpu(self._gtop)
        return [
            self._gtop.user,
            self._gtop.sys,
            self._gtop.nice,
            self._gtop.idle,
            self._gtop.iowait,
        ]

    def sample(self) -> tuple[list[float], int] | None:
        cur = self._read_counters()
        if not self._have_last:
            self._last = cur
            self._have_last = True
            return None

        delta = sum(cur[i] - self._last[i] for i in range(5))
        if delta <= 0:
            return None

        for i in range(5):
            self.usage[i] = round(100 * (cur[i] - self._last[i]) / delta)
        self._last = cur

        percent = round(100 - self.usage[3])
        other = 100
        for u in self.usage:
            other -= u
        other = max(0, other)
        vals = [
            float(self.usage[0]),
            float(self.usage[1]),
            float(self.usage[2]),
            float(self.usage[4]),
            float(other),
        ]
        return vals, percent

    @property
    def chart_max(self) -> float:
        return 100.0


@dataclass
class MemoryCollector:
    _gtop: object = field(default_factory=GTop.glibtop_mem, init=False)
    percent: int = 0

    def sample(self) -> list[float]:
        GTop.glibtop_get_mem(self._gtop)
        total = self._gtop.total
        if total == 0:
            self.percent = 0
            return [0.0, 0.0, 0.0]
        user = self._gtop.user / total
        buf = self._gtop.buffer / total
        cached = self._gtop.cached / total
        self.percent = round(user * 100)
        return [user, buf, cached]


@dataclass
class NetCollector:
    ifaces: list[str] = field(default_factory=_active_net_ifaces)
    _gtop: object = field(default_factory=GTop.glibtop_netload, init=False)
    _last: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0], init=False)
    _last_time: float = 0.0
    usage: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0], init=False)

    def sample(self) -> list[float]:
        if not self.ifaces:
            self.ifaces = _active_net_ifaces()
        accum = [0, 0, 0, 0, 0]
        for ifn in self.ifaces:
            GTop.glibtop_get_netload(self._gtop, ifn)
            accum[0] += self._gtop.bytes_in
            accum[1] += self._gtop.errors_in
            accum[2] += self._gtop.bytes_out
            accum[3] += self._gtop.errors_out
            accum[4] += self._gtop.collisions
        t = _monotonic_ms()
        delta = t - self._last_time
        if delta > 0:
            for i in range(5):
                self.usage[i] = round((accum[i] - self._last[i]) / delta)
                self._last[i] = accum[i]
        self._last_time = t
        return [float(x) for x in self.usage]
