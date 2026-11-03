# libkrunfw-asterinas

An x86-64 proof of concept running Asterinas with **Fedora's unmodified Podman,
crun-krun and libkrun packages**. This RPM provides `libkrunfw.so.5` and replaces
Fedora's Linux firmware package. It compiles the Asterinas kernel and its matching
OSDK from the source revision pinned in [upstream.json](upstream.json), with the
kernel patches listed in [patches/series](patches/series).

The acceptance test runs the **unmodified `docker.io/library/nginx:stable` image**
and fetches its welcome page from the host. It uses virtio-net through passt,
with TSI disabled by libkrun's network-device configuration.

## Build RPMs in a Fedora container

```sh
bash tools/build-rpm.sh
```

All compilation and RPM assembly happen inside Fedora 44. The build host needs
Podman; `CONTAINER_ENGINE=docker` selects Docker instead. KVM is needed for tests.
The builder installs Asterinas's pinned Rust nightly with `rust-src`, `rustc-dev`,
LLVM tools and the bare-metal x86-64 target. Source archives and Cargo downloads
are cached under `.cache/`. Compilation uses two jobs by default;
`KERNEL_BUILD_JOBS` changes this for machines with more memory.

Binary RPMs are written to `dist/rpmbuild/RPMS/x86_64/`, and SRPMs to
`dist/rpmbuild/SRPMS/`. The SRPM contains the checksum-verified Asterinas source
archive, the vDSO input archive, and the wrapper source. Its build stage compiles
OSDK and the kernel inside the prepared Fedora builder; the first build needs
network access for Cargo dependencies. The vDSO archive contains upstream's
precompiled Linux vDSO libraries, which are still used as kernel build inputs.

The kernel uses the upstream development profile, the `vmm-direct` boot method,
and 64-page task stacks. This step keeps the same upstream kernel revision as the
previous prebuilt PoC. The multiport console patch is applied during both local
and RPM builds. The installed
`/usr/share/libkrunfw-asterinas/kernel-build.json` records the source and kernel
hashes, compiler version and build settings; `kernel-Cargo.lock` records the
dependencies resolved for the generated OSDK kernel crate. Patch hashes are
included in the build record, and the RPM installs the patch series alongside it.

For an incremental kernel-only build with the prepared builder:

```sh
podman run --rm -v "$PWD:/work:Z" -w /work \
    localhost/libkrunfw-asterinas-build:44 make kernel
```

Use `/work` as the mount point: upstream component registration currently breaks
when a parent path contains `src/`. The RPM build script handles this.

## Install and run nginx on Fedora

```sh
sudo dnf install podman crun-krun passt
sudo dnf install --allowerasing ./dist/rpmbuild/RPMS/x86_64/libkrunfw-asterinas-0.1.0-7.fc44.x86_64.rpm

sudo podman network create --subnet 10.0.2.0/24 --gateway 10.0.2.2 asterinas
sudo podman run -d --name asterinas-nginx --runtime /usr/bin/krun \
    --security-opt seccomp=unconfined --pid host \
    --annotation krun.cpus=1 --annotation krun.use_passt=1 \
    --network asterinas --ip 10.0.2.15 -p 8080:8080 \
    -v /usr/share/libkrunfw-asterinas/nginx.conf:/etc/nginx/conf.d/default.conf:ro,Z \
    docker.io/library/nginx:stable

curl --noproxy '*' http://127.0.0.1:8080/
```

The RPM removes stock `libkrunfw`, installs its replacement in `/usr/lib64/`, and
satisfies libkrun's firmware dependency. **Every consumer of the system firmware
will then load Asterinas.** Restore Linux firmware with:

```sh
sudo dnf swap libkrunfw-asterinas libkrunfw
```

The supplied nginx config listens on `10.0.2.15:8080`. Asterinas currently has a
fixed IPv4 address and rejects wildcard binds such as `0.0.0.0:80`; DHCP cannot
change its address yet. This bind mount supplies runtime configuration while
keeping the upstream image, executable, entrypoint, and CMD unchanged. Port 8080
also avoids privileged-port restrictions on passt's forwarding sockets.

`--pid=host` works around crun 1.28 starting passt with an inconsistent `/proc`
view. Guest processes still run inside the VM. This PoC uses one vCPU and 1 GiB
RAM; rootless operation and Fedora host SELinux enforcement are not validated.

## Console support and current limitations

The patched driver negotiates virtio-console multiport, exchanges device/port
readiness messages, and gives each port independent receive/transmit queues.
`/dev/hvc0` uses the existing TTY line discipline. Raw `/dev/vport0pN` devices
carry krun's named `krun-stdin`, `krun-stdout`, and `krun-stderr` streams without
terminal processing. Standard port names are exposed through
`/sys/class/virtio-ports/vport0pN/name`. Fedora libkrun's unmodified `/init.krun`
selects the streams and launches the OCI command. The kernel mounts the virtiofs
root and devtmpfs, supplies standard `/dev/std*` links, and starts that injected
binary directly as PID 1. There is no custom guest init or initramfs.

Container output is available through normal Podman logging:

```sh
sudo podman logs asterinas-nginx
sudo podman kill asterinas-nginx
sudo podman rm asterinas-nginx
```

