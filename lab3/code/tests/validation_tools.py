#!/usr/bin/env python3
"""Isolated Lab3 validation. No kernel edits; no historical-log replacement."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ('interrupt_handler', 'exception_handler', 'trap', '__alltraps', '__trapret')


class ValidationError(RuntimeError):
    pass


def configured_env(source=None):
    env = dict(os.environ if source is None else source)
    # Fail explicitly rather than silently accepting build-changing flags.
    for name in ('MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS', 'MAKEFILES', 'DEFS', 'QEMU'):
        if env.get(name):
            raise ValidationError('Unset ' + name + ' for default-config validation.')
    paths = []
    for name in ('TOOLCHAIN_BIN', 'QEMU_BIN'):
        if env.get(name):
            folder = Path(env[name]).expanduser().resolve()
            if not folder.is_dir():
                raise ValidationError(name + ' is not a directory: ' + str(folder))
            paths.append(str(folder))
    env['PATH'] = os.pathsep.join(paths + [env.get('PATH', os.defpath)])
    return env


def preflight(env, names):
    resolved = {name: shutil.which(name, path=env['PATH']) for name in names}
    missing = [name for name, path in resolved.items() if path is None]
    if missing:
        raise ValidationError('Missing tools: ' + ', '.join(missing) +
                              '; configure PATH or TOOLCHAIN_BIN/QEMU_BIN. No target test ran.')
    return resolved


def source_hashes(root):
    names = [root / 'Makefile']
    for folder in ('kern', 'libs', 'tools'):
        names.extend(p for p in (root / folder).rglob('*') if p.is_file())
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(names)}


def new_log_dir(root, kind, env):
    parent = Path(env.get('LAB3_LOG_ROOT', str(root / 'validation'))).expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return Path(tempfile.mkdtemp(prefix=kind + '-' + stamp + '-', dir=parent))


def stop_group(proc):
    # proc was started in its own session; never use pkill or a global process name.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    # A child can ignore TERM even after the group leader exits.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def run_logged(command, cwd, env, logfile, seconds):
    metadata = {'command': [str(x) for x in command], 'cwd': str(cwd),
                'timeout_seconds': seconds}
    print('RUN:', ' '.join(metadata['command']), flush=True)
    with logfile.open('w', encoding='utf-8') as output:
        proc = subprocess.Popen(metadata['command'], cwd=cwd, env=env,
                                stdout=output, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            metadata['returncode'] = proc.wait(timeout=seconds)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            stop_group(proc)
            metadata.update(returncode=proc.returncode, interrupted=type(exc).__name__)
            raise ValidationError(type(exc).__name__ + '; own process group stopped; log: ' + str(logfile)) from exc
        finally:
            logfile.with_suffix(logfile.suffix + '.json').write_text(
                json.dumps(metadata, indent=2), encoding='utf-8')
    if metadata['returncode'] != 0:
        raise ValidationError('Command exited ' + str(metadata['returncode']) + '; log: ' + str(logfile))
    return logfile.read_text(encoding='utf-8', errors='replace')


def copy_source(root, work):
    for folder in ('kern', 'libs', 'tools'):
        for path in (root / folder).rglob('*'):
            if path.is_symlink():
                raise ValidationError('Refusing external/symlinked source: ' + str(path))
        shutil.copytree(root / folder, work / folder)
    shutil.copy2(root / 'Makefile', work / 'Makefile')


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def check_normal(text):
    require(text.splitlines().count('100 ticks') == 10, 'Expected exactly 10 timer reports.')
    require('memory management: default_pmm_manager' in text, 'Default PMM changed.')
    require('check_alloc_page() succeeded!' in text, 'Page self-check missing.')
    require('panic' not in text.lower(), 'Unexpected panic in normal boot.')


def check_extended(text):
    expected = (
        '[EXT] all writable GPRs, sp, ra, gp, tp and disabled SIE: PASS',
        '[EXT] 16-bit c.ebreak and halfword-aligned 32-bit ebreak return: PASS',
        '[EXT] 16-bit and 32-bit illegal instruction return: PASS',
        '[EXT] nested critical section preserves disabled SIE: PASS',
        '[EXT] exception return and nested critical section restore enabled SIE: PASS',
        '[EXT] sustained timer after mixed exceptions: PASS (ticks=250)',
    )
    lines = text.splitlines()
    for item in expected:
        require(lines.count(item) == 1, 'Missing/duplicate result: ' + item)
    require(text.count('[EXT]') == 6, 'Unexpected EXT result count.')
    require('best_fit_pmm_manager' in text and 'check_alloc_page() succeeded!' in text,
            'Best-Fit self-check missing.')
    require('panic' not in text.lower(), 'Unexpected panic in extended run.')
    require(lines.count('100 ticks') == 2, 'Expected 2 timer reports in extended run.')


def setup_extended(root, work):
    extra = work / 'kern/extra'
    extra.mkdir()
    for name in ('extended.c', 'extended_context.S'):
        shutil.copy2(root / 'tests' / name, extra / name)
    makefile = work / 'Makefile'
    text = makefile.read_text()
    anchor = 'KCFLAGS\t\t+='
    require(text.count(anchor) == 1, 'Unexpected Makefile; do not guess injection position.')
    makefile.write_text(text.replace(anchor, 'KINCLUDE += kern/extra\nKSRCDIR += kern/extra\n' + anchor))
    init = work / 'kern/init/init.c'
    text = init.read_text()
    require(text.count('idt_init();') == 2 and text.count('intr_enable();') == 1,
            'Unexpected init layout; refusing injection.')
    index = text.rindex('idt_init();') + len('idt_init();')
    text = text[:index] + '\n    extended_before_clock();' + text[index:]
    text = text.replace('intr_enable();', 'intr_enable();\n    extended_after_enable();')
    init.write_text('void extended_before_clock(void);\nvoid extended_after_enable(void);\n' + text)
    pmm = work / 'kern/mm/pmm.c'
    text = pmm.read_text()
    require(text.count('pmm_manager = &default_pmm_manager;') == 1, 'Default PMM anchor missing.')
    pmm.write_text(text.replace('pmm_manager = &default_pmm_manager;',
                                'pmm_manager = &best_fit_pmm_manager;'))


def qemu_command():
    return ['qemu-system-riscv64', '-machine', 'virt', '-nographic', '-bios', 'default',
            '-device', 'loader,file=bin/ucore.img,addr=0x80200000', '-monitor', 'none', '-no-reboot']


def static_metrics(symbols, assembly):
    result = {}
    for name in FUNCTIONS:
        symbol = re.search(r'^([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+[tT]\s+' + re.escape(name) + r'$', symbols, re.M)
        body = re.search(r'^[0-9a-fA-F]+ <' + re.escape(name) + r'>:\n(.*?)(?=^[0-9a-fA-F]+ <|\Z)', assembly, re.M | re.S)
        require(body is not None, 'Missing disassembly: ' + name)
        instructions = len(re.findall(r'^\s*[0-9a-fA-F]+:\s+[0-9a-fA-F]+\s+\S+', body.group(1), re.M))
        size = int(symbol.group(2), 16) if symbol else 0
        result[name] = {'static_instructions': instructions,
                        'elf_symbol_bytes': size or None}
        # Assembly labels may have zero st_size. Do not invent their byte size.
    return result


def audit_tree(root, env, logs, label):
    with tempfile.TemporaryDirectory(prefix='lab3-audit-') as temporary:
        work = Path(temporary) / 'source'
        work.mkdir()
        copy_source(root, work)
        run_logged(['make', '-j2', 'DEFS='], work, env, logs / (label + '-build.log'), 120)
        symbols = run_logged(['riscv64-unknown-elf-nm', '-S', '--defined-only', 'bin/kernel'],
                             work, env, logs / (label + '-symbols.log'), 15)
        assembly = run_logged(['riscv64-unknown-elf-objdump', '-d', 'bin/kernel'],
                              work, env, logs / (label + '-disassembly.log'), 15)
        return {'source_sha256': source_hashes(root), 'metrics': static_metrics(symbols, assembly)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('required', 'extended', 'audit'))
    parser.add_argument('--baseline', type=Path, help='audit only: baseline CODE directory, not ZIP')
    args = parser.parse_args(argv)
    if args.baseline and args.mode != 'audit':
        parser.error('--baseline is only supported for audit')
    logs = new_log_dir(ROOT, args.mode, os.environ)
    print('LOG DIRECTORY:', logs, flush=True)
    summary = {'mode': args.mode, 'status': 'STARTED', 'source_sha256': source_hashes(ROOT),
               'target_runtime_verified': False}
    try:
        env = configured_env()
        run_logged([sys.executable, str(ROOT / 'tests/check_integrity.py')], ROOT, env,
                   logs / 'integrity.log', 20)
        names = ['make', 'riscv64-unknown-elf-gcc', 'riscv64-unknown-elf-ld',
                 'riscv64-unknown-elf-objcopy', 'riscv64-unknown-elf-objdump']
        names += ['riscv64-unknown-elf-nm'] if args.mode == 'audit' else ['qemu-system-riscv64', 'timeout']
        summary['tools'] = preflight(env, names)
        summary['PATH'] = env['PATH']
        for name in ('make', 'riscv64-unknown-elf-gcc', 'riscv64-unknown-elf-objdump'):
            run_logged([name, '--version'], ROOT, env, logs / (name + '-version.log'), 15)
        if args.mode != 'audit':
            run_logged(['qemu-system-riscv64', '--version'], ROOT, env, logs / 'qemu-version.log', 15)
        if args.mode == 'audit':
            summary['candidate'] = audit_tree(ROOT, env, logs, 'candidate')
            if args.baseline:
                summary['baseline'] = audit_tree(args.baseline.resolve(), env, logs, 'baseline')
                before = summary['baseline']['metrics']
                after = summary['candidate']['metrics']
                summary['static_delta_candidate_minus_baseline'] = {
                    name: {field: after[name][field] - before[name][field]
                           if after[name][field] is not None and before[name][field] is not None else None
                           for field in ('static_instructions', 'elf_symbol_bytes')}
                    for name in FUNCTIONS}
            summary['interpretation'] = 'STATIC ONLY; not a runtime speed measurement.'
        else:
            with tempfile.TemporaryDirectory(prefix='lab3-validation-') as temporary:
                work = Path(temporary) / 'source'
                work.mkdir()
                copy_source(ROOT, work)
                if args.mode == 'extended':
                    setup_extended(ROOT, work)
                run_logged(['make', '-j2', 'DEFS='], work, env, logs / 'build.log', 120)
                boot = run_logged(qemu_command(), work, env, logs / 'qemu.log', 30)
                (check_normal if args.mode == 'required' else check_extended)(boot)
                if args.mode == 'required':
                    # Override only the grading scratch path, not flags or tests.
                    grade = run_logged(['make', 'GRADE_TMP=' + str(Path(temporary) / 'grade'), 'grade'],
                                       work, env, logs / 'grade.log', 150)
                    require('Total Score: 100/100' in grade, 'Official grade was not 100/100.')
                summary['target_runtime_verified'] = True
        summary['status'] = 'PASS'
        print(args.mode.upper() + ' PASS; evidence:', logs)
        return 0
    except (ValidationError, OSError) as exc:
        summary.update(status='FAIL_OR_BLOCKED', error=str(exc))
        print('FAIL/BLOCKED:', exc, file=sys.stderr)
        return 1
    finally:
        (logs / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
