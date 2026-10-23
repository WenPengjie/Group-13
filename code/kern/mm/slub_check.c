// lab2 independent object tests: initial version 2511565; all-class coverage 2511057; final review 2511955.
#include <slub.h>
#include <pmm.h>
#include <stdio.h>

static void pattern_write(void *p, size_t n, unsigned seed) {
    unsigned char *v = p;
    for (size_t i = 0; i < n; i++) v[i] = (unsigned char)(seed + i * 13);
}
static void pattern_check(void *p, size_t n, unsigned seed) {
    unsigned char *v = p;
    for (size_t i = 0; i < n; i++) assert(v[i] == (unsigned char)(seed + i * 13));
}
#ifdef LAB2_EXT_TEST
/* Static tracking belongs to the kernel image; no allocation by the tested API. */
static void *objects[600];
static void *exhausted[(PHYSICAL_MEMORY_END - DRAM_BASE) / PGSIZE];
static void *active[64];
static size_t requested[64];
static const size_t cases[] = {
    1,15,16,17,31,32,33,63,64,65,127,128,129,255,256,257,
    511,512,513,1023,1024,1025,2047,2048,2049,4095,4096,4097,8193,16000
};
static unsigned random_state = 2511057;
static unsigned random_next(void) {
    random_state = random_state * 1103515245U + 12345U;
    return random_state >> 8;
}
static void nonoverlap(void *a, size_t an, void *b, size_t bn) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    assert(x + an <= y || y + bn <= x);
}
static void boundary_checks(void) {
    size_t before = nr_free_pages(), count = sizeof(cases) / sizeof(cases[0]);
    assert(!kmalloc(0)); kfree(NULL);
    assert(!kmalloc((size_t)-1) && !kmalloc((size_t)-32));
    assert(nr_free_pages() == before);
    for (size_t i = 0; i < count; i++) {
        objects[i] = kmalloc(cases[i]);
        assert(objects[i] && !((uintptr_t)objects[i] % 16));
        for (size_t j = 0; j < i; j++) nonoverlap(objects[i], cases[i], objects[j], cases[j]);
        pattern_write(objects[i], cases[i], i + 1);
    }
    for (size_t i = 0; i < count; i++) pattern_check(objects[i], cases[i], i + 1);
    for (size_t i = 0; i < count; i += 2) kfree(objects[i]);
    for (size_t i = 1; i < count; i += 2) {
        pattern_check(objects[i], cases[i], i + 1); kfree(objects[i]);
    }
    assert(nr_free_pages() == before);
    cprintf("[SLUB] class/page boundaries, alignment, contents: PASS\n");
}
static void reuse_checks(void) {
    const size_t classes[] = {16, 32, 64, 128, 256, 512, 1024, 2048};
    for (unsigned c = 0; c < sizeof(classes) / sizeof(classes[0]); c++) {
    size_t size = classes[c];
    size_t before = nr_free_pages();
    for (unsigned i = 0; i < 600; i++) {
        objects[i] = kmalloc(size); assert(objects[i]);
        pattern_write(objects[i], size, i);
    }
    size_t full_free = nr_free_pages();
    size_t occupied = before - nr_free_pages();
    assert(occupied > 1 && occupied <= 600);
    if (size < 2048) assert(ROUNDDOWN((uintptr_t)objects[0], PGSIZE) ==
                           ROUNDDOWN((uintptr_t)objects[1], PGSIZE));
    for (unsigned i = 0; i < 600; i += 2) kfree(objects[i]);
    for (unsigned i = 0; i < 600; i += 2) {
        objects[i] = kmalloc(size); assert(objects[i]); pattern_write(objects[i], size, i);
    }
    assert(nr_free_pages() == full_free);
    for (unsigned i = 0; i < 600; i++) {
        pattern_check(objects[i], size, i); kfree(objects[i]);
    }
    assert(nr_free_pages() == before);
    cprintf("[SLUB] class=%lu full/partial/empty reuse: PASS\n", size);
    }
}

