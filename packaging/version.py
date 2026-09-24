#!/usr/bin/env python3
# Copyright (C) 2026 Jerome Berclaz
# SPDX-License-Identifier: GPL-3.0-or-later
"""Single source of truth for the release version.

The canonical version lives in the VERSION file at the repo root.
Distro formats (PKGBUILD / .SRCINFO / .spec) require static version
strings, so they restate it -- this script propagates and verifies
instead of hand-editing every file:

    python3 packaging/version.py            # print canonical version
    python3 packaging/version.py check      # exit 1 if any file disagrees
    python3 packaging/version.py bump 0.2.0 # rewrite all files + spec changelog
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
PKGBUILD = ROOT / "packaging" / "aur" / "PKGBUILD"
SRCINFO = ROOT / "packaging" / "aur" / ".SRCINFO"
SPEC = ROOT / "packaging" / "fedora" / "system-monitor-sway.spec"

VERSION_RE = re.compile(r"^[0-9][0-9A-Za-z.+-]*$")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def canonical() -> str:
    return read(VERSION_FILE).strip()


def collected() -> dict[str, list[str]]:
    """Every static restatement of the version, by file."""
    srcinfo = read(SRCINFO)
    return {
        str(PKGBUILD.relative_to(ROOT)): re.findall(r"^pkgver=(\S+)", read(PKGBUILD), re.M),
        str(SRCINFO.relative_to(ROOT)): (
            re.findall(r"^\tpkgver = (\S+)", srcinfo, re.M)
            + re.findall(r"system-monitor-sway-([\d.]+)\.tar\.gz", srcinfo)
            + re.findall(r"refs/tags/v([\d.]+)\.tar\.gz", srcinfo)
        ),
        str(SPEC.relative_to(ROOT)): re.findall(r"^Version:\s+(\S+)", read(SPEC), re.M),
    }


def cmd_check() -> int:
    want = canonical()
    if not VERSION_RE.match(want):
        print(f"VERSION file holds garbage: {want!r}")
        return 1
    bad = False
    for path, found in collected().items():
        if not found:
            print(f"{path}: no version found!")
            bad = True
        for v in found:
            status = "ok" if v == want else "MISMATCH"
            if v != want:
                bad = True
            print(f"{path}: {v} [{status}]")
    print(f"canonical (VERSION): {want}")
    return 1 if bad else 0


def _sub(path: Path, pattern: str, repl: str, *, count: int = 1) -> None:
    text = read(path)
    new, n = re.subn(pattern, repl, text, count=count, flags=re.M)
    assert n == count, f"{path}: pattern {pattern!r} matched {n}x, expected {count}x"
    path.write_text(new, encoding="utf-8")


def cmd_bump(version: str) -> int:
    if not VERSION_RE.match(version):
        print(f"refusing odd version: {version!r}")
        return 1
    (ROOT / "VERSION").write_text(version + "\n", encoding="utf-8")
    _sub(PKGBUILD, r"^pkgver=\S+", f"pkgver={version}")
    _sub(SRCINFO, r"(?<=pkgver = )[^\s]+", version)
    _sub(SRCINFO, r"(?<=system-monitor-sway-)[\d.]+(?=\.tar\.gz)", version)
    _sub(SRCINFO, r"(?<=refs/tags/v)[\d.]+(?=\.tar\.gz)", version)
    _sub(SPEC, r"^Version:\s+\S+", f"Version:        {version}")
    _sub(SPEC, r"^Release:\s+\S+", r"Release:        1%{?dist}")
    today = time.strftime("%a %b %d %Y")
    _sub(
        SPEC,
        r"(?<=%changelog\n)",
        f"* {today} Jerome Berclaz - {version}-1\n- Release {version}\n\n",
    )
    print(f"bumped to {version}; run '{sys.argv[0]} check' to verify")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 1:
        print(canonical())
        return 0
    if argv[1] == "check":
        return cmd_check()
    if argv[1] == "bump" and len(argv) == 3:
        return cmd_bump(argv[2])
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
