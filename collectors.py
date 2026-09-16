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
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import gi

gi.require_version("GTop", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import GLib, GTop

THERMAL_SENSOR_DEFAULT = "/sys/devices/virtual/thermal/thermal_zone0/temp"
FAN_SENSOR_DEFAULT = "/sys/devices/virtual/thermal/cooling_device0/cur_state"


def millidegree_c(raw: int) -> int:
    return round(raw / 1000)


def disk_rate(sector_delta: float, dt_s: float) -> float:
    """GNOME Disk.refresh: sectors/s / 1024 / 8 (labeled MiB/s)."""
    if dt_s <= 0:
        return 0.0
    return sector_delta / dt_s / 1024.0 / 8.0


def gpu_chart_vals(percentage: float, mem: float, total: float) -> list[float]:
    """Utilization and leftover memory-% so Chart layers do not accumulate."""
    if total == 0:
        return [0.0, 0.0]
    return [float(percentage), mem / total * 100.0 - percentage]


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def _read_int(path: str) -> int | None:
    raw = _read_text(path)
    if raw is None:
        return None
    try:
        return int(raw.split()[0], 10)
    except ValueError:
        return None


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


@dataclass
class SwapCollector:
    _gtop: object = field(default_factory=GTop.glibtop_swap, init=False)
    percent: int = 0

    def sample(self) -> list[float]:
        GTop.glibtop_get_swap(self._gtop)
        total = self._gtop.total
        if total == 0:
            self.percent = 0
            return [0.0]
        used = self._gtop.used / total
        self.percent = round(used * 100)
        return [used]

    @property
    def chart_max(self) -> float:
        return 1.0


@dataclass
class DiskCollector:
    _last: list[int] = field(default_factory=lambda: [0, 0], init=False)
    _last_time: float = 0.0
    usage: list[float] = field(default_factory=lambda: [0.0, 0.0], init=False)

    def sample(self) -> list[float]:
        accum = [0, 0]
        try:
            with open("/proc/diskstats", encoding="utf-8") as f:
                for line in f:
                    entry = line.split()
                    if len(entry) < 10:
                        continue
                    accum[0] += int(entry[5])
                    accum[1] += int(entry[9])
        except (OSError, ValueError):
            return list(self.usage)
        t = GLib.get_monotonic_time() / 1000.0
        delta = (t - self._last_time) / 1000.0
        if self._last_time > 0 and delta > 0:
            self.usage = [
                disk_rate(accum[0] - self._last[0], delta),
                disk_rate(accum[1] - self._last[1], delta),
            ]
        self._last = accum
        self._last_time = t
        return list(self.usage)


@dataclass
class FreqCollector:
    freq: int = 0

    def sample(self) -> list[float]:
        try:
            ncpu = int(GTop.glibtop_get_sysinfo().ncpu)
        except Exception:
            ncpu = 1
        total = 0
        counted = 0
        for i in range(max(ncpu, 1)):
            khz = _read_int(f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq")
            if khz is None:
                continue
            total += khz
            counted += 1
        self.freq = round(total / counted / 1000) if counted else 0
        return [float(self.freq)]


@dataclass
class ThermalCollector:
    sensor_file: str = THERMAL_SENSOR_DEFAULT
    fahrenheit_unit: bool = False
    temperature: int = 0
    _logged_missing: bool = False

    def sample(self) -> list[float]:
        raw = _read_int(self.sensor_file)
        if raw is None:
            if not self._logged_missing:
                sys.stderr.write(f"error reading: {self.sensor_file}\n")
                self._logged_missing = True
            self.temperature = 0
        else:
            self.temperature = millidegree_c(raw)
        return [float(self.temperature)]

    @property
    def chart_max(self) -> float:
        return 100.0


@dataclass
class FanCollector:
    sensor_file: str = FAN_SENSOR_DEFAULT
    rpm: int = 0
    _logged_missing: bool = False

    def sample(self) -> list[float]:
        raw = _read_int(self.sensor_file)
        if raw is None:
            if not self._logged_missing:
                sys.stderr.write(f"error reading: {self.sensor_file}\n")
                self._logged_missing = True
            self.rpm = 0
        else:
            self.rpm = raw
        return [self.rpm / 10.0]


def _nvidia_gpu() -> tuple[int, int, int] | None:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        proc = subprocess.run(
            [
                smi,
                "-i",
                "0",
                "--query-gpu=memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    parts = [p.strip() for p in proc.stdout.replace("\n", ",").split(",") if p.strip()]
    if len(parts) < 3:
        return None
    try:
        return int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
    except ValueError:
        return None


def _amd_gpu() -> tuple[int, int, int] | None:
    base = "/sys/class/drm/card0/device"
    total_b = _read_int(f"{base}/mem_info_vram_total")
    used_b = _read_int(f"{base}/mem_info_vram_used")
    busy = _read_int(f"{base}/gpu_busy_percent")
    if total_b is None or used_b is None:
        return None
    return total_b // 1024 // 1024, used_b // 1024 // 1024, busy or 0


def _glxinfo_gpu() -> tuple[int, int, int] | None:
    glx = shutil.which("glxinfo")
    if not glx:
        return None
    try:
        proc = subprocess.run(
            [glx], capture_output=True, text=True, timeout=2, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    lines = proc.stdout.splitlines()
    total = avail = None
    for i, line in enumerate(lines):
        if "GL_NVX_gpu_memory_info" not in line:
            continue
        for extra in lines[i + 1 : i + 6]:
            low = extra.lower()
            nums = [int(t) for t in extra.replace(",", " ").split() if t.isdigit()]
            if not nums:
                continue
            if "available dedicated" in low:
                avail = nums[0]
            elif "dedicated" in low and total is None:
                total = nums[0]
        break
    if total is None or avail is None:
        return None
    return total, max(total - avail, 0), 0


@dataclass
class GpuCollector:
    mem: int = 0
    total: int = 0
    percentage: int = 0

    def sample(self) -> list[float]:
        stats = _nvidia_gpu() or _amd_gpu() or _glxinfo_gpu()
        if stats is None:
            self.total = self.mem = self.percentage = 0
            return [0.0, 0.0]
        self.total, self.mem, self.percentage = stats
        return gpu_chart_vals(self.percentage, self.mem, self.total)

    @property
    def chart_max(self) -> float:
        return 100.0


def _battery_dir() -> Path | None:
    root = Path("/sys/class/power_supply")
    if not root.is_dir():
        return None
    bats: list[Path] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return None
    for path in entries:
        kind = _read_text(str(path / "type"))
        if kind == "Battery" or path.name.startswith("BAT"):
            bats.append(path)
    return bats[0] if bats else None


def _battery_seconds(bat: Path) -> float | None:
    if _read_text(str(bat / "status")) != "Discharging":
        return None
    energy = _read_int(str(bat / "energy_now"))
    power = _read_int(str(bat / "power_now"))
    if energy is not None and power and power > 0:
        return energy / power * 3600.0
    charge = _read_int(str(bat / "charge_now"))
    current = _read_int(str(bat / "current_now"))
    if charge is not None and current and current > 0:
        return charge / current * 3600.0
    return None


@dataclass
class BatteryCollector:
    percentage: int = 0
    time_string: str = "-- "

    def sample(self) -> list[float]:
        bat = _battery_dir()
        if bat is None:
            self.percentage = 0
            self.time_string = "-- "
            return [0.0]
        cap = _read_int(str(bat / "capacity"))
        self.percentage = 0 if cap is None else max(0, min(100, cap))
        seconds = _battery_seconds(bat)
        if seconds is not None and seconds > 60:
            minutes = round(seconds / 60)
            self.time_string = f"{minutes // 60}:{minutes % 60:02d}"
        else:
            self.time_string = "-- "
        return [float(self.percentage)]
