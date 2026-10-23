#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 1 ]]; then echo 'Usage: bash debug/locate-qemu.sh /qemu/source' >&2; exit 2; fi
src=$(realpath "$1")
if ! command -v rg >/dev/null 2>&1; then
    echo 'ripgrep (rg) is required; install it or use grep -nE for these patterns.' >&2
    exit 2
fi
cat "$src/VERSION"
rg -n 'get_physical_address|riscv_cpu_tlb_fill|tlb_set_page|ptshift|pte_addr' "$src/target/riscv/cpu_helper.c"
rg -n 'load_helper|store_helper|victim_tlb_hit|tlb_hit\(|tlb_fill\(' "$src/accel/tcg/cputlb.c"
rg -n 'tcg_out_tlb_load|TLB Hit|jne slow_path' "$src/tcg/i386/tcg-target.inc.c"
