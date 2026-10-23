// lab2 Buddy implementation 2511565; final review 2511955
#include <buddy_pmm.h>
#include <buddy_internal.h>

static struct buddy_context system_buddy;
/* In kernel BSS: page_init reserves these bytes as part of the kernel image. */
static struct buddy_meta system_meta[BUDDY_CAPACITY];

static int request_order(size_t n) {
    if (!n || n > BUDDY_CAPACITY) return -1;
    unsigned order = 0;
    while (((size_t)1 << order) < n) order++;
    return order;
}

void buddy_core_init(struct buddy_context *c, struct Page *base,
                     struct buddy_meta *meta, size_t capacity) {
    assert(capacity <= BUDDY_CAPACITY);
    c->base = base;
    c->meta = meta;
    c->capacity = capacity;
    c->available = c->next_domain = 0;
    for (unsigned i = 0; i <= BUDDY_MAX_ORDER; i++) list_init(&c->lists[i]);
    for (size_t i = 0; i < capacity; i++) {
        meta[i].request = meta[i].domain = meta[i].order = 0;
        meta[i].state = B_UNREGISTERED;
    }
}

static void add_free(struct buddy_context *c, size_t i, unsigned order) {
    c->meta[i].state = B_FREE;
    c->meta[i].order = order;
    c->meta[i].request = 0;
    c->base[i].property = (size_t)1 << order;
    SetPageProperty(&c->base[i]);
    list_add(&c->lists[order], &c->base[i].page_link);
}

static void remove_free(struct buddy_context *c, size_t i) {
    list_del_init(&c->base[i].page_link);
    ClearPageProperty(&c->base[i]);
    c->base[i].property = 0;
    c->meta[i].state = B_TAIL;
}

void buddy_core_register(struct buddy_context *c, size_t start, size_t n) {
    assert(n && start < c->capacity && n <= c->capacity - start);
    assert(c->next_domain != ~0U);
    /* Validate the entire interval before changing any descriptor. */
    for (size_t i = start; i < start + n; i++)
        assert(c->meta[i].state == B_UNREGISTERED && PageReserved(&c->base[i]));
    unsigned domain = ++c->next_domain;
    for (size_t i = start; i < start + n; i++) {
        c->meta[i].state = B_TAIL;
        c->meta[i].domain = domain;
        c->base[i].flags = c->base[i].property = 0;
        set_page_ref(&c->base[i], 0);
        list_init(&c->base[i].page_link);
    }
    size_t at = start, left = n;
    while (left) {
        unsigned order = 0;
        while (order < BUDDY_MAX_ORDER) {
            size_t larger = (size_t)1 << (order + 1);
            if (larger > left || (at & (larger - 1))) break;
            order++;
        }
        add_free(c, at, order);
        size_t block = (size_t)1 << order;
        at += block;
        left -= block;
    }
    c->available += n;
}

struct Page *buddy_core_alloc(struct buddy_context *c, size_t n) {
    int wanted = request_order(n);
    if (wanted < 0 || ((size_t)1 << wanted) > c->available) return NULL;
    unsigned order = wanted;
    while (order <= BUDDY_MAX_ORDER && list_empty(&c->lists[order])) order++;
    if (order > BUDDY_MAX_ORDER) return NULL;
    struct Page *p = le2page(list_next(&c->lists[order]), page_link);
    size_t i = p - c->base;
    remove_free(c, i);
    while (order > (unsigned)wanted) {
        order--;
        add_free(c, i + ((size_t)1 << order), order);
    }
    c->meta[i].state = B_ALLOCATED;
    c->meta[i].order = wanted;
    c->meta[i].request = n;
    c->available -= (size_t)1 << wanted;
    return p;
}

void buddy_core_free(struct buddy_context *c, struct Page *p, size_t n) {
    uintptr_t addr = (uintptr_t)p, lo = (uintptr_t)c->base;
    assert(addr >= lo && addr - lo < c->capacity * sizeof(*p));
    assert((addr - lo) % sizeof(*p) == 0);
    size_t i = (addr - lo) / sizeof(*p);
    assert(c->meta[i].state == B_ALLOCATED && c->meta[i].request == n);
    unsigned order = c->meta[i].order, domain = c->meta[i].domain;
    size_t released = (size_t)1 << order;
    for (size_t j = i; j < i + released; j++) set_page_ref(&c->base[j], 0);
    c->meta[i].state = B_TAIL;
    c->meta[i].request = 0;
    while (order < BUDDY_MAX_ORDER) {
        size_t partner = i ^ ((size_t)1 << order);
        if (partner >= c->capacity || c->meta[partner].state != B_FREE ||
            c->meta[partner].order != order || c->meta[partner].domain != domain)
            break;
        remove_free(c, partner);
        if (partner < i) i = partner;
        order++;
    }
    add_free(c, i, order);
    c->available += released;  // merging never creates extra free pages
}

static void buddy_init(void) {
    /* pages/npage are set later by page_init; bind the real descriptor range
     * on the first registration, not here. */
    buddy_core_init(&system_buddy, NULL, system_meta, BUDDY_CAPACITY);
}
static void buddy_init_memmap(struct Page *base, size_t n) {
    assert(npage >= nbase && npage - nbase <= BUDDY_CAPACITY);
    system_buddy.base = pages;
    system_buddy.capacity = npage - nbase;
    assert(base >= pages && base < pages + system_buddy.capacity);
    buddy_core_register(&system_buddy, base - pages, n);
}
static struct Page *buddy_alloc_pages(size_t n) { return buddy_core_alloc(&system_buddy, n); }
static void buddy_free_pages(struct Page *p, size_t n) { buddy_core_free(&system_buddy, p, n); }
static size_t buddy_nr_free_pages(void) { return system_buddy.available; }
const struct pmm_manager buddy_pmm_manager = {
    .name = "buddy_pmm_manager", .init = buddy_init,
    .init_memmap = buddy_init_memmap, .alloc_pages = buddy_alloc_pages,
    .free_pages = buddy_free_pages, .nr_free_pages = buddy_nr_free_pages,
    .check = buddy_check,
};
