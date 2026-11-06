#!/usr/bin/env python3
"""Clean isolated static audit; no claim of measured runtime acceleration."""
import sys
from validation_tools import main

if __name__ == '__main__':
    raise SystemExit(main(['audit'] + sys.argv[1:]))
