# libkrunfw-asterinas

A minimal x86-64 boot proof of concept using Asterinas as the guest kernel
for **Fedora's unmodified libkrun 1.19.x**. The kernel is an upstream prebuilt
artifact; only the firmware wrapper, boot data, and small launcher are built here.

The first milestone is a command running on an extracted container root filesystem,
with one vCPU, 1 GiB RAM, a serial console, and no network or TSI support.
The launcher uses libkrun's C API. It is **not an OCI runtime**, so do not pass it
to `podman --runtime`. Podman integration is a later milestone.

## Build RPMs in a Fedora container

On an x86-64 Linux build host with Podman installed:

```sh
bash tools/build-rpm.sh
```

Use `CONTAINER_ENGINE=docker` to use Docker for the build, or
`FEDORA_VERSION=44` to select the Fedora release explicitly. All compilation and
RPM assembly happen in the Fedora container. KVM is needed for boot tests only.

The build downloads and verifies the artifact pinned in [upstream.json](upstream.json).
It produces a binary RPM under `dist/rpmbuild/RPMS/x86_64/` and an SRPM under
`dist/rpmbuild/SRPMS/`. The SRPM contains the prebuilt kernel and the wrapper's
source; it is deliberately a binary-kernel repackaging PoC.

## Install and try on Fedora

```sh
sudo dnf install ./dist/rpmbuild/RPMS/x86_64/libkrunfw-asterinas-*.rpm

# Prepare a disposable root filesystem from an OCI image.
mkdir rootfs
container_id=$(podman create registry.fedoraproject.org/fedora:44)
podman export "$container_id" | tar -xf - -C rootfs
podman rm "$container_id"

sudo libkrunfw-asterinas-run "$PWD/rootfs" /bin/uname -a
```

The user running the launcher needs access to `/dev/kvm`. The RPM installs the
alternate `libkrunfw.so.5` in `/usr/lib64/libkrunfw-asterinas/`; the launcher selects
it for its own process. It does not replace the system's Linux firmware, alter
Podman's default runtime, or install a container daemon.

Use a disposable root filesystem: the guest mounts it read-write through virtio-fs.
The PoC supports non-interactive commands running as guest UID/GID 0. It does not
provide the full OCI lifecycle, networking, multiport consoles, or SMP.

## Boot plumbing

The kernel's ELF load segments are flattened, including zero-filled memory.
The wrapper chooses Asterinas's **Linux64** entry instead of its 32-bit ELF entry.
A short boot stub supplies a single-CPU ACPI MADT, preserves libkrun's device and
command arguments, and attaches an initramfs. Its guest bootstrap mounts libkrun's
`/dev/root` virtio-fs share and executes the requested command.

Asterinas's current single-port virtio console does not complete libkrun's multiport
handshake. The launcher therefore selects the existing libkrun serial-console API.
It disables the implicit vsock device, so TSI kernel patches are not needed.

The host observes the guest's `ASTERINAS_POC_EXIT=<status>` serial line, terminates
the VM, and returns that status. This is a reserved PoC control line, not a secure
or general-purpose process supervision protocol; workloads must not print it.
Stock libkrun's virtio-fs exit-status ioctl and native guest shutdown are not used.

## Validation

`make check` (inside the Fedora builder) verifies the firmware ABI, alignment,
ELF segment preservation, boot entry, ACPI checksums, and initramfs headers.
Boot testing uses KVM with Fedora's packaged libkrun and an extracted Fedora image.

After building, run the installed-RPM tests in a disposable Fedora container:

```sh
bash tools/smoke-test.sh
```

This test needs rootful Podman/Docker and KVM. It verifies a Fedora command,
arguments containing spaces and quotes, and a nonzero exit status. Logs are saved
in `build/smoke-*.log`. The privileged outer container is only the test environment;
the RPM's launcher runs directly on a Fedora host after installation.

The wrapper and bootstrap are MIT licensed. The prebuilt kernel is MPL-2.0.
The initramfs also contains the Fedora glibc and json-c runtime libraries needed by
the bootstrap; the RPM includes their license notices. Artifact provenance is
recorded in `upstream.json` and the generated `layout.json`.
