#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
project_dir=$PWD
engine=${CONTAINER_ENGINE:-podman}
fedora=${FEDORA_VERSION:-44}
builder="localhost/libkrunfw-asterinas-build:${fedora}"
rpm=$(printf '%s\n' dist/rpmbuild/RPMS/x86_64/libkrunfw-asterinas-*.rpm | sort -V | tail -1)
test -f "$rpm"
mkdir -p .cache build
rootfs=$(mktemp -d "$project_dir/.cache/smoke-rootfs.XXXXXX")
container_id=
test_container="libkrunfw-asterinas-smoke-$$"
cleanup() {
    "$engine" rm -f "$test_container" >/dev/null 2>&1 || true
    if [ -n "$container_id" ]; then "$engine" rm -f "$container_id" >/dev/null 2>&1 || true; fi
    rm -rf -- "$rootfs"
}
trap cleanup EXIT
container_id=$("$engine" create "registry.fedoraproject.org/fedora:$fedora")
"$engine" export "$container_id" | tar -xf - -C "$rootfs"
"$engine" rm "$container_id" >/dev/null
container_id=
"$engine" run --rm --name "$test_container" --privileged --network none \
    -v "$project_dir:/src:Z" -v "$rootfs:/rootfs:Z" "$builder" \
    bash -c 'set -e; dnf -y --disablerepo="*" install --allowerasing "/src/$1"; rpm -V libkrunfw-asterinas; python3 tools/smoke.py /rootfs' bash "$rpm"
