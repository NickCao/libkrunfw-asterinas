%global debug_package %{nil}
%global asterinas_commit 7861bff17133b941cf89329917033541d14813ab
%global vdso_commit 8af571775a3d3a1df3e84fc9709b9d6b160c771a
Name:           libkrunfw-asterinas
Version:        0.1.0
Release:        9%{?dist}
Summary:        Experimental Asterinas guest payload for libkrun
License:        MIT AND MPL-2.0
URL:            https://github.com/NickCao/libkrunfw-asterinas
Source0:        %{name}-%{version}.tar.gz
Source1:        asterinas-%{asterinas_commit}.tar.gz
Source2:        linux-vdso-%{vdso_commit}.tar.gz
ExclusiveArch:  x86_64
BuildRequires:  gcc
BuildRequires:  binutils
BuildRequires:  make
BuildRequires:  python3
BuildRequires:  json-c-devel
BuildRequires:  libkrun-devel >= 1.19.6
BuildRequires:  clang
BuildRequires:  git
BuildRequires:  openssl-devel
BuildRequires:  pkgconf-pkg-config
BuildRequires:  patch
# The supplied Fedora builder also installs the Rust nightly, rust-src,
# rustc-dev and llvm-tools components pinned in upstream.json.
Requires:       libkrun >= 1.19.6
Requires:       libkrun < 2
Provides:       libkrunfw-asterinas(abi) = 5
# Compatibility version for libkrun's libkrunfw >= 5.0.0 dependency.
Provides:       libkrunfw = 5.0.0
Provides:       libkrunfw%{?_isa} = 5.0.0
Obsoletes:      libkrunfw < 6
Conflicts:      libkrunfw
Provides:       bundled(asterinas) = 0.19.0

%description
A source-built Asterinas kernel wrapped in libkrunfw ABI 5. Stock libkrun enters
the kernel directly. The kernel mounts the virtiofs root and starts libkrun's
guest init without an initramfs. Includes a one-vCPU C API launcher
for testing an extracted container filesystem with Fedora's stock libkrun.
Replaces the system libkrunfw. This is an experimental payload for the
unmodified Fedora libkrun and krun packages.

%prep
%setup -q
python3 tools/fetch-sources.py --cache %{_sourcedir} --offline
tar -xf %{SOURCE1}
tar -xf %{SOURCE2}

%build
bash tools/build-kernel.sh "$PWD/asterinas-%{asterinas_commit}" "$PWD/linux_vdso-%{vdso_commit}"
%make_build CFLAGS="%{build_cflags}"

%check
%make_build check

%install
install -Dpm0755 build/libkrunfw.so.5 %{buildroot}%{_libdir}/libkrunfw.so.5
install -Dpm0755 build/run %{buildroot}%{_libexecdir}/%{name}/run
install -Dpm0755 bin/libkrunfw-asterinas-run %{buildroot}%{_bindir}/libkrunfw-asterinas-run
install -Dpm0644 build/payload/layout.json %{buildroot}%{_datadir}/%{name}/layout.json
install -Dpm0644 upstream.json %{buildroot}%{_datadir}/%{name}/upstream.json
install -Dpm0644 build/kernel-build.json %{buildroot}%{_datadir}/%{name}/kernel-build.json
install -Dpm0644 build/kernel-Cargo.lock %{buildroot}%{_datadir}/%{name}/kernel-Cargo.lock
install -Dpm0644 examples/nginx.conf %{buildroot}%{_datadir}/%{name}/nginx.conf
cp -a patches %{buildroot}%{_datadir}/%{name}/patches

%files
%license LICENSE licenses/ASTERINAS-MPL-2.0
%doc README.md
%{_bindir}/libkrunfw-asterinas-run
%{_libexecdir}/%{name}/
%{_libdir}/libkrunfw.so.5
%{_datadir}/%{name}/

%changelog
* Mon Nov 02 2026 Nick Cao <nickcao@nichi.co> - 0.1.0-9
- Remove the Podman CPU overrides after SMP checks with 4, 8 and 16 vCPUs
- Use stock krun CPU selection in examples and runtime checks

* Mon Nov 02 2026 Nick Cao <nickcao@nichi.co> - 0.1.0-8
- Discover CPUs and I/O APICs from Intel MP tables when no ACPI MADT is available
- Add a legacy reset fallback and honor the preferred serial console
- Enter Asterinas directly without a guest boot shim or generated ACPI tables

* Mon Nov 02 2026 Nick Cao <nickcao@nichi.co> - 0.1.0-7
- Make direct virtiofs root boot the only firmware path and remove the custom init
- Prepare standard device links and resolve the static gateway during kernel boot

* Mon Nov 02 2026 Nick Cao <nickcao@nichi.co> - 0.1.0-6
- Support kernel-mounted virtiofs root filesystems and the /dev/root fallback tag
- Include direct root boot firmware without the bootstrap initramfs

* Mon Nov 02 2026 Nick Cao <nickcao@nichi.co> - 0.1.0-5
- Hand off PID 1 to stock libkrun's unmodified init binary
- Expose virtio-port names in sysfs and forward libkrun's exit-status ioctl
- Supply an ACPI reset register so guest completion terminates the VM

* Mon Nov 02 2026 Nick Cao <nickcao@nichi.co> - 0.1.0-4
- Add Asterinas multiport virtio-console queues, control messages and raw ports
- Route OCI stdio through stock krun's console and named pipe ports

* Mon Nov 02 2026 Nick Cao <nickcao@nichi.co> - 0.1.0-3
- Compile the pinned Asterinas kernel and OSDK from source inside the Fedora builder
- Include source archives in the SRPM and record the kernel build provenance

* Mon Nov 02 2026 Nick Cao <nickcao@nichi.co> - 0.1.0-2
- Provide the system libkrunfw ABI and replace the stock firmware package
- Leave the unsupported multiport console unbound when booted by stock krun
- Bootstrap virtio-net and verify host HTTP access to the upstream nginx image

* Mon Nov 02 2026 Nick Cao <nickcao@nichi.co> - 0.1.0-1
- Initial prebuilt-kernel boot proof of concept
