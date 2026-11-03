#!/usr/bin/python3
"""Small stdio/TTY checks in a retained Fedora nginx-test container."""
from pathlib import Path
import os
import selectors
import subprocess
import sys
import threading
import time

engine = os.environ.get("CONTAINER_ENGINE", "podman")
container = sys.argv[1]
podman = ["podman", "--cgroup-manager=cgroupfs", "--storage-driver=vfs"]
runtime = [
    "--runtime", "/usr/bin/krun", "--security-opt", "seccomp=unconfined",
    "--pid", "host", "--cgroupns", "host", "--network", "none",
    "--log-driver=k8s-file",
]
image = "docker.io/library/nginx:stable"
payload = bytes(range(256)) * 128


def check(name, command, data, markers, tty=False, expected=0):
    guest_name = f"console-{name}"
    run = podman + ["run", "--name", guest_name, "-i"] + runtime
    if tty:
        run += ["-t"]
    run += [image, "/bin/sh", "-c", command]
    outer = [engine, "exec", "-i"]
    if tty:
        outer += ["-t"]
    outer += [container]
    if tty:
        outer += ["bash", "-c", 'stty rows 37 cols 101 -echo; exec "$@"', "bash"]
    process = subprocess.Popen(outer + run, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = [bytearray(), bytearray()]

    def feed():
        try:
            process.stdin.write(data)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, 0)
    selector.register(process.stderr, selectors.EVENT_READ, 1)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            for event, _ in selector.select(0.2):
                block = os.read(event.fileobj.fileno(), 65536)
                if block:
                    output[event.data].extend(block)
                else:
                    selector.unregister(event.fileobj)
            if all(marker in output[stream] for stream, marker in markers):
                break
            if process.poll() is not None and not selector.get_map():
                break
        for index, stream in enumerate(("stdout", "stderr")):
            Path(f"build/console-{name}-{stream}.log").write_bytes(output[index])
        for stream, marker in markers:
            if marker not in output[stream]:
                raise SystemExit(f"{name}: missing {marker!r}; see build/console-{name}-*.log")
        result = process.wait(timeout=15)
        if result != expected:
            raise SystemExit(f"{name}: expected exit {expected}, got {result}")
    finally:
        for operation in ("kill", "rm"):
            subprocess.run([engine, "exec", container] + podman + [operation, guest_name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        process.wait(timeout=15)
        selector.close()
        writer.join(timeout=1)
    return output


out, err = check("pipe", "printf PIPE_BEGIN; printf STDERR_ONLY >&2; cat; printf PIPE_EOF",
                 payload, [(0, b"PIPE_EOF"), (1, b"STDERR_ONLY")])
body = bytes(out).split(b"PIPE_BEGIN", 1)[1].split(b"PIPE_EOF", 1)[0]
assert body == payload, "piped I/O changed or lost bytes"
assert b"STDERR_ONLY" not in out and b"PIPE_BEGIN" not in err, "stdout/stderr were merged"
print("PASS: separate stdout/stderr, 32 KiB binary stdin round trip, host EOF", flush=True)

out, _ = check("tty", 'test -t 0 && printf "TTY_READY\\n"; stty size; read line; printf "TTY_INPUT=<%s>\\n" "$line"',
               b"terminal-input\n", [(0, b"TTY_READY"), (0, b"37 101"), (0, b"TTY_INPUT=<terminal-input>")], tty=True)
print("PASS: interactive console input and initial 37x101 terminal size", flush=True)

check("exit7", "printf EXIT7_OK; exit 7", b"", [(0, b"EXIT7_OK")], expected=7)
print("PASS: guest exit 7 propagates through stock krun and Podman", flush=True)
