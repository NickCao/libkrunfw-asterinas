#!/usr/bin/python3
"""Fetch nginx from the actual build host, without using HTTP proxy settings."""
import http.client
from pathlib import Path
import sys
import time

port = int(sys.argv[1])
deadline = time.monotonic() + 90
failure = "nginx did not start"
while time.monotonic() < deadline:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read()
        server = response.getheader("Server", "")
        if response.status != 200 or not server.startswith("nginx/") or b"Welcome to nginx!" not in body:
            raise ValueError(f"Unexpected response: {response.status}, server={server!r}")
        headers = f"HTTP/1.1 {response.status} {response.reason}\n" + "".join(
            f"{name}: {value}\n" for name, value in response.getheaders()
        )
        Path("build/nginx-http.headers").write_text(headers)
        Path("build/nginx-http.html").write_bytes(body)
        print(f"HTTP 200 OK from {server} at http://127.0.0.1:{port}/ ({len(body)} bytes)", flush=True)
        break
    except (OSError, http.client.HTTPException, ValueError) as error:
        failure = str(error)
        time.sleep(1)
    finally:
        connection.close()
else:
    raise SystemExit(f"FAIL: {failure}; see build/nginx-test.log and build/nginx-guest.log")
