/* Native algorithm harness. Uses the REAL project headers and allocator C files.
 * Only firmware, privileged execution and physical RAM are replaced. */
#include <pmm.h>
#include <best_fit_pmm.h>
#include <buddy_pmm.h>
#include <slub.h>
#include <stdio.h>
extern void *stdout;
extern void setbuf(void *, char *);
extern int vprintf(const char *, va_list);
extern int posix_memalign(void **, unsigned long, unsigned long);
extern void free(void *);
extern void abort(void) __attribute__((noreturn));

struct Page *pages;
size_t npage;
const size_t nbase = DRAM_BASE / PGSIZE;
uint64_t va_pa_offset;
const struct pmm_manager *pmm_manager;
static struct Page descriptors[(PHYSICAL_MEMORY_END - DRAM_BASE) / PGSIZE];
struct Page *alloc_pages(size_t n) { return pmm_manager->alloc_pages(n); }
void free_pages(struct Page *p, size_t n) { pmm_manager->free_pages(p, n); }
size_t nr_free_pages(void) { return pmm_manager->nr_free_pages(); }
int cprintf(const char *fmt, ...) {
    va_list ap; va_start(ap, fmt);
    int n = vprintf(fmt, ap); __builtin_va_end(ap); return n;
}
void __panic(const char *file, int line, const char *fmt, ...) {
    cprintf("HOST PANIC %s:%d: ", file, line);
    va_list ap; va_start(ap, fmt); vprintf(fmt, ap); __builtin_va_end(ap);
    cprintf("\n"); abort();
}
int main(void) {
    setbuf(stdout, NULL);
    void *ram = NULL;
    assert(posix_memalign(&ram, PGSIZE, PHYSICAL_MEMORY_END - DRAM_BASE) == 0);
    pages = descriptors;
    npage = PHYSICAL_MEMORY_END / PGSIZE;
    va_pa_offset = (uintptr_t)ram - DRAM_BASE;
    for (size_t i = 0; i < npage - nbase; i++) SetPageReserved(&pages[i]);
#ifdef LAB2_PMM_BUDDY
    pmm_manager = &buddy_pmm_manager;
#else
    pmm_manager = &best_fit_pmm_manager;
#endif
    pmm_manager->init();
    pmm_manager->init_memmap(pages + 1024, npage - nbase - 1024);
    size_t baseline = nr_free_pages();
    cprintf("HOST algorithm check: %s, %lu free pages\n", pmm_manager->name, baseline);
    pmm_manager->check();
    assert(nr_free_pages() == baseline);
    cprintf("[PMM] check and baseline restoration PASS\n");
#ifdef LAB2_ENABLE_SLUB
    slub_init(); slub_check();
    assert(nr_free_pages() == baseline);
#endif
    for (size_t i = 0; i < 1024; i++) assert(PageReserved(&pages[i]));
    free(ram);
    cprintf("HOST PASS (not a RISC-V boot test)\n");
    return 0;
}
