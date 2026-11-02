#!/bin/bash
# Runs in the Fedora builder, including when invoked by rpmbuild.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
project_dir=$PWD
if [ "$#" -eq 0 ]; then
    python3 tools/fetch-sources.py --extract-to .cache/source-build
    source_dir=$(python3 -c 'import json; print(".cache/source-build/" + json.load(open("upstream.json"))["source"]["directory"])')
    vdso_dir=$(python3 -c 'import json; print(".cache/source-build/" + json.load(open("upstream.json"))["vdso"]["directory"])')
elif [ "$#" -eq 2 ]; then
    source_dir=$1
    vdso_dir=$2
else
    echo "Usage: $0 [ASTERINAS_SOURCE VDSO_SOURCE]" >&2
    exit 2
fi
source_dir=$(realpath "$source_dir")
if [[ "$source_dir/" == *src/* ]]; then
    echo "Asterinas component registration requires a source path without 'src/'; mount this checkout at /work." >&2
    exit 1
fi
export VDSO_LIBRARY_DIR
VDSO_LIBRARY_DIR=$(realpath "$vdso_dir")
export RUSTUP_TOOLCHAIN
RUSTUP_TOOLCHAIN=$(python3 -c 'import json; print(json.load(open("upstream.json"))["rust_toolchain"])')
export CARGO_BUILD_JOBS=${KERNEL_BUILD_JOBS:-2}
export CARGO_TARGET_DIR
CARGO_TARGET_DIR=$(realpath -m "${KERNEL_TARGET_DIR:-$project_dir/build/kernel-target}")
export OSTD_TASK_STACK_SIZE_IN_PAGES
OSTD_TASK_STACK_SIZE_IN_PAGES=$(python3 -c 'import json; print(json.load(open("upstream.json"))["kernel_build"]["stack_pages"])')
arch=$(python3 -c 'import json; print(json.load(open("upstream.json"))["kernel_build"]["arch"])')
boot_method=$(python3 -c 'import json; print(json.load(open("upstream.json"))["kernel_build"]["boot_method"])')
profile=$(python3 -c 'import json; print(json.load(open("upstream.json"))["kernel_build"]["profile"])')
# OSDK supplies the freestanding target's flags. Fedora RPM defaults include
# hosted linker specs that rust-lld cannot use. This script's environment is
# separate from the wrapper's subsequent make invocation.
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS CFLAGS CXXFLAGS CPPFLAGS LDFLAGS
python3 - "$source_dir" <<'PY'
import json, pathlib, sys, tomllib
lock = json.load(open("upstream.json"))
source = pathlib.Path(sys.argv[1])
assert (source / "VERSION").read_text().strip() == lock["asterinas_version"]
assert tomllib.loads((source / "rust-toolchain.toml").read_text())["toolchain"]["channel"] == lock["rust_toolchain"]
PY
# Build the matching OSDK rather than using a potentially different installed one.
OSDK_LOCAL_DEV=1 cargo build --locked --release --manifest-path "$source_dir/osdk/Cargo.toml"
export PATH="$CARGO_TARGET_DIR/release:$PATH"
# Only a kernel is needed. The upstream make target also builds rootfs images;
# use its OSDK invocation directly and omit QEMU-only manifest configuration.
cat > "$source_dir/kernel/OSDK.toml" <<'OSDK'
[boot]
method = "vmm-direct"
[qemu]
args = ""
OSDK
(
    cd "$source_dir/kernel"
    cargo osdk build --target-arch "$arch" --boot-method "$boot_method" \
        --profile "$profile" --kcmd-args=loglevel=error --kcmd-args=earlycon \
        --output "$project_dir/build/kernel-artifacts"
)
install -Dm0644 "$project_dir/build/kernel-artifacts/asterinas-osdk-bin.elf" "$project_dir/build/asterinas.elf"
install -Dm0644 "$project_dir/build/kernel-artifacts/asterinas-run-base/Cargo.lock" "$project_dir/build/kernel-Cargo.lock"
python3 - <<'PY'
import hashlib, json, pathlib, subprocess
lock = json.load(open("upstream.json"))
kernel = pathlib.Path("build/asterinas.elf")
manifest = {
    "asterinas_commit": lock["asterinas_commit"],
    "source_sha256": lock["source"]["sha256"],
    "vdso_commit": lock["vdso"]["commit"],
    "vdso_sha256": lock["vdso"]["sha256"],
    "rustc": subprocess.check_output(["rustc", "--version"], text=True).strip(),
    "kernel_build": lock["kernel_build"],
    "kernel_sha256": hashlib.file_digest(kernel.open("rb"), "sha256").hexdigest(),
    "cargo_lock_sha256": hashlib.file_digest(pathlib.Path("build/kernel-Cargo.lock").open("rb"), "sha256").hexdigest(),
}
pathlib.Path("build/kernel-build.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("Built Asterinas from source:", manifest["kernel_sha256"])
PY
