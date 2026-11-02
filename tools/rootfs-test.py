#!/usr/bin/python3
"""Boot the RPM's firmware without an initramfs through stock Fedora krun."""
from pathlib import Path
import json
import os
import subprocess
import sys

engine = os.environ.get("CONTAINER_ENGINE", "podman")
container = sys.argv[1]
podman = ["podman", "--cgroup-manager=cgroupfs", "--storage-driver=vfs"]
name = f"virtiofs-root-{os.getpid()}"
firmware = "/usr/lib64/libkrunfw-asterinas/rootfs"
outer = [engine, "exec", "-e", f"LD_LIBRARY_PATH={firmware}", container]
layout = subprocess.check_output(
    [engine, "exec", container, "cat", "/usr/share/libkrunfw-asterinas/rootfs-layout.json"],
    text=True,
)
assert json.loads(layout)["INITRD_SIZE"] == 0, "firmware still contains an initramfs"
command = r'''
case " $(cat /proc/cmdline) " in *" root="*) exit 90;; esac
awk '$2 == "/" && $3 == "virtiofs" { found=1 } END { exit !found }' /proc/mounts || exit 91
printf 'VIRTIOFS_ROOT_OK\n'
exit 7
'''
try:
    result = subprocess.run(
        outer + podman + [
            "run", "--name", name, "--runtime", "/usr/bin/krun",
            "--security-opt", "seccomp=unconfined", "--pid", "host", "--cgroupns", "host",
            "--network", "none", "--log-driver=k8s-file", "--annotation", "krun.cpus=1",
            "docker.io/library/nginx:stable", "/bin/sh", "-c", command,
        ],
        capture_output=True, timeout=60,
    )
    output = result.stdout + result.stderr
    Path("build/rootfs-test.log").write_bytes(output)
    for marker in (
        b"rootfs is ready (mounted from /dev/root)",
        b"running /init.krun as the init process",
        b"VIRTIOFS_ROOT_OK",
    ):
        assert marker in output, f"missing {marker!r}; see build/rootfs-test.log"
    assert result.returncode == 7, f"expected guest exit 7, got {result.returncode}"
    print("PASS: no initramfs, default /dev/root virtiofs tag, stock init and Podman exit 7")
finally:
    subprocess.run(
        [engine, "exec", container] + podman + ["rm", "-f", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
    )
