# Packaging (Phase 1)

Single source of truth for the version: `__version__` in
`system_monitor_sway.py` (mirrored in `pyproject.toml`,
`packaging/aur/PKGBUILD`, `packaging/fedora/*.spec`, man page header).
Bump all of them together when tagging `vX.Y.Z`.

## Arch Linux (AUR)

Template lives in `packaging/aur/` (`PKGBUILD` + `.SRCINFO`).
To publish/update the real AUR repo:

```bash
git clone ssh://aur@aur.archlinux.org/system-monitor-sway.git aur-out
cp packaging/aur/PKGBUILD packaging/aur/.SRCINFO aur-out/
cd aur-out
# refresh checksums + .SRCINFO on an Arch machine:
makepkg --printsrcinfo > .SRCINFO
makepkg -si   # builds and installs locally
git add PKGBUILD .SRCINFO && git commit -m "v0.1.0" && git push
```

Users then install with any AUR helper:

```bash
yay -S system-monitor-sway
```

## Fedora (COPR)

Spec lives in `packaging/fedora/system-monitor-sway.spec`
(`BuildArch: noarch`, pure Python).

```bash
# local smoke test (needs rpmbuild):
rpmbuild -ba packaging/fedora/system-monitor-sway.spec
# COPR web UI or CLI:
copr-cli create system-monitor-sway --chroot fedora-43-x86_64 --chroot fedora-44-x86_64
copr-cli build system-monitor-sway --now packaging/fedora/system-monitor-sway.spec
```

Users enable with:

```bash
sudo dnf copr enable <you>/system-monitor-sway
sudo dnf install system-monitor-sway
```

## PyPI / pipx (all distros)

System GIR libraries are still required first (see README §1),
then:

```bash
pipx install system-monitor-sway
# or
pip install system-monitor-sway
```

Build artifacts locally:

```bash
python3 -m build
twine check dist/*
```

## Debian/Ubuntu (deferred to Phase 2)

Not shipped yet on purpose: Sway users skew Arch/Fedora, and
hand-rolled `.deb`s add signing/hosting toil. When demand proves out,
generate from the same tree via Open Build Service or `nfpm`
rather than maintaining `debian/` by hand.
