%global debug_package %{nil}
# This private payload must not satisfy dependencies on the system Linux firmware.
%global __provides_exclude_from ^%{_libdir}/%{name}/.*$

Name:           libkrunfw-asterinas
Version:        0.1.0
Release:        1%{?dist}
Summary:        Experimental Asterinas guest payload for libkrun
License:        MIT AND MPL-2.0 AND LGPL-2.1-or-later
URL:            https://github.com/NickCao/libkrunfw-asterinas
Source0:        %{name}-%{version}.tar.gz
# Extracted from the checksum-pinned release recorded in upstream.json.
Source1:        asterinas-7861bff17133b941cf89329917033541d14813ab.elf
ExclusiveArch:  x86_64
BuildRequires:  gcc
BuildRequires:  binutils
BuildRequires:  make
BuildRequires:  python3
BuildRequires:  json-c-devel
BuildRequires:  libkrun-devel >= 1.19.6
Requires:       libkrun >= 1.19.6
Requires:       libkrun < 2
Provides:       libkrunfw-asterinas(abi) = 5
Provides:       bundled(asterinas) = 0.19.0

%description
A prebuilt Asterinas kernel wrapped in libkrunfw ABI 5, with minimal boot
data and a guest bootstrap. Includes a one-vCPU, network-free C API launcher
for testing an extracted container filesystem with Fedora's stock libkrun.
Installs alongside the system libkrunfw without replacing it. This is a boot
proof of concept, not an OCI runtime or a general-purpose Podman backend.

%prep
%setup -q
mkdir -p build
cp %{SOURCE1} build/asterinas.elf
printf '653efaa8d1c1130d1e6f06c479acc7c32e0153f781e7a477a8cb6bfe22ee58f2  build/asterinas.elf\n' | sha256sum -c -
cp -a /usr/share/licenses/glibc licenses/guest-glibc
cp -a /usr/share/licenses/json-c licenses/guest-json-c

%build
%make_build CFLAGS="%{build_cflags}"

%check
%make_build check

%install
install -Dpm0755 build/libkrunfw.so.5 %{buildroot}%{_libdir}/%{name}/libkrunfw.so.5
install -Dpm0755 build/run %{buildroot}%{_libexecdir}/%{name}/run
install -Dpm0755 bin/libkrunfw-asterinas-run %{buildroot}%{_bindir}/libkrunfw-asterinas-run
install -Dpm0644 build/payload/layout.json %{buildroot}%{_datadir}/%{name}/layout.json
install -Dpm0644 upstream.json %{buildroot}%{_datadir}/%{name}/upstream.json

%files
%license LICENSE licenses/ASTERINAS-MPL-2.0 licenses/guest-glibc licenses/guest-json-c
%doc README.md
%{_bindir}/libkrunfw-asterinas-run
%{_libexecdir}/%{name}/
%{_libdir}/%{name}/
%{_datadir}/%{name}/

%changelog
* Mon Nov 02 2026 Nick Cao <nickcao@nichi.co> - 0.1.0-1
- Initial prebuilt-kernel boot proof of concept
