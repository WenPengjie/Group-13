// lab2 simplified SLUB: initial implementation 2511565; bitmap improvement 2511057; final review 2511955.
// Single CPU / externally serialized calls.
#include <slub.h>
#include <pmm.h>
#include <list.h>

#define SLAB_MAGIC 0x2511565a51ab2026ULL
#define LARGE_MAGIC 0x2511565a1a492026ULL
#define CLASSES 8
#define BITMAP_WORDS 4  // 256 bits cover every 16-byte slot in one page
static const size_t sizes[CLASSES] = {16, 32, 64, 128, 256, 512, 1024, 2048};
struct slab_header {
    uint64_t magic;
    list_entry_t link;
    struct Page *page;
    size_t page_request, stride, capacity, inuse;
    void *free;
    unsigned class_id;
    uint64_t allocated[BITMAP_WORDS];
};
#define HEADER_SIZE ((sizeof(struct slab_header) + 15) & ~(size_t)15)
static list_entry_t partial[CLASSES];
static size_t live_blocks;
static int initialized;

void slub_init(void) {
    assert(!initialized || live_blocks == 0);
    for (unsigned i = 0; i < CLASSES; i++) list_init(&partial[i]);
    live_blocks = 0;
    initialized = 1;
}

static struct slab_header *new_block(size_t n) {
    struct Page *p = alloc_pages(n);
    if (!p) return NULL;
    uintptr_t pa = page2pa(p);
    assert(pa >= KERNEL_BEGIN_PADDR && pa < PHYSICAL_MEMORY_END);
    struct slab_header *h = (void *)(pa + va_pa_offset);
    h->page = p;
    h->page_request = n;
    list_init(&h->link);
    live_blocks++;
    return h;
}

void *kmalloc(size_t size) {
    assert(initialized);
    if (!size) return NULL;
    unsigned c = 0;
    while (c < CLASSES && sizes[c] < size) c++;
    if (c == CLASSES) {
        if (size > (size_t)-1 - HEADER_SIZE) return NULL;
        size_t bytes = size + HEADER_SIZE;
        /* quotient + remainder avoids the usual bytes+PGSIZE-1 overflow */
        size_t n = bytes / PGSIZE + (bytes % PGSIZE != 0);
        struct slab_header *h = new_block(n);
        if (!h) return NULL;
        h->magic = LARGE_MAGIC;
        return (char *)h + HEADER_SIZE;
    }
    struct slab_header *h;
    if (list_empty(&partial[c])) {
        h = new_block(1);
        if (!h) return NULL;
        h->magic = SLAB_MAGIC;
        h->class_id = c;
        h->stride = sizes[c];
        h->capacity = (PGSIZE - HEADER_SIZE) / h->stride;
        assert(h->capacity > 0 && h->capacity <= BITMAP_WORDS * 64);
        for (unsigned i = 0; i < BITMAP_WORDS; i++) h->allocated[i] = 0;
        h->inuse = 0;
        h->free = NULL;
        for (size_t i = h->capacity; i; i--) {
            void *slot = (char *)h + HEADER_SIZE + (i - 1) * h->stride;
            *(void **)slot = h->free;
            h->free = slot;
        }
        list_add(&partial[c], &h->link);
    } else h = to_struct(list_next(&partial[c]), struct slab_header, link);
    void *out = h->free;
    assert(out && h->inuse < h->capacity);
    size_t slot = ((uintptr_t)out - (uintptr_t)h - HEADER_SIZE) / h->stride;
    uint64_t bit = (uint64_t)1 << (slot % 64);
    assert(slot < h->capacity && !(h->allocated[slot / 64] & bit));
    h->allocated[slot / 64] |= bit;
    h->free = *(void **)out;
    h->inuse++;
    if (h->inuse == h->capacity) list_del_init(&h->link);
    return out;
}

void kfree(void *ptr) {
    if (!ptr) return;
    assert(initialized);
    struct slab_header *h = (void *)ROUNDDOWN((uintptr_t)ptr, PGSIZE);
    if (h->magic == LARGE_MAGIC) {
        assert(ptr == (char *)h + HEADER_SIZE);
        struct Page *p = h->page;
        size_t n = h->page_request;
        h->magic = 0;
        live_blocks--;
        free_pages(p, n);
        return;
    }
    assert(h->magic == SLAB_MAGIC && h->class_id < CLASSES && h->inuse);
    size_t offset = (uintptr_t)ptr - (uintptr_t)h;
    assert(offset >= HEADER_SIZE && (offset - HEADER_SIZE) % h->stride == 0);
    assert((offset - HEADER_SIZE) / h->stride < h->capacity);
    /* lab2 2511057: constant-time diagnosis for a still-live slab.
     * Arbitrary invalid pointers / use-after-free remain outside the contract. */
    size_t slot = (offset - HEADER_SIZE) / h->stride;
    uint64_t bit = (uint64_t)1 << (slot % 64);
    assert(h->allocated[slot / 64] & bit);
    h->allocated[slot / 64] &= ~bit;
    if (h->inuse == h->capacity) list_add(&partial[h->class_id], &h->link);
    *(void **)ptr = h->free;
    h->free = ptr;
    if (--h->inuse == 0) {
        struct Page *p = h->page;
        list_del_init(&h->link);
        h->magic = 0;
        live_blocks--;
        free_pages(p, 1);
    }
}
