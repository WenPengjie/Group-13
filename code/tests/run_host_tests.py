#!/usr/bin/env python3
"""Run actual allocator sources with native RAM adapters and ASan/UBSan."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INCLUDES = ['libs', 'kern/mm', 'kern/debug', 'kern/driver']
SOURCES = ['tests/host_main.c', 'kern/mm/best_fit_pmm.c',
           'kern/mm/buddy_pmm.c', 'kern/mm/buddy_check.c',
           'kern/mm/slub.c', 'kern/mm/slub_check.c']

def main():
    with tempfile.TemporaryDirectory(prefix='lab2-host-') as tmp:
        for name, defines in [
            ('best-fit', []),
            ('buddy', ['LAB2_PMM_BUDDY']),
            ('best-fit-slub', ['LAB2_ENABLE_SLUB']),
            ('buddy-slub', ['LAB2_PMM_BUDDY', 'LAB2_ENABLE_SLUB']),
        ]:
            binary = str(Path(tmp) / name)
            command = [os.environ.get('HOSTCC', 'gcc'), '-std=gnu99', '-O1', '-g',
                       '-Wall', '-Werror', '-Wno-unused', '-fno-builtin', '-nostdinc',
                       '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                       '-no-pie', '-DLAB2_EXT_TEST']
            command += ['-I' + s for s in INCLUDES]
            command += ['-D' + s for s in defines]
            command += SOURCES + ['-o', binary]
            print('\nBUILD', name, flush=True)
            subprocess.run(command, cwd=ROOT, check=True)
            # LeakSanitizer requires /proc process tracing, unavailable in some hosts.
            # ASan/UBSan remain enabled; allocator leaks are checked by page baselines.
            env = dict(os.environ, ASAN_OPTIONS='detect_leaks=' + os.environ.get('HOST_LSAN', '0') + ':halt_on_error=1',
                       UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
            subprocess.run([binary], check=True, env=env, timeout=120)
    print('\nAll four HOST configurations passed. Target/QEMU verification is separate.')

if __name__ == '__main__':
    main()
