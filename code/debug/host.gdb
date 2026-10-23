# Use host gdb --args /absolute/debug/qemu-system-riscv64 ... -s -S
set pagination off
set breakpoint pending on
# From original kernel mapping: a 1-GiB root leaf covers this high VA region.
# To restrict to a particular observed memory access, add a condition on addr.
break get_physical_address if addr >= 0xffffffffc0200000 && mmu_idx == 1
echo Host breakpoint prepared for QEMU 4.1.1. Type run, then connect guest GDB.\n
echo This is a page-table/Bare translation breakpoint, not proof of a TLB hit.\n
