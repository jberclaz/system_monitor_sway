# Packaging Phase 0+1 — todo

Branch: `packaging-phase01`

- [x] Phase 0: `__version__ = "0.1.0"` + `-V/--version` in `system_monitor_sway.py`
- [x] Phase 0: `pyproject.toml` (PyPI/pipx, console_scripts entry point, build verified)
- [x] Phase 0: `DESTDIR` staging support in `install.sh` + `system-monitor-sway.1` man page
- [x] Phase 1: `packaging/aur/PKGBUILD` + `.SRCINFO`
- [x] Phase 1: `packaging/fedora/system-monitor-sway.spec` (BuildArch noarch, COPR-ready)
- [x] Phase 1: `packaging/README.md` (AUR/COPR/PyPI publish instructions)
- [x] Verify: `--self-check` ok, `verify_graphs.py` ok, `python -m build` ok,
      DESTDIR staging yields bin/lib/share/man tree, man page renders

## Review

- Wheel contains `chart.py`, `collectors.py`, `system_monitor_sway.py` + entry point. Good.
- Fedora `%files` uses explicit `/usr/lib/system-monitor-sway/` because
  `install.sh` hardcodes `$PREFIX/lib` (not `%{_libdir}`). Intentional, documented in spec.
- `license-files = ["LICENSE"]` (PEP 639) instead of deprecated `license.text`.
- `dist/`, `build/`, `*.egg-info/` added to `.gitignore`; no build artifacts committed.
- NOT verified (no tools on this host): `makepkg -si`, `rpmbuild -ba`, `copr-cli build`.
  Run those on Arch/Fedora hosts before publishing. `.SRCINFO` checksums are `SKIP`
  placeholders until the `v0.1.0` tag tarball exists.

## Next (not started)

- Tag `v0.1.0`, fill real `sha256sums`, `makepkg --printsrcinfo > .SRCINFO`
- Publish AUR repo + COPR project (see `packaging/README.md`)
- Phase 2 (deferred): OBS/nfpm `.deb`/`.rpm` artifacts for Debian/Ubuntu
