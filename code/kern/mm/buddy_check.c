// lab2 independent Buddy tests: initial version 2511565; coverage improved 2511057; final review 2511955.
#include <buddy_pmm.h>
#include <buddy_internal.h>
#include <stdio.h>

#ifdef LAB2_EXT_TEST
static struct Page isolated_pages[64];
static struct buddy_meta isolated_meta[64];
static struct buddy_context isolated;
static struct Page *held[BUDDY_CAPACITY];
static unsigned char owned[BUDDY_CAPACITY];

static void reset_isolated(void) {
    /* Metadata-only instance: never use page2pa or dereference simulated RAM. */
    buddy_core_init(&isolated, isolated_pages, isolated_meta, 64);
    for (unsigned i = 0; i < 64; i++) {
        isolated_pages[i].flags = 0;
        SetPageReserved(&isolated_pages[i]);
    }
}

static void isolated_checks(void) {
    reset_isolated();
    buddy_core_register(&isolated, 0, 16);
    struct Page *a = buddy_core_alloc(&isolated, 3);
    struct Page *b = buddy_core_alloc(&isolated, 5);
    assert(a == isolated_pages && b == isolated_pages + 8);
    assert(isolated.available == 4);
    buddy_core_free(&isolated, a, 3);
    buddy_core_free(&isolated, b, 5);
    assert(buddy_core_alloc(&isolated, 16) == isolated_pages);
    buddy_core_free(&isolated, isolated_pages, 16);
    assert(isolated.available == 16);
    cprintf("[Buddy] split and recursive merge: PASS\n");

    reset_isolated();
    buddy_core_register(&isolated, 0, 4);
    struct Page *p[4];
    for (unsigned i = 0; i < 4; i++) {
        p[i] = buddy_core_alloc(&isolated, 1);
        assert(p[i] == isolated_pages + i);
    }
    buddy_core_free(&isolated, p[1], 1);
    buddy_core_free(&isolated, p[2], 1);
    assert(isolated.available == 2 && buddy_core_alloc(&isolated, 2) == NULL);
    buddy_core_free(&isolated, p[0], 1);
    buddy_core_free(&isolated, p[3], 1);
    assert(buddy_core_alloc(&isolated, 4) == isolated_pages);
    buddy_core_free(&isolated, isolated_pages, 4);
    cprintf("[Buddy] adjacent non-buddies: PASS\n");

    reset_isolated();
    buddy_core_register(&isolated, 3, 13);   // [3,16)
    buddy_core_register(&isolated, 20, 7);   // [20,27), hole between
    unsigned seen[64] = {0};
    for (unsigned i = 0; i < 20; i++) {
        struct Page *q = buddy_core_alloc(&isolated, 1);
        assert(q);
        size_t at = q - isolated_pages;
        assert((at >= 3 && at < 16) || (at >= 20 && at < 27));
        assert(!seen[at]);
        seen[at] = 1;
        held[i] = q;
    }
    assert(isolated.available == 0 && !buddy_core_alloc(&isolated, 1));
    for (unsigned i = 20; i; i--) buddy_core_free(&isolated, held[i - 1], 1);
    assert(isolated.available == 20 && !buddy_core_alloc(&isolated, 16));
    /* Adjacent registrations remain distinct merge domains. */
    reset_isolated();
    buddy_core_register(&isolated, 0, 2);
    buddy_core_register(&isolated, 2, 2);
    assert(isolated.available == 4 && !buddy_core_alloc(&isolated, 4));
    assert(!buddy_core_alloc(&isolated, 0));
    assert(!buddy_core_alloc(&isolated, (size_t)-1));
    assert(isolated.available == 4);
    cprintf("[Buddy] irregular ranges, holes, domains, invalid sizes: PASS\n");
}

static unsigned rng = 2511057;
static unsigned random_next(void) {
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    return rng;
}
static struct Page *active[64];
static size_t requests[64];
static unsigned char patterns[64];

static size_t rounded(size_t n) {
    size_t r = 1;
    while (r < n) r *= 2;
    return r;
}
static unsigned char *ram(struct Page *p) {
    return (unsigned char *)(page2pa(p) + va_pa_offset);
}
static void verify_active(void) {
    for (unsigned s = 0; s < 64; s++) if (active[s]) {
        unsigned char *v = ram(active[s]);
        for (size_t i = 0; i < rounded(requests[s]) * PGSIZE; i++)
            assert(v[i] == patterns[s]);
    }
}

static void shuffled_merge_checks(void) {
    const unsigned seeds[] = {2511057U, 0x9e3779b9U, 0xa5a5f00dU};
    for (unsigned trial = 0; trial < sizeof(seeds) / sizeof(seeds[0]); trial++) {
        struct Page *order[64];
        rng = seeds[trial];
        reset_isolated();
        buddy_core_register(&isolated, 0, 64);
        for (unsigned i = 0; i < 64; i++) {
            order[i] = buddy_core_alloc(&isolated, 1);
            assert(order[i]);
        }
        for (unsigned i = 64; i > 1; i--) {
            unsigned j = random_next() % i;
            struct Page *tmp = order[i - 1];
            order[i - 1] = order[j]; order[j] = tmp;
        }
        for (unsigned i = 0; i < 63; i++) buddy_core_free(&isolated, order[i], 1);
        assert(!buddy_core_alloc(&isolated, 64));
        buddy_core_free(&isolated, order[63], 1);
        struct Page *whole = buddy_core_alloc(&isolated, 64);
        assert(whole == isolated_pages && isolated.available == 0);
        buddy_core_free(&isolated, whole, 64);
        assert(isolated.available == 64);
    }
    cprintf("[Buddy] shuffled 64-page merge, three seeds: PASS\n");
}

