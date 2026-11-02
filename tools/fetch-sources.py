#!/usr/bin/python3
"""Download and verify the source archives pinned in upstream.json."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile
import urllib.request


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path(".cache/upstream"))
    parser.add_argument("--extract-to", type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    lock = json.loads((Path(__file__).resolve().parents[1] / "upstream.json").read_text())
    args.cache.mkdir(parents=True, exist_ok=True)
    for name in ("source", "vdso"):
        item = lock[name]
        archive = args.cache / item["archive"]
        if not archive.exists() or digest(archive) != item["sha256"]:
            if args.offline:
                raise SystemExit(f"Missing or invalid source archive: {archive}")
            temporary = archive.with_suffix(archive.suffix + ".part")
            with urllib.request.urlopen(item["url"], timeout=60) as response, temporary.open("wb") as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            if digest(temporary) != item["sha256"]:
                temporary.unlink()
                raise SystemExit(f"Source archive SHA256 mismatch: {item['archive']}")
            os.replace(temporary, archive)
        if args.extract_to:
            target = args.extract_to / item["directory"]
            if not target.exists():
                args.extract_to.mkdir(parents=True, exist_ok=True)
                with tarfile.open(archive) as source:
                    source.extractall(args.extract_to, filter="data")
        print(f"Verified {name}: {archive}")


if __name__ == "__main__":
    main()
