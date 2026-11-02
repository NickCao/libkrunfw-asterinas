#!/bin/bash
# Real Podman -> packaged krun -> packaged libkrun -> Asterinas HTTP test.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
project_dir=$PWD
engine=${CONTAINER_ENGINE:-podman}
fedora=${FEDORA_VERSION:-44}
port=${NGINX_TEST_PORT:-18080}
builder="localhost/libkrunfw-asterinas-build:${fedora}"
test_container="asterinas-nginx-e2e-$$"
rpm=$(printf '%s\n' dist/rpmbuild/RPMS/x86_64/libkrunfw-asterinas-*.rpm | sort -V | tail -1)
test -f "$rpm"
mkdir -p build
collect_guest_log() {
    "$engine" exec "$test_container" bash -c '
        podman --cgroup-manager=cgroupfs --storage-driver=vfs logs nginx-asterinas
    ' >build/nginx-guest.log 2>/dev/null || true
}
cleanup() {
    result=$?
    collect_guest_log
    if [ "$result" -eq 0 ] && [ "${KEEP_TEST_CONTAINER:-0}" = 1 ]; then
        printf 'Kept Fedora test container: %s\n' "$test_container"
    else
        "$engine" kill "$test_container" >/dev/null 2>&1 || true
        "$engine" rm -f "$test_container" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT
"$engine" run -d --name "$test_container" --privileged --cgroupns host \
    -p "127.0.0.1:$port:18080" \
    -v "$project_dir:/src:Z" -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
    "$builder" sleep infinity >/dev/null
"$engine" exec -i "$test_container" bash -s -- "$rpm" >build/nginx-test.log 2>&1 <<'FEDORA'
set -euo pipefail
dnf -y --disablerepo='*' install --allowerasing "/src/$1"
rpm -V libkrunfw-asterinas libkrun crun-krun
# The stock package must have been removed by the replacement transaction.
if rpm -q libkrunfw; then exit 1; fi
rpm -q --whatprovides 'libkrunfw.so.5()(64bit)'
rpm -q podman crun-krun libkrun libkrunfw-asterinas > /src/build/nginx-packages.log
podman --cgroup-manager=cgroupfs --storage-driver=vfs network create \
    --subnet 10.0.2.0/24 --gateway 10.0.2.2 asterinas
# --pid=host avoids crun 1.28's inconsistent /proc while it starts passt.
# --cgroupns=host also makes the nested test's cgroup mount consistent.
podman --cgroup-manager=cgroupfs --storage-driver=vfs run -d \
    --name nginx-asterinas --runtime /usr/bin/krun \
    --log-driver=k8s-file \
    --security-opt seccomp=unconfined --pid host --cgroupns host \
    --annotation krun.cpus=1 --annotation krun.use_passt=1 \
    --network asterinas --ip 10.0.2.15 -p 18080:8080 \
    -v /usr/share/libkrunfw-asterinas/nginx.conf:/etc/nginx/conf.d/default.conf:ro \
    docker.io/library/nginx:stable
podman --cgroup-manager=cgroupfs --storage-driver=vfs image inspect \
    docker.io/library/nginx:stable --format '{{.Digest}}' > /src/build/nginx-image.log
podman --cgroup-manager=cgroupfs --storage-driver=vfs inspect \
    nginx-asterinas --format '{{.OCIRuntime}}' > /src/build/nginx-runtime.log
FEDORA
python3 tools/check-nginx.py "$port"
collect_guest_log
grep -Fq 'Asterinas libkrunfw bootstrap' build/nginx-guest.log
grep -Fq 'Network eth0: 10.0.2.15' build/nginx-guest.log
grep -Fq '"GET / HTTP/1.1" 200 ' build/nginx-guest.log
printf 'PASS: host HTTP request reached nginx inside Asterinas through stock Fedora krun/libkrun\n'
