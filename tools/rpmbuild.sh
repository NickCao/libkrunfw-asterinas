#!/bin/bash
# Runs inside the Fedora builder image.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python3 tools/fetch-sources.py
topdir=$PWD/dist/rpmbuild
mkdir -p "$topdir"/{SOURCES,SPECS,BUILD,BUILDROOT,RPMS,SRPMS}
tar --sort=name --mtime='2026-11-02 00:00:00Z' --owner=0 --group=0 --numeric-owner \
    --exclude='__pycache__' --exclude='*.pyc' \
    --transform='s,^,libkrunfw-asterinas-0.1.0/,' \
    -czf "$topdir/SOURCES/libkrunfw-asterinas-0.1.0.tar.gz" \
    LICENSE README.md Makefile upstream.json src bin tools tests containers packaging licenses examples
python3 - "$topdir/SOURCES" <<'PY'
import json, pathlib, shutil, sys
lock = json.load(open("upstream.json"))
for key in ("source", "vdso"):
    name = lock[key]["archive"]
    shutil.copyfile(pathlib.Path(".cache/upstream") / name, pathlib.Path(sys.argv[1]) / name)
PY
rpmbuild -ba packaging/libkrunfw-asterinas.spec --define "_topdir $topdir"
