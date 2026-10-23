#!/usr/bin/env python3
"""Capture real guest/host GDB evidence using an independently built QEMU 4.1.1.

Run from a trusted local checkout. No installation, attachment to unrelated
processes, remote upload or change to protected course sources is performed.
"""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--qemu-debug', required=True, type=Path)
    ap.add_argument('--qemu-source', required=True, type=Path)
    ap.add_argument('--host-gdb', default='gdb')
    ap.add_argument('--target-gdb', default='riscv64-unknown-elf-gdb')
    ap.add_argument('--host-library-path')
    ap.add_argument('--gccprefix', default='riscv64-unknown-elf-')
    ap.add_argument('--output-dir', type=Path, default=ROOT.parent / 'report/logs/debug')
    args = ap.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    qemu = str(args.qemu_debug.resolve())
    helper = args.qemu_source.resolve() / 'target/riscv/cpu_helper.c'
    lines = helper.read_text().splitlines()
    pte_line = next(i + 1 for i, text in enumerate(lines)
                    if 'target_ulong ppn = pte >> PTE_PPN_SHIFT;' in text)
    pa_line = next(i + 1 for i, text in enumerate(lines)
                   if '*physical = (ppn | (vpn &' in text)
    env = dict(os.environ)
    if args.host_library_path:
        env['LD_LIBRARY_PATH'] = args.host_library_path
    env['DEBUGINFOD_URLS'] = ''

    with (output / 'kernel-build.log').open('w') as out:
        subprocess.run(['make', 'PMM=best_fit', 'SLUB=0', 'EXT_TEST=0',
                        'GCCPREFIX=' + args.gccprefix], cwd=ROOT,
                       stdout=out, stderr=subprocess.STDOUT, check=True)

    qemu_args = [qemu, '-machine', 'virt', '-m', '128M', '-nographic',
                 '-monitor', 'none', '-bios', 'default', '-device',
                 'loader,file=bin/ucore.img,addr=0x80200000']
    preamble = '''set pagination off
set confirm off
set print pretty on
set print elements 8
handle SIGPIPE nostop noprint pass
'''
    sv39 = preamble + f'''break riscv_cpu_tlb_fill if mmu_idx == 1 && access_type == 0 && address >= 0xffffffffc0200000
run
disable 1
tbreak get_physical_address
continue
printf "\\n=== REAL SV39 DATA LOAD ===\\n"
bt 8
info args
p/x env->satp
printf "VA=0x%lx SATP=0x%lx ACCESS=%d MMU=%d\\n", addr, env->satp, access_type, mmu_idx
set $saved_env = env
set $saved_va = addr
set $saved_physical = physical
tbreak {helper}:{pte_line}
continue
printf "\\n=== PAGE TABLE WALK ===\\n"
p levels
p ptshift
p/x base
p/x idx
p/x pte_addr
p/x pte
printf "ROOT_PA=0x%lx LEVELS=%d PTSHIFT=%d INDEX=%lu PTE_ADDR=0x%lx PTE=0x%lx\\n", base, levels, ptshift, idx, pte_addr, pte
next
p/x ppn
tbreak {helper}:{pa_line}
continue
next
p/x *physical
p/x (*physical | (addr & 4095))
printf "PHYSICAL_PAGE=0x%lx FINAL_PA=0x%lx\\n", *physical, (*physical | (addr & 4095))
finish
next
printf "\\n=== TRANSLATION RETURN ===\\n"
p ret
p/x pa
tbreak tlb_set_page
continue
printf "\\n=== SOFTWARE TLB FILL ===\\n"
info args
set $saved_cpu = (RISCVCPU *)cpu
set $saved_mmu = mmu_idx
set $saved_vpage = vaddr
finish
set $saved_index = ($saved_vpage >> 12) & ($saved_cpu->neg.tlb.f[$saved_mmu].mask >> 5)
set $saved_entry = &$saved_cpu->neg.tlb.f[$saved_mmu].table[$saved_index]
p/x $saved_index
p/x *$saved_entry
p $saved_entry->addr_read == $saved_vpage
rwatch -location $saved_entry->addr_read
continue
printf "\\n=== POST-FILL TAG RELOAD IN C SLOW PATH ===\\n"
bt 4
python
import gdb
for observation in range(32):
    if gdb.selected_frame().name() == 'code_gen_buffer':
        break
    gdb.execute('continue')
else:
    raise gdb.GdbError('Generated TCG tag read was not observed')
end
printf "\\n=== EXECUTED GENERATED TCG TLB HIT ===\\n"
bt 4
x/8i $pc
p/x $eflags
p ($eflags & 64) != 0
stepi
x/i $pc
printf "\\n=== SV39 CAPTURE COMPLETE ===\\n"
kill
quit
'''
    bare = preamble + r'''break get_physical_address if mmu_idx == 1 && env->satp == 0 && addr >= 0x80200000
run
disable 1
printf "\n=== REAL S-MODE BARE ACCESS ===\n"
bt 8
info args
p/x env->satp
set $saved_physical = physical
finish
next
p/x *$saved_physical
p ret
tbreak tlb_set_page
continue
printf "\n=== BARE ALSO FILLS QEMU SOFTWARE TLB ===\n"
info args
printf "\n=== BARE CAPTURE COMPLETE ===\n"
kill
quit
'''
    guest = preamble + r'''set architecture riscv:rv64
set tcp auto-retry on
set tcp connect-timeout 30
file bin/kernel
target remote 127.0.0.1:1257
hbreak kern_init
continue
printf "\n=== REAL GUEST KERNEL ENTRY ===\n"
info registers pc sp satp
x/8i $pc
p/x &boot_page_table_sv39
p/x ((unsigned long *)&boot_page_table_sv39)[511]
printf "\n=== GUEST CAPTURE COMPLETE ===\n"
detach
quit
'''
    guest_path = output / 'guest.gdb'
    guest_path.write_text(guest)

    for name, script in [('host-sv39', sv39), ('host-bare', bare)]:
        path = output / (name + '.gdb')
        path.write_text(script)
        print('CAPTURE', name, flush=True)
        with (output / (name + '.log')).open('w') as out:
            actual_args = qemu_args + (['-gdb', 'tcp:127.0.0.1:1257', '-S']
                                      if name == 'host-sv39' else [])
            process = subprocess.Popen([args.host_gdb, '-q', '-batch', '-x', str(path),
                                        '--args'] + actual_args, cwd=ROOT, env=env,
                                       stdout=out, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            try:
                if name == 'host-sv39':
                    # The guest debugger inspects kern_init, then detaches.
                    # Only a real riscv_cpu_tlb_fill can trigger the host's
                    # first breakpoint, so debugger memory reads are excluded.
                    time.sleep(1)
                    with (output / 'guest.log').open('w') as guest_out:
                        subprocess.run([args.target_gdb, '-q', '-batch', '-x', str(guest_path)],
                                       cwd=ROOT, stdout=guest_out, stderr=subprocess.STDOUT,
                                       timeout=60, check=True)
                status = process.wait(timeout=150)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        if status:
            raise SystemExit(name + ' failed; inspect ' + str(output / (name + '.log')))

    print('Real host/guest GDB captures completed:', output, flush=True)


if __name__ == '__main__':
    main()
