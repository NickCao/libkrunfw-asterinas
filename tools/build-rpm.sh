#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
project_dir=$PWD
engine=${CONTAINER_ENGINE:-podman}
fedora=${FEDORA_VERSION:-44}
builder="localhost/libkrunfw-asterinas-build:${fedora}"
rust_toolchain=$(python3 -c 'import json; print(json.load(open("upstream.json"))["rust_toolchain"])')
"$engine" build --build-arg "FEDORA_VERSION=$fedora" --build-arg "RUST_TOOLCHAIN=$rust_toolchain" \
    -f containers/Containerfile -t "$builder" .
mkdir -p .cache/cargo/registry .cache/cargo/git
# Upstream component registration parses file paths; a parent named /src breaks it.
"$engine" run --rm -v "$project_dir:/work:Z" -w /work \
    -v "$project_dir/.cache/cargo/registry:/root/.cargo/registry:Z" \
    -v "$project_dir/.cache/cargo/git:/root/.cargo/git:Z" \
    -e KERNEL_TARGET_DIR=/work/.cache/kernel-target-rpm \
    -e KERNEL_BUILD_JOBS="${KERNEL_BUILD_JOBS:-2}" \
    "$builder" bash tools/rpmbuild.sh
