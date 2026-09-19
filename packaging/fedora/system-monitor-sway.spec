Name:           system-monitor-sway
Version:        0.1.0
Release:        1%{?dist}
Summary:        Stacked CPU/memory/network graphs for Sway
License:        GPL-3.0-or-later
URL:            https://github.com/jberclaz/system_monitor_sway
Source0:        https://github.com/jberclaz/system_monitor_sway/archive/refs/tags/v%{version}.tar.gz
BuildArch:      noarch

Requires:       python3-gobject
Requires:       libgtop2
Requires:       gtk-layer-shell

%description
Stacked CPU, memory, network, and optional disk/swap/freq/GPU/thermal/fan/
battery graphs for Sway, matching gnome-shell-system-monitor-applet.
A small overlay sits in the center of Waybar via gtk-layer-shell.
GNOME is not required.

%prep
%autosetup -n system_monitor_sway-%{version}

%install
DESTDIR=%{buildroot} ./install.sh /usr

%files
%license LICENSE
%{_bindir}/system-monitor-sway
%{_datadir}/system-monitor-sway/config.json
# install.sh uses $PREFIX/lib (not %{_libdir}) so the libdir is /usr/lib
# on all arches; list it explicitly.
/usr/lib/system-monitor-sway/
%{_mandir}/man1/system-monitor-sway.1*

%changelog
* Fri Sep 19 2026 Jerome Berclaz - 0.1.0-1
- Initial COPR packaging (Phase 1)