The raw ports preserve host EOF and use bounded queues with readiness-based
blocking for backpressure. Console resize messages update the TTY size and
signal its foreground process group. Kernel diagnostic output is best effort
when its console queue fills, so logging cannot wait on host I/O with interrupts
disabled. The PoC supports one console and up to 32 ports per device, with ports
opened during discovery. General hotplug/reopen handling is not implemented.

Workload exit status follows libkrun's normal protocol: its init sends ioctl
`0x7602` through the virtiofs root, syncs, and resets the VM using the ACPI reset
register. The VMM exits with that status, so foreground `podman run` returns the
guest's code and the container stops normally.

`podman exec` remains unsupported by the stock krun versions used here
([upstream issue](https://github.com/containers/crun/issues/2090)). Graceful
delivery of arbitrary host signals into the guest remains outside this PoC.
Validation covers root guest commands, one container at the fixed network
address, and IPv4. Nginx reports unavailable
Linux AIO (`io_setup`) and continues using epoll and ordinary file I/O.

## Validation

```sh
bash tools/smoke-test.sh
bash tools/nginx-test.sh
```

Tests require rootful Podman/Docker and `/dev/kvm`. Both install the built RPM in
a disposable Fedora container. The nginx test verifies that stock libkrunfw was
removed, the packaged libkrun and krun files were not modified, a host HTTP request
returns nginx's welcome page, and that request appears in `podman logs`.
Versions, image digest, response, and logs are saved under `build/nginx-*`.

`KEEP_TEST_CONTAINER=1` leaves the successful nginx test serving on host port
18080; `NGINX_TEST_PORT` changes that port. The outer privileged Fedora container
provides the test environment on a non-Fedora build host. The inner Podman
workload uses the normal capability set. These tests do not validate a native
Fedora host's SELinux policy. An outdated Debian AppArmor profile for passt can
also block a newer Fedora passt binary before the VM starts.

For a small console smoke check, run `python3 tools/console-test.py CONTAINER`
with the Fedora container name printed by a retained nginx test. It checks
separate stdout/stderr, a 32 KiB binary stdin round trip and EOF, plus interactive
console input and initial terminal dimensions, and Podman exit status 7. Logs are saved under
`build/console-*`.

`make check` inside the Fedora builder verifies the firmware ABI, alignment,
unchanged ELF segments, Linux64 entry, ACPI checksums, and the absence of an initramfs.
The direct C API smoke test checks argument preservation and nonzero exit status.

## Boot plumbing and direct launcher

The kernel's ELF load segments are flattened, including zero-filled memory.
A boot stub chooses Asterinas's Linux64 entry, supplies a single-CPU ACPI MADT
and a FADT with libkrun's emulated reset register, and preserves libkrun's
root-share and network devices. The kernel mounts the `/dev/root` virtiofs tag
as its root filesystem and executes the unmodified `/init.krun` injected by
stock libkrun. That init handles the OCI process config, stdio redirection,
process supervision and exit reporting.

The kernel supplies `/dev/fd` and `/dev/std*` links before starting init. Ethernet
interface setup sends an ARP request for the configured gateway, allowing passt
to learn the static guest's Ethernet address before an inbound connection.
The boot stub removes the Linux-only TSI flag and `KRUN_DHCP` setting while
Asterinas's network configuration remains fixed. No guest bootstrap executable
or guest glibc libraries are embedded in the firmware.

`libkrunfw-asterinas-run ROOT COMMAND [ARG...]` remains available for direct C API
tests with an extracted, disposable root filesystem. It selects libkrun's serial
console API and explicitly disables TSI/vsock. Set `ASTERINAS_PASST_SOCKET` to an
existing passt stream socket to enable virtio-net; otherwise networking is off.
The host launcher relays serial output and returns the VMM process's exit code.
It uses the same upstream init and exit protocol as the Podman path.

The wrapper and boot stub are MIT licensed; the Asterinas kernel is MPL-2.0.
Provenance is recorded in `upstream.json` and the generated `kernel-build.json`,
`kernel-Cargo.lock`, and `layout.json`.

## Direct virtiofs root boot

The firmware boots directly from virtiofs without an initramfs.
With `rootfstype=virtiofs`, `root=TAG` selects a virtiofs tag rather than a block
device. If `root` is omitted, the source defaults to `/dev/root`, matching Linux's
root mount fallback and stock krun's default export tag. The kernel mounts the
share as `/`, mounts devtmpfs, and starts the program selected by `init`, normally
libkrun's injected `/init.krun`. Explicit tags must exist; `ro` and `rw` control
root write access. Ext2 root boot and initramfs init selection remain supported.

This is the default `/usr/lib64/libkrunfw.so.5` installed by the RPM. For a
console-only command using stock krun:

```sh
sudo podman run --rm --runtime /usr/bin/krun --network none \
    --security-opt seccomp=unconfined --pid host \
    docker.io/library/nginx:stable /bin/sh -c 'cat /proc/mounts; exit 7'
```

`python3 tools/rootfs-test.py CONTAINER` checks the RPM in a retained Fedora test
container: the default firmware has no initramfs, mounts root from the default
tag, supplies functioning stdio links, starts stock init, and returns exit
status 7 through Podman. Its output is saved in `build/rootfs-test.log`.
