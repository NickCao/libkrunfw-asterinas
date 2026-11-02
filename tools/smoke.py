#!/usr/bin/python3
"""KVM tests of the installed RPM, using stock Fedora libkrun and userspace."""
from pathlib import Path
import re
import subprocess
import sys

rootfs = sys.argv[1]
cases = [
    ("success", 0, 'printf "ARGUMENT_TEST=<%s>\\n" "a b"; uname -a; cat /etc/fedora-release'),
    ("exit7", 7, "exit 7"),
]
for name, expected, command in cases:
    result = subprocess.run(
        ["/usr/bin/libkrunfw-asterinas-run", rootfs, "/bin/sh", "-c", command],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
    )
    log = Path("build") / f"smoke-{name}.log"
    log.write_bytes(result.stdout)
    output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout.decode(errors="replace"))
    if result.returncode != expected:
        raise SystemExit(f"{name}: expected exit {expected}, got {result.returncode}; see {log}")
    if name == "success" and not all(s in output for s in ["ARGUMENT_TEST=<a b>", "Fedora release", "x86_64"]):
        raise SystemExit(f"{name}: guest output missing; see {log}")
    print(f"PASS: {name} (guest and host exit {expected}); {log}", flush=True)
