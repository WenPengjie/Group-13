#!/usr/bin/env python3
"""Verify supplied tests and protected framework files against original ZIP hashes."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'tests/protected-sha256.json').read_text())
for name, expected in manifest.items():
    if name == 'best_fit_original_test_suffix':
        data = (root / 'kern/mm/best_fit_pmm.c').read_text().split('// Framework tests:', 1)[1].encode()
    else:
        data = (root / name).read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected: raise SystemExit('CHANGED protected content: ' + name)
    print('UNCHANGED', name)
print('Protected framework and official tests: PASS')