/* Snapshot an actually allocatable order; total free pages alone are not
 * evidence that the largest aligned block exists after later recovery. */
static size_t largest_available_block(void) {
    size_t largest = 0;
    for (size_t n = 1; n <= BUDDY_CAPACITY; n *= 2) {
        struct Page *p = alloc_pages(n);
        if (!p) break;
        largest = n;
        free_pages(p, n);
    }
    return largest;
}

static void check_large_recovery(size_t n, size_t before) {
    struct Page *p = alloc_pages(n);
    assert(p && nr_free_pages() == before - n);
    free_pages(p, n);
    assert(nr_free_pages() == before);
}

static void live_checks(void) {
    size_t before = nr_free_pages(), capacity = npage - nbase;
    size_t largest = largest_available_block();
    assert(largest > 0 && nr_free_pages() == before);
    assert(capacity <= BUDDY_CAPACITY);
    assert(!alloc_pages(0) && !alloc_pages((size_t)-1));
    assert(nr_free_pages() == before);
    const unsigned seeds[] = {2511057U, 0x9e3779b9U, 0xa5a5f00dU};
    for (unsigned trial = 0; trial < sizeof(seeds) / sizeof(seeds[0]); trial++) {
    unsigned allocations = 0, releases = 0;
    rng = seeds[trial];
    for (size_t i = 0; i < capacity; i++) owned[i] = 0;
    for (unsigned step = 0; step < 512; step++) {
        unsigned s = random_next() % 64;
        size_t request = 1 + random_next() % 17, count = rounded(request);
        verify_active();
        if (active[s]) {
            size_t at = active[s] - pages, count = rounded(requests[s]);
            for (size_t i = at; i < at + count; i++) { assert(owned[i]); owned[i] = 0; }
            size_t old = nr_free_pages();
            free_pages(active[s], requests[s]);
            assert(nr_free_pages() == old + count);
            active[s] = NULL;
            releases++;
        } else {
            size_t old = nr_free_pages();
            struct Page *p = alloc_pages(request);
            if (!p) { assert(old == nr_free_pages()); continue; }
            size_t at = p - pages;
            assert(at < capacity && count <= capacity - at && !(at % count));
            for (size_t i = at; i < at + count; i++) {
                assert(!owned[i] && !PageReserved(pages + i)); owned[i] = 1;
            }
            assert(nr_free_pages() == old - count);
            active[s] = p; requests[s] = request; patterns[s] = 1 + s;
            unsigned char *v = ram(p);
            for (size_t i = 0; i < count * PGSIZE; i++) v[i] = patterns[s];
            allocations++;
        }
    }
    verify_active();
    for (unsigned i = 0; i < 64; i++) if (active[i]) {
        free_pages(active[i], requests[i]); active[i] = NULL;
    }
    assert(nr_free_pages() == before);
    check_large_recovery(largest, before);
    cprintf("[Buddy] seed=%u alloc=%u free=%u, contents/non-overlap/large-block: PASS\n",
            seeds[trial], allocations, releases);
    }

    for (size_t i = 0; i < capacity; i++) owned[i] = 0;
    size_t used = 0;
    struct Page *p;
    while ((p = alloc_pages(1)) != NULL) {
        assert(used < BUDDY_CAPACITY);
        size_t at = p - pages;
        assert(at < capacity && !owned[at]); owned[at] = 1;
        held[used++] = p;
        ram(p)[0] = (unsigned char)at;
    }
    assert(used == before && nr_free_pages() == 0);
    for (size_t i = used; i; i--) {
        p = held[i - 1]; assert(ram(p)[0] == (unsigned char)(p - pages));
        free_pages(p, 1);
    }
    assert(nr_free_pages() == before);
    check_large_recovery(largest, before);
    cprintf("[Buddy] exhaustion and recovery (largest=%lu pages): PASS\n", largest);
}
#endif

void buddy_check(void) {
    size_t before = nr_free_pages();
    if (!before) { cprintf("[Buddy] no free pages; smoke check skipped\n"); return; }
    struct Page *p = alloc_pages(1);
    assert(p && nr_free_pages() == before - 1);
    free_pages(p, 1);
    assert(nr_free_pages() == before);
#ifdef LAB2_EXT_TEST
    isolated_checks();
    shuffled_merge_checks();
    live_checks();
    cprintf("[Buddy] ALL TESTS PASS; baseline=%lu restored=%lu\n", before, nr_free_pages());
#else
    cprintf("[Buddy] smoke check PASS (full tests disabled)\n");
#endif
}
