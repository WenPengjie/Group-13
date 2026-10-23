# Run from project root: riscv64-unknown-elf-gdb -x debug/guest.gdb
set pagination off
set confirm off
set architecture riscv:rv64
file bin/kernel
target remote localhost:1234
# Hardware breakpoint avoids planting a virtual-address software breakpoint
# before the boot page table is installed.
hbreak kern_init
echo Guest connected. Type continue; then inspect $pc, $satp and disassemble /r kern_init.\n
