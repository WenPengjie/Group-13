#include <default_pmm.h>
#include <best_fit_pmm.h>
#ifdef LAB2_PMM_BUDDY
#include <buddy_pmm.h>
#endif
#include <defs.h>
#include <error.h>
#include <memlayout.h>
#include <mmu.h>
#include <pmm.h>
#include <sbi.h>
#include <stdio.h>
#include <string.h>
#include <riscv.h>
#include <dtb.h>

// virtual address of physical page array
struct Page *pages;
// amount of physical memory (in pages)
size_t npage = 0;
// the kernel image is mapped at VA=KERNBASE and PA=info.base
uint64_t va_pa_offset;
// memory starts at 0x80000000 in RISC-V
// DRAM_BASE defined in riscv.h as 0x80000000
const size_t nbase = DRAM_BASE / PGSIZE;

// virtual address of boot-time page directory
uintptr_t *satp_virtual = NULL;
// physical address of boot-time page directory
uintptr_t satp_physical;

// physical memory management
const struct pmm_manager *pmm_manager;


static void check_alloc_page(void);

// init_pmm_manager - initialize a pmm_manager instance
static void init_pmm_manager(void) {
#ifdef LAB2_PMM_BUDDY
    pmm_manager = &buddy_pmm_manager;
#else
    pmm_manager = &best_fit_pmm_manager;
#endif
    cprintf("memory management: %s\n", pmm_manager->name);
    pmm_manager->init();
}

// init_memmap - call pmm->init_memmap to build Page struct for free memory
static void init_memmap(struct Page *base, size_t n) {
    pmm_manager->init_memmap(base, n);
}

// alloc_pages - call pmm->alloc_pages to allocate a continuous n*PAGESIZE
// memory
struct Page *alloc_pages(size_t n) {
    return pmm_manager->alloc_pages(n);
}

// free_pages - call pmm->free_pages to free a continuous n*PAGESIZE memory
void free_pages(struct Page *base, size_t n) {
    pmm_manager->free_pages(base, n);
}

// nr_free_pages - call pmm->nr_free_pages to get the size (nr*PAGESIZE)
// of current free memory
size_t nr_free_pages(void) {
    return pmm_manager->nr_free_pages();
}

// lab2 function1: initial implementation 2511565; layout reviewed 2511057; final review 2511955.
static void page_init(void) {
    extern char end[];
    const uintptr_t addr_max = ~(uintptr_t)0;
    uint64_t mem_base = get_memory_base();
    uint64_t mem_size = get_memory_size();

    // The boot mapping and Page/PPN conversions use a fixed DRAM base.
    if (mem_base != DRAM_BASE || mem_size == 0 ||
        mem_size > addr_max - mem_base) {
        panic("page_init: invalid or unsupported DTB memory range");
    }
    uintptr_t mem_end = mem_base + mem_size;  // exclusive physical end
    cprintf("Physical memory from DTB: [0x%016llx, 0x%016llx)\n",
            (unsigned long long)mem_base, (unsigned long long)mem_end);

    // PADDR must not be used before the mapping offset is initialized.
    va_pa_offset = PHYSICAL_MEMORY_OFFSET;
    uintptr_t maxpa = PHYSICAL_MEMORY_END;
    uintptr_t mapped_end = PADDR(KERNTOP);
    if (maxpa > mapped_end) {
        maxpa = mapped_end;
    }
    if (maxpa > mem_end) {
        maxpa = mem_end;
    }
    maxpa = ROUNDDOWN(maxpa, PGSIZE);
    if (PPN(maxpa) <= nbase) {
        panic("page_init: no manageable physical pages");
    }
    npage = PPN(maxpa);  // upper PPN, NOT the number of descriptors
    size_t page_count = npage - nbase;
    cprintf("Managed physical memory: [0x%016llx, 0x%016llx)\n",
            (unsigned long long)mem_base, (unsigned long long)maxpa);

    // Validate the entire descriptor layout before writing any descriptor.
    uintptr_t kernel_end_va = (uintptr_t)end;
    uintptr_t kernel_end_pa = PADDR(kernel_end_va);
    if (kernel_end_pa < KERNEL_BEGIN_PADDR || kernel_end_pa > maxpa ||
        kernel_end_va > addr_max - (PGSIZE - 1)) {
        panic("page_init: kernel end is outside manageable memory");
    }
    uintptr_t pages_va = ROUNDUP(kernel_end_va, PGSIZE);
    uintptr_t pages_pa = PADDR(pages_va);
    if (pages_pa < kernel_end_pa || pages_pa > maxpa ||
        page_count > (maxpa - pages_pa) / sizeof(struct Page)) {
        panic("page_init: insufficient memory for Page descriptors");
    }
    // The capacity check above also makes this multiplication safe.
    size_t descriptor_bytes = page_count * sizeof(struct Page);
    if (descriptor_bytes > addr_max - pages_va) {
        panic("page_init: descriptor virtual address overflow");
    }
    uintptr_t descriptors_end_pa = PADDR(pages_va + descriptor_bytes);
    if (descriptors_end_pa > addr_max - (PGSIZE - 1)) {
        panic("page_init: free-area alignment overflow");
    }
    uintptr_t free_begin_pa = ROUNDUP(descriptors_end_pa, PGSIZE);

    pages = (struct Page *)pages_va;
    for (size_t i = 0; i < page_count; i++) {
        struct Page *p = &pages[i];
        p->flags = 0;
        SetPageReserved(p);
        p->property = 0;
        set_page_ref(p, 0);
        list_init(&p->page_link);
    }
    cprintf("Page descriptors: VA 0x%016llx, PA [0x%016llx, 0x%016llx), "
            "%llu entries\n",
            (unsigned long long)pages_va, (unsigned long long)pages_pa,
            (unsigned long long)descriptors_end_pa,
            (unsigned long long)page_count);

    // Keep firmware, kernel, descriptors and alignment gaps reserved.
    if (free_begin_pa < maxpa) {
        assert(free_begin_pa >= mem_base && PPN(free_begin_pa) >= nbase);
        size_t free_count = (maxpa - free_begin_pa) / PGSIZE;
        init_memmap(pa2page(free_begin_pa), free_count);
        cprintf("Initial free memory: [0x%016llx, 0x%016llx), %llu pages\n",
                (unsigned long long)free_begin_pa, (unsigned long long)maxpa,
                (unsigned long long)free_count);
    } else {
        cprintf("Initial free memory: 0 complete pages; registration skipped\n");
    }
}

/* pmm_init - initialize the physical memory management */
void pmm_init(void) {
    // We need to alloc/free the physical memory (granularity is 4KB or other size).
    // So a framework of physical memory manager (struct pmm_manager)is defined in pmm.h
    // First we should init a physical memory manager(pmm) based on the framework.
    // Then pmm can alloc/free the physical memory.
    // Now the first_fit/best_fit/worst_fit/buddy_system pmm are available.
    init_pmm_manager();

    // detect physical memory space, reserve already used memory,
    // then use pmm->init_memmap to create free page list
    page_init();

    // use pmm->check to verify the correctness of the alloc/free function in a pmm
    check_alloc_page();

    extern char boot_page_table_sv39[];
    satp_virtual = (pte_t*)boot_page_table_sv39;
    satp_physical = PADDR(satp_virtual);
    cprintf("satp virtual address: 0x%016lx\nsatp physical address: 0x%016lx\n", satp_virtual, satp_physical);
}

static void check_alloc_page(void) {
    pmm_manager->check();
    cprintf("check_alloc_page() succeeded!\n");
}
