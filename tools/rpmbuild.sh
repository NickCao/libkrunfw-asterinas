#!/bin/bash
# Runs inside the Fedora builder image.
set -euo pipefail
cd /src
python3 tools/fetch-kernel.py
topdir=$PWD/dist/rpmbuild
mkdir -p "$topdir"/{SOURCES,SPECS,BUILD,BUILDROOT,RPMS,SRPMS}
tar --sort=name --mtime='2026-11-02 00:00:00Z' --owner=0 --group=0 --numeric-owner \
    --exclude='__pycache__' --exclude='*.pyc' \
    --transform='s,^,libkrunfw-asterinas-0.1.0/,' \
    -czf "$topdir/SOURCES/libkrunfw-asterinas-0.1.0.tar.gz" \
    LICENSE README.md Makefile upstream.json src bin tools tests containers packaging licenses
cp --reflink=auto build/asterinas.elf \
    "$topdir/SOURCES/asterinas-7861bff17133b941cf89329917033541d14813ab.elf"
rpmbuild -ba packaging/libkrunfw-asterinas.spec --define "_topdir $topdir"
