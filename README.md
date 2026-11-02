# libkrunfw-asterinas

An x86-64 proof of concept running Asterinas with **Fedora's unmodified Podman,
crun-krun and libkrun packages**. This RPM provides `libkrunfw.so.5` and replaces
Fedora's Linux firmware package. It compiles the Asterinas kernel and its matching
OSDK from the source revision pinned in [upstream.json](upstream.json).

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
previous prebuilt PoC. It adds no console or networking patches. The installed
`/usr/share/libkrunfw-asterinas/kernel-build.json` records the source and kernel
hashes, compiler version and build settings; `kernel-Cargo.lock` records the
dependencies resolved for the generated OSDK kernel crate.

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
sudo dnf install --allowerasing ./dist/rpmbuild/RPMS/x86_64/libkrunfw-asterinas-0.1.0-3.fc44.x86_64.rpm

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

## Current limitations

Asterinas's virtio console supports one port; libkrun's default console requires
multiport negotiation. Boot code leaves that device unbound, allowing stock krun
to boot without a console. The guest bootstrap writes stdout/stderr to
`/.asterinas.log` in the container's writable layer:

```sh
rootfs=$(sudo podman mount asterinas-nginx)
sudo cat "$rootfs/.asterinas.log"
sudo podman kill asterinas-nginx
sudo podman rm asterinas-nginx
```

`podman logs`, interactive input, guest exec, graceful guest signal delivery, and
guest exit-status propagation are not implemented. A completed guest command
leaves the Podman VM running until killed. The PoC supports root guest commands,
one container at the fixed network address, and IPv4. Nginx reports unavailable
Linux AIO (`io_setup`) and continues using epoll and ordinary file I/O.

## Validation

```sh
bash tools/smoke-test.sh
bash tools/nginx-test.sh
```

Tests require rootful Podman/Docker and `/dev/kvm`. Both install the built RPM in
a disposable Fedora container. The nginx test verifies that stock libkrunfw was
removed, the packaged libkrun and krun files were not modified, a host HTTP request
returns nginx's welcome page, and that request appears in the Asterinas guest log.
Versions, image digest, response, and logs are saved under `build/nginx-*`.

`KEEP_TEST_CONTAINER=1` leaves the successful nginx test serving on host port
18080; `NGINX_TEST_PORT` changes that port. The outer privileged Fedora container
provides the test environment on a non-Fedora build host. The inner Podman
workload uses the normal capability set. These tests do not validate a native
Fedora host's SELinux policy. An outdated Debian AppArmor profile for passt can
also block a newer Fedora passt binary before the VM starts.

`make check` inside the Fedora builder verifies the firmware ABI, alignment,
unchanged ELF segments, Linux64 entry, ACPI checksums, and initramfs headers.
The direct C API smoke test checks argument preservation and nonzero exit status.

## Boot plumbing and direct launcher

The kernel's ELF load segments are flattened, including zero-filled memory.
A boot stub chooses Asterinas's Linux64 entry, supplies a single-CPU ACPI MADT,
attaches an initramfs, and preserves libkrun's root-share and network devices.
The bootstrap mounts `/dev/root` through virtio-fs and runs the OCI process config
written by stock krun. It sends an initial packet so passt can learn the static
guest's Ethernet address without a DHCP exchange.

`libkrunfw-asterinas-run ROOT COMMAND [ARG...]` remains available for direct C API
tests with an extracted, disposable root filesystem. It selects libkrun's serial
console API and explicitly disables TSI/vsock. Set `ASTERINAS_PASST_SOCKET` to an
existing passt stream socket to enable virtio-net; otherwise networking is off.
The host launcher observes `ASTERINAS_POC_EXIT=<status>` on serial output, kills
the VM, and returns that status. Workloads must not print that reserved control
line; this is not a secure process-supervision protocol.

The wrapper and bootstrap are MIT licensed; the Asterinas kernel is MPL-2.0.
The initramfs contains Fedora glibc and json-c runtime libraries, with license
notices included in the RPM. Provenance is recorded in `upstream.json` and the
generated `kernel-build.json`, `kernel-Cargo.lock`, and `layout.json`.
