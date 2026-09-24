Name:           system-monitor-sway
Version:        0.1.0
Release:        1%{?dist}
Summary:        Stacked CPU/memory/network graphs for Sway
License:        GPL-3.0-or-later
URL:            https://github.com/jberclaz/system_monitor_sway
Source0:        https://github.com/jberclaz/system_monitor_sway/archive/refs/tags/v%{version}.tar.gz
# Arch-dependent: ships the compiled Waybar CFFI module (cffi/waybar_sysmon.so).
BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  pkgconf-pkg-config
BuildRequires:  gtk3-devel

Requires:       gtk3
Requires:       waybar

%description
Stacked CPU/memory/network graphs drawn directly inside Waybar as a
native CFFI module, matching gnome-shell-system-monitor-applet.

%prep
%autosetup -n system_monitor_sway-%{version}

%install
DESTDIR=%{buildroot} ./install.sh /usr

%files
%license LICENSE
%{_datadir}/system-monitor-sway/waybar-config-example.jsonc
# install.sh uses $PREFIX/lib (not %{_libdir}) so the libdir is /usr/lib
# on all arches; list it explicitly.
%{_mandir}/man1/waybar-sysmon.1*
/usr/lib/system-monitor-sway/

%changelog
* Fri Sep 19 2026 Jerome Berclaz - 0.1.0-1
- Initial COPR packaging (Phase 1)
