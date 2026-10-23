#ifndef LAB2_BUDDY_INTERNAL_H
#define LAB2_BUDDY_INTERNAL_H
#include <pmm.h>
/* Private core shared with the isolated metadata tests; not a public allocator API.
 * Coordinates are descriptor indices relative to ctx->base (global pages in PMM).
 * Each init_memmap call is its own merge domain. */
#define BUDDY_MAX_ORDER 15
#define BUDDY_CAPACITY (1U << BUDDY_MAX_ORDER)
enum { B_UNREGISTERED, B_TAIL, B_FREE, B_ALLOCATED };
struct buddy_meta { unsigned request, domain, order, state; };
struct buddy_context {
    struct Page *base;
    struct buddy_meta *meta;
    size_t capacity, available;
    unsigned next_domain;
    list_entry_t lists[BUDDY_MAX_ORDER + 1];
};
void buddy_core_init(struct buddy_context *, struct Page *, struct buddy_meta *, size_t);
void buddy_core_register(struct buddy_context *, size_t, size_t);
struct Page *buddy_core_alloc(struct buddy_context *, size_t);
void buddy_core_free(struct buddy_context *, struct Page *, size_t);
#endif
