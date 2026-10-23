#!/usr/bin/env python3
"""Execute the delivered page_init body in a translated host address arena.

This is a host-side contract test, not a RISC-V/QEMU boot test. Only the
linker end symbol is replaced by a configurable pointer; DTB, the address
mapping constants, panic, console and allocator registration are test doubles.
The function body itself is extracted from the supplied pmm.c, not rewritten.
"""
import pathlib
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).resolve()
text = source.read_text()
start = text.index('static void page_init(void) {')
stop = text.index('\n/* pmm_init -', start)
function = text[start:stop].replace('    extern char end[];\n', '')

prefix = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include <sys/mman.h>

#define PGSIZE 4096ULL
#define PGSHIFT 12
#define DRAM_BASE 0x80000000ULL
#define PHYSICAL_MEMORY_END 0x88000000ULL
#define PHYSICAL_MEMORY_OFFSET 0x80000000ULL
#define KERNEL_BEGIN_PADDR 0x80200000ULL
#define KERNBASE (KERNEL_BEGIN_PADDR + PHYSICAL_MEMORY_OFFSET)
#define KERNTOP (PHYSICAL_MEMORY_END + PHYSICAL_MEMORY_OFFSET)
#define PPN(a) (((uintptr_t)(a)) >> PGSHIFT)
#define ROUNDDOWN(a,n) ({size_t __a=(size_t)(a); (typeof(a))(__a-__a%(n));})
#define ROUNDUP(a,n) ({size_t __n=(size_t)(n); (typeof(a))(ROUNDDOWN((size_t)(a)+__n-1,__n));})
typedef struct list_entry {struct list_entry *prev, *next;} list_entry_t;
struct Page {int ref; uint64_t flags; unsigned int property; list_entry_t page_link;};
static struct Page *pages;
static size_t npage;
static const size_t nbase=DRAM_BASE/PGSIZE;
static uint64_t va_pa_offset, input_base, input_size;
static char *test_kernel_end;
#define end test_kernel_end
static jmp_buf abort_env;
static int panic_seen, registration_count;
static size_t free_count;
static uintptr_t registered_pa;
static unsigned char *arena;
static const size_t arena_size=PHYSICAL_MEMORY_END-DRAM_BASE;
static const char *panic_reason;
#define panic(message,...) do {panic_seen=1; panic_reason=(message); longjmp(abort_env,1);} while(0)
#define PADDR(kva) ({uintptr_t __m_kva=(uintptr_t)(kva); if(__m_kva<KERNBASE) panic("invalid kva"); __m_kva-va_pa_offset;})
#define SetPageReserved(p) ((p)->flags |= 1UL)
static void set_page_ref(struct Page *p,int n) {p->ref=n;}
static void list_init(list_entry_t *l) {l->next=l->prev=l;}
static uint64_t get_memory_base(void) {return input_base;}
static uint64_t get_memory_size(void) {return input_size;}
static int cprintf(const char *fmt,...) {(void)fmt; return 0;}
static struct Page *pa2page(uintptr_t pa) {
    if(PPN(pa)>=npage) panic("invalid pa");
    return &pages[PPN(pa)-nbase];
}
static uintptr_t page2pa(struct Page *p) {return (p-pages+nbase)<<PGSHIFT;}
static void init_memmap(struct Page *base,size_t n) {
    assert(n>0 && registration_count==0);
    assert(base>=pages && base+n<=pages+(npage-nbase));
    /* Inspect ALL descriptors before the mock backend changes free pages. */
    for(size_t i=0;i<npage-nbase;i++) {
        struct Page *p=pages+i;
        assert(p->flags==1 && p->property==0 && p->ref==0);
        assert(p->page_link.next==&p->page_link && p->page_link.prev==&p->page_link);
    }
    registration_count++;
    registered_pa=page2pa(base);
    free_count=n;
    for(size_t i=0;i<n;i++) base[i].flags=0;
    base->flags=2;
    base->property=n;
}
'''

suffix = r'''
static void run_case(const char *name,uint64_t base,uint64_t size,uintptr_t end_pa,
                     int expect_panic,uintptr_t expected_end,uintptr_t expected_free) {
    memset(arena,0xa5,arena_size);
    pages=NULL; npage=0; va_pa_offset=0;
    input_base=base; input_size=size;
    test_kernel_end=(char *)(end_pa+PHYSICAL_MEMORY_OFFSET);
    panic_seen=registration_count=0;
    free_count=0; registered_pa=0; panic_reason=NULL;
    if(setjmp(abort_env)==0) page_init();
    assert(panic_seen==expect_panic);
    if(expect_panic) {
        assert(registration_count==0);
        /* Invalid layout must be rejected BEFORE any descriptor write. */
        for(size_t i=0;i<arena_size;i++) assert(arena[i]==0xa5);
        printf("PASS %-32s expected panic: %s\n",name,panic_reason);
        return;
    }
    assert(va_pa_offset==PHYSICAL_MEMORY_OFFSET);
    assert(npage==expected_end/4096);
    uintptr_t expected_pages_pa=(end_pa+4095)/4096*4096;
    assert((uintptr_t)pages==expected_pages_pa+PHYSICAL_MEMORY_OFFSET);
    size_t expected_count=(expected_end-DRAM_BASE)/4096;
    assert(npage-nbase==expected_count);
    assert(expected_pages_pa+expected_count*sizeof(struct Page)<=expected_end);
    size_t expected_free_count=(expected_end-expected_free)/4096;
    assert(free_count==expected_free_count);
    assert(registration_count==(expected_free_count>0));
    if(expected_free_count) assert(registered_pa==expected_free);
    for(size_t i=0;i<expected_count;i++) {
        uintptr_t pa=DRAM_BASE+i*4096;
        struct Page *p=pages+i;
        assert(pa2page(page2pa(p))==p);
        if(pa<expected_free) assert(p->flags==1 && p->ref==0 && p->property==0);
        else assert((p->flags&1)==0);
    }
    /* The descriptor array must not write through its end into free memory. */
    uintptr_t after=expected_pages_pa+expected_count*sizeof(struct Page);
    for(uintptr_t pa=after;pa<expected_end;pa++) assert(arena[pa-DRAM_BASE]==0xa5);
    printf("PASS %-32s descriptors=%zu free=%zu registrations=%d\n",
           name,expected_count,free_count,registration_count);
}
int main(void) {
    assert(sizeof(uintptr_t)==8 && sizeof(struct Page)==40);
    void *want=(void *)(DRAM_BASE+PHYSICAL_MEMORY_OFFSET);
    arena=mmap(want,arena_size,PROT_READ|PROT_WRITE,
               MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    if(arena==MAP_FAILED) {perror("host arena mmap"); return 2;}
    run_case("normal_128MiB_unaligned_end",DRAM_BASE,0x8000000,0x80210123,0,0x88000000,0x80351000);
    run_case("already_aligned_kernel_end",DRAM_BASE,0x8000000,0x80211000,0,0x88000000,0x80351000);
    run_case("truncate_256MiB_to_cap",DRAM_BASE,0x10000000,0x80210123,0,0x88000000,0x80351000);
    run_case("unaligned_RAM_end",DRAM_BASE,0x7fff678,0x80210123,0,0x87fff000,0x80351000);
    run_case("zero_free_exact_array_end",DRAM_BASE,0x400000,0x803f6000,0,0x80400000,0x80400000);
    run_case("less_than_one_free_page",DRAM_BASE,0x3fffff,0x803f5000,0,0x803ff000,0x803ff000);
    run_case("exactly_one_free_page",DRAM_BASE,0x400000,0x803f5000,0,0x80400000,0x803ff000);
    run_case("zero_size",DRAM_BASE,0,0x80210123,1,0,0);
    run_case("zero_base",0,0x8000000,0x80210123,1,0,0);
    run_case("unsupported_DRAM_base",DRAM_BASE+4096,0x8000000,0x80210123,1,0,0);
    run_case("DTB_end_overflow",DRAM_BASE,UINT64_MAX,0x80210123,1,0,0);
    run_case("no_complete_DRAM_page",DRAM_BASE,4095,0x80210123,1,0,0);
    run_case("kernel_exceeds_RAM",DRAM_BASE,0x100000,0x80210123,1,0,0);
    run_case("descriptor_array_cannot_fit",DRAM_BASE,0x211000,0x80210123,1,0,0);
    run_case("kernel_below_link_base",DRAM_BASE,0x8000000,0x801ff000,1,0,0);
    assert(munmap(arena,arena_size)==0);
    puts("15/15 host contract scenarios passed (NOT a QEMU boot test).");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='lab2-page-init-') as directory:
    root = pathlib.Path(directory)
    c = root / 'check.c'
    exe = root / 'check'
    c.write_text(prefix + '\n' + function + '\n' + suffix)
    subprocess.run(['gcc', '-std=gnu99', '-Wall', '-Wextra', '-Werror',
                    '-O2', '-fsanitize=undefined', '-fno-sanitize-recover=all',
                    str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