static void existing_slab_when_pages_exhausted(void) {
    size_t before = nr_free_pages(), count = 0;
    void *first = kmalloc(31); assert(first);
    pattern_write(first, 31, 91);
    struct Page *p;
    while ((p = alloc_pages(1)) != NULL) {
        assert(count < sizeof(exhausted) / sizeof(exhausted[0]));
        exhausted[count++] = p;
    }
    assert(nr_free_pages() == 0);
    void *second = kmalloc(31);
    assert(second && ROUNDDOWN((uintptr_t)first, PGSIZE) ==
                     ROUNDDOWN((uintptr_t)second, PGSIZE));
    assert(!kmalloc(2048) && nr_free_pages() == 0);
    pattern_write(second, 31, 93);
    pattern_check(first, 31, 91); pattern_check(second, 31, 93);
    kfree(second); kfree(first);
    for (size_t i = count; i; i--) free_pages(exhausted[i - 1], 1);
    assert(nr_free_pages() == before);
    cprintf("[SLUB] existing slab usable with zero free physical pages: PASS\n");
}
static void random_checks(void) {
    size_t before = nr_free_pages();
    for (unsigned step = 0; step < 512; step++) {
        unsigned s = random_next() % 64;
        for (unsigned j = 0; j < 64; j++)
            if (active[j]) pattern_check(active[j], requested[j], j + 7);
        if (active[s]) { kfree(active[s]); active[s] = NULL; }
        else {
            size_t n = 1 + random_next() % 12000;
            size_t old = nr_free_pages();
            void *p = kmalloc(n);
            if (!p) { assert(nr_free_pages() == old); continue; }
            assert(!((uintptr_t)p % 16));
            for (unsigned j = 0; j < 64; j++)
                if (active[j]) nonoverlap(p, n, active[j], requested[j]);
            active[s] = p; requested[s] = n; pattern_write(p, n, s + 7);
        }
    }
    for (unsigned j = 0; j < 64; j++) if (active[j]) {
        pattern_check(active[j], requested[j], j + 7);
        kfree(active[j]); active[j] = NULL;
    }
    assert(nr_free_pages() == before);
    cprintf("[SLUB] seeded mixed allocation/free: PASS\n");
}
static void exhaustion_checks(void) {
    size_t before = nr_free_pages(), n = 0;
    void *sentinel = kmalloc(31); assert(sentinel); pattern_write(sentinel, 31, 57);
    for (;;) {
        size_t old = nr_free_pages();
        void *p = kmalloc(PGSIZE);
        if (!p) { assert(nr_free_pages() == old); break; }
        assert(n < sizeof(exhausted) / sizeof(exhausted[0]));
        exhausted[n++] = p;
        pattern_write(p, PGSIZE, n);
    }
    assert(n > 0);
    pattern_check(sentinel, 31, 57);
    for (size_t i = n; i; i--) {
        pattern_check(exhausted[i - 1], PGSIZE, i); kfree(exhausted[i - 1]);
    }
    kfree(sentinel);
    assert(nr_free_pages() == before);
    cprintf("[SLUB] backend exhaustion, rollback and recovery: PASS\n");
}
#endif

void slub_check(void) {
    size_t before = nr_free_pages();
    void *p = kmalloc(24);
    assert(p && !((uintptr_t)p % 16));
    pattern_write(p, 24, 1); pattern_check(p, 24, 1); kfree(p);
    assert(nr_free_pages() == before);
#ifdef LAB2_EXT_TEST
    boundary_checks(); reuse_checks(); random_checks(); exhaustion_checks();
    existing_slab_when_pages_exhausted();
    cprintf("[SLUB] ALL TESTS PASS; baseline=%lu restored=%lu\n", before, nr_free_pages());
#else
    cprintf("[SLUB] smoke check PASS (full tests disabled)\n");
#endif
}
