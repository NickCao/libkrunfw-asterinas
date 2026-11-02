#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
project_dir=$PWD
engine=${CONTAINER_ENGINE:-podman}
fedora=${FEDORA_VERSION:-44}
builder="localhost/libkrunfw-asterinas-build:${fedora}"
"$engine" build --build-arg "FEDORA_VERSION=$fedora" -f containers/Containerfile -t "$builder" .
"$engine" run --rm -v "$project_dir:/src:Z" "$builder" bash tools/rpmbuild.sh
