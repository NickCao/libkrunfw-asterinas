#!/usr/bin/python3
"""Fetch a pinned upstream binary; no kernel or Kata source build is involved."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path(".cache/upstream"))
    parser.add_argument("--output", type=Path, default=Path("build/asterinas.elf"))
    args = parser.parse_args()
    lock = json.loads((Path(__file__).resolve().parents[1] / "upstream.json").read_text())
    args.cache.mkdir(parents=True, exist_ok=True)
    archive = args.cache / lock["url"].rsplit("/", 1)[1]
    if not archive.exists() or digest(archive) != lock["sha256"]:
        temporary = archive.with_suffix(archive.suffix + ".part")
        with urllib.request.urlopen(lock["url"], timeout=60) as response, temporary.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
        if digest(temporary) != lock["sha256"]:
            temporary.unlink()
            raise SystemExit("Upstream archive SHA256 mismatch")
        os.replace(temporary, archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".part")
    with temporary.open("wb") as output:
        subprocess.run(["tar", "--zstd", "-xOf", str(archive), lock["member"]], stdout=output, check=True)
    if digest(temporary) != lock["kernel_sha256"]:
        temporary.unlink()
        raise SystemExit("Extracted kernel SHA256 mismatch")
    os.replace(temporary, args.output)
    print(f"Verified and extracted Asterinas {lock['asterinas_version']}: {args.output}")


if __name__ == "__main__":
    main()
