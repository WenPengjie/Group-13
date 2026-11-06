#include <assert.h>
#include <clock.h>
#include <intr.h>
#include <riscv.h>
#include <sbi.h>
#include <stdio.h>
#include <trap.h>
#include "../sync/sync.h"

extern uintptr_t extended_register_context(void);
typedef char frame_size_must_be_288[(sizeof(struct trapframe) == 288) ? 1 : -1];

void extended_before_clock(void) {
    assert(!(read_csr(stvec) & 3));
    assert(!(read_csr(sstatus) & SSTATUS_SIE));
    assert(extended_register_context() == 0);
    assert(!(read_csr(sstatus) & SSTATUS_SIE));
    assert(read_csr(sscratch) == 0);
    cprintf("[EXT] all writable GPRs, sp, ra, gp, tp and disabled SIE: PASS\n");
    cprintf("[EXT] 16-bit c.ebreak and halfword-aligned 32-bit ebreak return: PASS\n");
    asm volatile(".2byte 0x0000\n.4byte 0x0000007b" ::: "memory");
    cprintf("[EXT] 16-bit and 32-bit illegal instruction return: PASS\n");
    bool outer, inner;
    local_intr_save(outer);
    local_intr_save(inner);
    local_intr_restore(inner);
    local_intr_restore(outer);
    assert(!(read_csr(sstatus) & SSTATUS_SIE));
    cprintf("[EXT] nested critical section preserves disabled SIE: PASS\n");
}

void extended_after_enable(void) {
    assert(read_csr(sstatus) & SSTATUS_SIE);
    asm volatile(".2byte 0x9002\n.4byte 0x00100073" ::: "memory");
    assert(read_csr(sstatus) & SSTATUS_SIE);
    bool outer, inner;
    local_intr_save(outer);
    assert(!(read_csr(sstatus) & SSTATUS_SIE));
    local_intr_save(inner);
    local_intr_restore(inner);
    assert(!(read_csr(sstatus) & SSTATUS_SIE));
    local_intr_restore(outer);
    assert(read_csr(sstatus) & SSTATUS_SIE);
    cprintf("[EXT] exception return and nested critical section restore enabled SIE: PASS\n");
    while (ticks < 250) {
        asm volatile("" ::: "memory");
    }
    cprintf("[EXT] sustained timer after mixed exceptions: PASS (ticks=%lu)\n", ticks);
    sbi_shutdown();
    while (1) {}
}
