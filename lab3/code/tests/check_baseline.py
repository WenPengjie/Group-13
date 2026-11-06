#!/usr/bin/env python3
"""Verify all kernel/library/course-tool bytes against the exact input ZIP."""
import argparse
import hashlib
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('archive', nargs='?', type=Path, default=root.parent / 'baseline-input.zip')
args = parser.parse_args()
with zipfile.ZipFile(args.archive) as archive:
    names = [name for name in archive.namelist()
             if name.startswith('lab3_2511057/code/') and not name.endswith('/')]
    protected = [name for name in names if name.split('/code/', 1)[1] == 'Makefile'
                 or name.split('/code/', 1)[1].startswith(('kern/', 'libs/', 'tools/'))]
    errors = []
    for name in protected:
        relative = name.split('/code/', 1)[1]
        target = root / relative
        if not target.is_file() or target.read_bytes() != archive.read(name):
            errors.append(relative)
if errors:
    raise SystemExit('FAIL: source differs from input ZIP: ' + ', '.join(errors))
print('PASS:', len(protected), 'course source files exactly match lab3_2511057(2).zip; kernel speedup NOT claimed.')
print('Input ZIP SHA256:', hashlib.sha256(args.archive.read_bytes()).hexdigest())
