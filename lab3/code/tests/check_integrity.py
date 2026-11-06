#!/usr/bin/env python3
"""Verify original course files and protected implementation regions."""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'tests/protected-sha256.json').read_text(encoding='utf-8'))
sha = lambda data: hashlib.sha256(data).hexdigest()
errors = []
for file, expected in manifest['files'].items():
    path = root / file
    if not path.exists() or sha(path.read_bytes()) != expected:
        errors.append(file)
for entry in manifest['regions']:
    text = (root / entry['file']).read_text(encoding='utf-8')
    matched = re.search(entry['pattern'], text, re.S)
    if not matched or sha(matched.group().encode()) != entry['sha256']:
        errors.append(entry['file'] + ' [protected region]')
for file in ('kern/trap/trap.c', 'kern/trap/trapentry.S'):
    text = (root / file).read_text(encoding='utf-8')
    if 'YOUR CODE' in text:
        errors.append(file + ' [unfilled student marker]')
if errors:
    raise SystemExit('FAIL: ' + ', '.join(errors))
print('PASS: %d original files and %d protected regions unchanged; student markers filled.'
      % (len(manifest['files']), len(manifest['regions'])))
