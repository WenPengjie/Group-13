#!/usr/bin/env python3
"""Exercise actual handler C bodies with host stubs; NOT an ISA/QEMU test."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
text = (root / 'kern/trap/trap.c').read_text()
handlers = text[text.index('//lab3 function2'):text.index('static inline void trap_dispatch')]
constants = '\n'.join(re.findall(r'^#define (?:IRQ_|CAUSE_)[^\n]+',
                                 (root / 'libs/riscv.h').read_text(), re.M))
prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#define __riscv_xlen 64
'''
# Use the actual C layout, not a reduced synthetic trapframe.
prefix += (root / 'kern/trap/trap.h').read_text().replace('#include <defs.h>', '')
prefix += r'''
static volatile size_t ticks;
static size_t arms, reports_seen, shutdowns, frames;
static char output[8192];
static void clock_set_next_event(void) { ++arms; }
static void print_ticks(void) { ++reports_seen; }
static void sbi_shutdown(void) { ++shutdowns; }
void print_trapframe(struct trapframe *tf) { (void)tf; ++frames; }
static int cprintf(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    size_t offset = strlen(output);
    int n = vsnprintf(output + offset, sizeof(output) - offset, fmt, ap);
    va_end(ap);
    return n;
}
#define TICK_NUM 100
'''
main = r'''
int main(void) {
    assert(sizeof(struct trapframe) == 288);
    assert(offsetof(struct trapframe, gpr.sp) == 16);
    assert(offsetof(struct trapframe, status) == 256);
    assert(offsetof(struct trapframe, epc) == 264);
    assert(offsetof(struct trapframe, badvaddr) == 272);
    assert(offsetof(struct trapframe, cause) == 280);
    struct trapframe tf = {0};
    _Alignas(4) uint16_t code[] = {0x9002, 0x0073, 0x0010, 0x0000, 0x007b, 0};
    uintptr_t addresses[] = {(uintptr_t)&code[0], (uintptr_t)&code[1],
                            (uintptr_t)&code[3], (uintptr_t)&code[4]};
    size_t lengths[] = {2, 4, 2, 4};
    for (size_t i = 0; i < 4; ++i) {
        tf.cause = i < 2 ? CAUSE_BREAKPOINT : CAUSE_ILLEGAL_INSTRUCTION;
        tf.epc = addresses[i];
        exception_handler(&tf);
        assert(tf.epc == addresses[i] + lengths[i]);
    }
    assert(strstr(output, "Exception type: Breakpoint\nBreakpoint at 0x"));
    assert(strstr(output, "Exception type: Illegal instruction\nIllegal instruction at 0x"));
    // Real byte encodings, explicit expected lengths and two alignments.
    const uint16_t encodings[] = {0x0000, 0x0001, 0x0002, 0x9002, 0x0073, 0x007b};
    const size_t expected[] = {2, 2, 2, 2, 4, 4};
    _Alignas(4) uint16_t slots[4] = {0};
    for (size_t cause = 2; cause <= 3; ++cause) {
        for (size_t align = 0; align <= 1; ++align) {
            for (size_t j = 0; j < 6; ++j) {
                output[0] = 0;
                slots[align] = encodings[j];
                tf.cause = cause;
                tf.epc = (uintptr_t)&slots[align];
                exception_handler(&tf);
                assert(tf.epc == (uintptr_t)&slots[align] + expected[j]);
            }
        }
    }
    output[0] = 0;
    tf.epc = 0x1000; tf.cause = 20;
    exception_handler(&tf);
    assert(frames == 1 && tf.epc == 0x1000);
    for (uintptr_t cause = 0; cause <= 11; ++cause) {
        if (cause == IRQ_S_TIMER) continue;
        tf.cause = ((uintptr_t)1 << 63) | cause;
        interrupt_handler(&tf);
    }
    tf.cause = ((uintptr_t)1 << 63) | 15;
    interrupt_handler(&tf);
    assert(frames == 2 && strstr(output, "Unknown interrupt: cause 15\n"));
    assert(strstr(output, "Supervisor software interrupt\n"));
    assert(ticks == 0 && arms == 0 && reports_seen == 0);
    tf.cause = ((uintptr_t)1 << 63) | IRQ_S_TIMER;
    uintptr_t interrupted_epc = tf.epc;
    for (size_t i = 1; i <= 1000; ++i) {
        interrupt_handler(&tf);
        assert(ticks == i && arms == i && reports_seen == i / 100);
        assert(shutdowns == (i == 1000 ? 1 : 0));
        assert(tf.epc == interrupted_epc);
    }
    puts("HOST PASS: actual 288-byte layout, 24 encoding/alignment cases, output formats, fallbacks, unchanged timer EPC, 1000 re-arms and shutdown threshold.");
}
'''
# Remove only the real SBI include; all implemented handler statements are used.
handlers = handlers.replace('#include <sbi.h>', '')
with tempfile.TemporaryDirectory(prefix='lab3_handlers_host_') as folder:
    source = Path(folder) / 'handlers.c'
    executable = Path(folder) / 'handlers'
    source.write_text(prefix + constants + '\n' + handlers + main)
    subprocess.run([os.environ.get('HOSTCC', 'gcc'), '-std=c11', '-Wall', '-Wextra',
                    '-Werror', '-fsanitize=undefined', str(source), '-o', str(executable)], check=True, timeout=30)
    subprocess.run([str(executable)], check=True, timeout=5)
print('LIMIT: no RISC-V instructions, CSR restoration, real timer or SBI firmware were executed.')
