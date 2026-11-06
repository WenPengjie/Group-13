#!/usr/bin/env python3
"""HOST unit tests of harness failure handling; never report these as QEMU PASS."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import validation_tools as v


class ValidationToolsTests(unittest.TestCase):
    def test_path_kept(self):
        env = v.configured_env({'PATH': '/caller/toolchain:/usr/bin', 'OTHER': 'keep'})
        self.assertEqual(env['PATH'], '/caller/toolchain:/usr/bin')
        self.assertEqual(env['OTHER'], 'keep')

    def test_explicit_tool_directory(self):
        with tempfile.TemporaryDirectory() as d:
            env = v.configured_env({'PATH': '/caller', 'TOOLCHAIN_BIN': d})
            self.assertEqual(env['PATH'], d + os.pathsep + '/caller')
        with self.assertRaises(v.ValidationError):
            v.configured_env({'PATH': '/usr/bin', 'TOOLCHAIN_BIN': '/does-not-exist-lab3'})

    def test_refuse_hidden_build_flags(self):
        for name in ('MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS', 'MAKEFILES', 'DEFS', 'QEMU'):
            with self.subTest(name=name), self.assertRaises(v.ValidationError):
                v.configured_env({'PATH': '/usr/bin', name: 'override'})

    def test_missing_tools(self):
        with self.assertRaisesRegex(v.ValidationError, 'Missing tools'):
            v.preflight({'PATH': ''}, ['lab3_nonexistent_tool'])

    def test_unique_logs_preserve_history(self):
        with tempfile.TemporaryDirectory() as d:
            parent = Path(d)
            historical = parent / 'historical.log'
            historical.write_text('old evidence')
            first = v.new_log_dir(parent, 'test', {'LAB3_LOG_ROOT': d})
            second = v.new_log_dir(parent, 'test', {'LAB3_LOG_ROOT': d})
            self.assertNotEqual(first, second)
            self.assertEqual(historical.read_text(), 'old evidence')

    def test_success_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            log = directory / 'result.log'
            output = v.run_logged([sys.executable, '-c', 'print("actual host child")'],
                                   directory, os.environ.copy(), log, 5)
            self.assertIn('actual host child', output)
            self.assertEqual(json.loads(log.with_suffix('.log.json').read_text())['returncode'], 0)
            with self.assertRaisesRegex(v.ValidationError, 'exited 7'):
                v.run_logged([sys.executable, '-c', 'raise SystemExit(7)'],
                              directory, os.environ.copy(), log, 5)
            self.assertEqual(json.loads(log.with_suffix('.log.json').read_text())['returncode'], 7)

    def test_timeout_only_own_group(self):
        # Real host subprocesses, not a simulated TimeoutExpired exception.
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            log = directory / 'timeout.log'
            child_code = 'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)'
            parent_code = ('import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c",' +
                           repr(child_code) + ']); print(p.pid,flush=True); time.sleep(30)')
            with self.assertRaisesRegex(v.ValidationError, 'TimeoutExpired'):
                v.run_logged([sys.executable, '-c', parent_code], directory,
                              os.environ.copy(), log, 0.5)
            pid = int(log.read_text().strip())
            # Killed descendants may briefly be zombies awaiting host reaping.
            stat = Path('/proc') / str(pid) / 'stat'
            if stat.exists():
                self.assertEqual(stat.read_text().split(') ')[1][0], 'Z')
            self.assertEqual(json.loads(log.with_suffix('.log.json').read_text())['interrupted'], 'TimeoutExpired')

    def test_normal_result_oracle(self):
        normal = 'memory management: default_pmm_manager\ncheck_alloc_page() succeeded!\n' + '100 ticks\n' * 10
        v.check_normal(normal)
        for bad in (normal.replace('100 ticks\n', '', 1), normal + 'panic\n',
                    normal.replace('default_pmm_manager', 'best_fit_pmm_manager')):
            with self.assertRaises(v.ValidationError):
                v.check_normal(bad)

    def test_extended_oracle_against_fixture(self):
        # Input is historical fixture text, not a new target execution.
        fixture = (v.ROOT.parent / 'report/logs/07-extended-qemu.log').read_text()
        v.check_extended(fixture)
        with self.assertRaises(v.ValidationError):
            v.check_extended(fixture.replace('ticks=250', 'ticks=249'))
        with self.assertRaises(v.ValidationError):
            v.check_extended(fixture + '[EXT] fake PASS\n')

    def test_injection_is_isolated(self):
        before = v.source_hashes(v.ROOT)
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            v.copy_source(v.ROOT, work)
            v.setup_extended(v.ROOT, work)
            self.assertIn('extended_before_clock();', (work / 'kern/init/init.c').read_text())
            self.assertIn('pmm_manager = &best_fit_pmm_manager;', (work / 'kern/mm/pmm.c').read_text())
        self.assertEqual(before, v.source_hashes(v.ROOT))

    def test_static_metrics_no_false_runtime_claim(self):
        symbols = '\n'.join('00000000 00000008 T ' + n for n in v.FUNCTIONS)
        assembly = '\n'.join('00000000 <' + n + '>:\n   0: 0001 nop\n   2: 8082 ret\n' for n in v.FUNCTIONS)
        result = v.static_metrics(symbols, assembly)
        self.assertEqual(result['trap']['static_instructions'], 2)
        self.assertEqual(result['trap']['elf_symbol_bytes'], 8)
        result = v.static_metrics(symbols.replace('00000008 T', '00000000 T'), assembly)
        self.assertIsNone(result['__alltraps']['elf_symbol_bytes'])
        with self.assertRaises(v.ValidationError):
            v.static_metrics('', '')

    def test_missing_tools_exit_failure_and_unique_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            env = {'PATH': '', 'LAB3_LOG_ROOT': d}
            for _ in range(2):
                result = subprocess.run([sys.executable, str(v.ROOT / 'tests/validation_tools.py'), 'required'],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 1)
                self.assertIn('Missing tools', result.stderr)
            summaries = list(Path(d).glob('*/summary.json'))
            self.assertEqual(len(summaries), 2)
            for path in summaries:
                data = json.loads(path.read_text())
                self.assertEqual(data['status'], 'FAIL_OR_BLOCKED')
                self.assertFalse(data['target_runtime_verified'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
