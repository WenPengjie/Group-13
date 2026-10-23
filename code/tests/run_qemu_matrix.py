#!/usr/bin/env python3
"""Real cross-build + QEMU tests. Never report a timeout as success."""
from pathlib import Path
import argparse
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--qemu', default='qemu-system-riscv64')
    ap.add_argument('--gccprefix', default='riscv64-unknown-elf-')
    ap.add_argument('--timeout', type=float, default=90)
    ap.add_argument('--log-dir', type=Path, default=ROOT / 'test-results')
    ap.add_argument('--reuse-build', action='store_true',
                    help='switch configurations without clean, then switch back to default')
    args = ap.parse_args()
    for tool in [args.qemu, args.gccprefix + 'gcc', args.gccprefix + 'ld',
                 args.gccprefix + 'objcopy', args.gccprefix + 'objdump']:
        if not shutil.which(tool):
            raise SystemExit('Missing tool: ' + tool + '; no target test was run.')
    logs = args.log_dir.resolve()
    logs.mkdir(parents=True, exist_ok=True)
    subprocess.run([args.qemu, '--version'], check=True)
    configs = [('best_fit', 0), ('buddy', 0), ('best_fit', 1), ('buddy', 1)]
    if args.reuse_build: configs.append(('best_fit', 0))
    for config_index, (pmm, slub) in enumerate(configs):
        name = pmm + ('-slub' if slub else '')
        if args.reuse_build: name = str(config_index + 1) + '-' + name
        print('BUILD + BOOT', name, flush=True)
        settings = ['PMM=' + pmm, 'SLUB=' + str(slub),
                    'EXT_TEST=' + ('1' if pmm == 'buddy' or slub else '0'),
                    'GCCPREFIX=' + args.gccprefix]
        with (logs / (name + '-build.log')).open('w') as out:
            if not args.reuse_build or config_index == 0:
                subprocess.run(['make', 'clean'], cwd=ROOT, stdout=out, stderr=out, check=True)
            subprocess.run(['make', '-j2'] + settings, cwd=ROOT,
                           stdout=out, stderr=out, check=True)
        expected = ['memory management: ' + ('buddy_pmm_manager' if pmm == 'buddy'
                                           else 'best_fit_pmm_manager'),
                    'check_alloc_page() succeeded!', 'satp physical address:']
        if pmm == 'buddy': expected.append('[Buddy] ALL TESTS PASS;')
        if slub: expected.append('[SLUB] ALL TESTS PASS;')
        path = logs / (name + '-qemu.log')
        command = [args.qemu, '-machine', 'virt', '-m', '128M', '-nographic',
                   '-monitor', 'none', '-bios', 'default', '-device',
                   'loader,file=bin/ucore.img,addr=0x80200000']
        with path.open('wb') as out:
            proc = subprocess.Popen(command, cwd=ROOT, stdout=out,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            deadline = time.monotonic() + args.timeout
            ok = False
            try:
                while time.monotonic() < deadline:
                    text = path.read_text(errors='replace')
                    if 'panic at' in text.lower() or 'assertion failed' in text.lower(): break
                    if (not slub and '[SLUB]' in text) or (pmm != 'buddy' and '[Buddy]' in text): break
                    if all(marker in text for marker in expected):
                        ok = True
                        break
                    if proc.poll() is not None: break
                    time.sleep(0.1)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try: proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill(); proc.wait()
            if not ok:
                raise SystemExit('FAIL or timeout: ' + name + '; inspect ' + str(path))
        print('TARGET PASS', name, 'log:', path, flush=True)
    print(('Five configuration switches' if args.reuse_build else 'Four target configurations') +
          ' passed. Run default `make grade` separately for official scoring.')

if __name__ == '__main__': main()
