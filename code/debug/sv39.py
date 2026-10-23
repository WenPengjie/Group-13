#!/usr/bin/env python3
"""Decode an observed leaf PTE. Not a page-table walker or a permission checker."""
import argparse

def translate_leaf(va, pte, level):
    if not (0 <= va < 1 << 64 and 0 <= pte < 1 << 64):
        raise ValueError('VA/PTE must be unsigned 64-bit values')
    if level not in (0, 1, 2): raise ValueError('level must be 0, 1 or 2')
    upper = va >> 39
    if upper != ((1 << 25) - 1 if va & (1 << 38) else 0):
        raise ValueError('noncanonical Sv39 VA')
    if pte >> 54: raise ValueError('reserved high PTE bits set for this baseline Sv39 decoder')
    if not pte & 1 or not pte & (2 | 8) or (pte & 4 and not pte & 2):
        raise ValueError('invalid/non-leaf PTE or W without R')
    shift = 12 + 9 * level
    physical_base = ((pte >> 10) & ((1 << 44) - 1)) << 12
    mask = (1 << shift) - 1
    if physical_base & mask: raise ValueError('misaligned superpage')
    return physical_base | (va & mask), 1 << shift

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--va', type=lambda x: int(x, 0), required=True)
    ap.add_argument('--pte', type=lambda x: int(x, 0), required=True)
    ap.add_argument('--level', type=int, required=True)
    a = ap.parse_args()
    pa, size = translate_leaf(a.va, a.pte, a.level)
    print('VPN2/1/0:', *(hex((a.va >> (12 + 9*i)) & 511) for i in (2,1,0)))
    print(f'PA={pa:#x}, leaf_size={size:#x}, low12={a.va & 4095:#x}')
    print('Arithmetic only; verify observed PTE, satp, privilege and access permissions separately.')

if __name__ == '__main__': main()
