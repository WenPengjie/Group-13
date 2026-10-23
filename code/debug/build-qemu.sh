#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 2 ]]; then
    echo 'Usage: bash debug/build-qemu.sh /absolute/qemu-4.1.1 /absolute/new-build-dir' >&2
    exit 2
fi
src=$(realpath "$1")
build=$(realpath -m "$2")
test -f "$src/configure"
test -f "$src/VERSION"
if [[ $(cat "$src/VERSION") != 4.1.1 ]]; then
    echo 'This helper is for QEMU 4.1.1; inspect the actual version/options first.' >&2
    exit 2
fi
if [[ -e "$build" ]]; then
    echo 'Choose a new build directory; existing build was not changed.' >&2
    exit 2
fi
mkdir -p "$build"
cd "$build"
"$src/configure" --target-list=riscv64-softmmu --enable-debug --disable-werror \
    --extra-cflags='-O0 -g3'
make -j2
test -x riscv64-softmmu/qemu-system-riscv64
echo "Debug QEMU: $build/riscv64-softmmu/qemu-system-riscv64"
echo 'No make install was run. Existing installed QEMU is unchanged.'
