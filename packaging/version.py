#!/usr/bin/env python3
# Copyright (C) 2026 Jerome Berclaz
# SPDX-License-Identifier: GPL-3.0-or-later
"""Single source of truth for the release version: the git tag.

Truth hierarchy: `git describe` > VERSION file > 0.0.0-dev.
Distro formats (PKGBUILD / .SRCINFO / .spec) require static version
strings and build from tarballs without .git, so they are *stamped*
from the tag instead of hand-edited:

    python3 packaging/version.py            # print canonical version
    python3 packaging/version.py check      # exit 1 if stamps disagree
    python3 packaging/version.py sync       # stamp tag version into distro files
    python3 packaging/version.py bump 0.2.0 # create tag v0.2.0 (push it yourself)
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
PKGBUILD = ROOT / "packaging" / "aur" / "PKGBUILD"
SRCINFO = ROOT / "packaging" / "aur" / ".SRCINFO"
SPEC = ROOT / "packaging" / "fedora" / "system-monitor-sway.spec"

VERSION_RE = re.compile(r"^[0-9][0-9A-Za-z.+-]*$")
TAG_RE = re.compile(r"^v(\d[\dA-Za-z.]*?)(?:-(\d+)-g([0-9a-f]+))?$")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def describe() -> str | None:
    """Raw `git describe` output, or None without git metadata."""
    try:
        proc = subprocess.run(
            ["git", "describe", "--tags", "--match", "v[0-9]*"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def canonical() -> str:
    """Display version: tag without `v`, `-N-gSHA` as `+N.gSHA`."""
    desc = describe()
    if desc is None:
        try:
            return read(VERSION_FILE).strip()
        except OSError:
            return "0.0.0-dev"
    m = TAG_RE.match(desc)
    if not m:
        return desc.lstrip("v")
    base, dist, _sha = m.groups()
    if not dist:
        return base
    return f"{base}+{dist}.g{_sha}"


def base_version() -> str:
    """X.Y.Z part of the canonical version (no local suffix)."""
    return canonical().split("+", 1)[0]


def rpm_release() -> str:
    """RPM Release with commit distance: 1 / 1.3.gc09a55d."""
    desc = describe()
    if desc is None:
        return "1%{?dist}"
    m = TAG_RE.match(desc)
    if not m or not m.group(2):
        return "1%{?dist}"
    return f"1.{m.group(2)}.g{m.group(3)}%{{?dist}}"


def collected() -> list[tuple[str, str, str]]:
    """(file, found value, expected value) for every static restatement."""
    srcinfo = read(SRCINFO)
    pkgbuild = read(PKGBUILD)
    items: list[tuple[str, str, str]] = []
    base = base_version()
    for v in re.findall(r"^pkgver=(\S+)", pkgbuild, re.M):
        items.append(("packaging/aur/PKGBUILD:pkgver", v, base))
    for v in re.findall(r"refs/tags/v([\d.]+)\.tar\.gz", pkgbuild + srcinfo):
        items.append(("tarball tag ref", v, base))
    for v in re.findall(r"system-monitor-sway-([\d.]+)\.tar\.gz", srcinfo):
        items.append(("tarball file ref", v, base))
    for v in re.findall(r"^\tpkgver = (\S+)", srcinfo, re.M):
        items.append(("packaging/aur/.SRCINFO:pkgver", v, base))
    for v in re.findall(r"^Version:\s+(\S+)", read(SPEC), re.M):
        items.append(("fedora .spec Version", v, base))
    return items


def cmd_check() -> int:
    items = collected()
    if not items:
        print("no version stamps found!")
        return 1
    bad = False
    for where, found, want in items:
        ok = found == want
        print(f"{where}: {found} (want {want}) [{'ok' if ok else 'MISMATCH'}]")
        bad = bad or not ok
    print(f"canonical: {canonical()} (tag: {describe() or 'none'})")
    return 1 if bad else 0


def _sub(path: Path, pattern: str, repl: str, *, count: int = 1) -> None:
    text = read(path)
    new, n = re.subn(pattern, repl, text, count=count, flags=re.M)
    assert n == count, f"{path}: pattern {pattern!r} matched {n}x, expected {count}x"
    path.write_text(new, encoding="utf-8")


def cmd_sync() -> int:
    """Stamp the tag-derived version into the static distro files."""
    base, release = base_version(), rpm_release()
    _sub(PKGBUILD, r"^pkgver=\S+", f"pkgver={base}")
    _sub(SRCINFO, r"(?<=pkgver = )[^\s]+", base)
    _sub(SRCINFO, r"(?<=system-monitor-sway-)[\d.]+(?=\.tar\.gz)", base)
    _sub(SRCINFO, r"(?<=refs/tags/v)[\d.]+(?=\.tar\.gz)", base)
    _sub(SPEC, r"^Version:\s+\S+", f"Version:        {base}")
    _sub(SPEC, r"^Release:\s+\S+", f"Release:        {release}")
    spec_text = read(SPEC)
    if not re.search(rf"^%changelog\n\* \S+ \S+ \d+ \d+ .* - {re.escape(base)}-",
                     spec_text, re.M):
        today = time.strftime("%a %b %d %Y")
        _sub(
            SPEC,
            r"(?<=%changelog\n)",
            f"* {today} Jerome Berclaz - {base}-1\n- Release {base}\n\n",
        )
    print(f"stamped {base} (release {release})")
    return 0


def cmd_bump(version: str) -> int:
    """Create tag v<version>. Push separately; CI stamps from the tag."""
    if not VERSION_RE.match(version):
        print(f"refusing odd version: {version!r}")
        return 1
    tag = f"v{version}"
    proc = subprocess.run(["git", "rev-parse", tag], cwd=ROOT,
                          capture_output=True, check=False)
    if proc.returncode == 0:
        print(f"tag {tag} already exists")
        return 1
    proc = subprocess.run(["git", "tag", "-m", f"Release {version}", tag],
                          cwd=ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        print(f"failed to create tag {tag}: {proc.stderr.strip()}")
        return 1
    print(f"created tag {tag}; push with: git push origin {tag}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 1:
        print(canonical())
        return 0
    if argv[1] == "check":
        return cmd_check()
    if argv[1] == "sync":
        return cmd_sync()
    if argv[1] == "bump" and len(argv) == 3:
        return cmd_bump(argv[2])
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
