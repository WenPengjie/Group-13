#ifndef LAB2_SLUB_H
#define LAB2_SLUB_H
#include <defs.h>
/* Single CPU / externally serialized calls. Returned storage is >=16-byte
 * aligned but is not zeroed. kmalloc(0) returns NULL; kfree(NULL) is a no-op.
 * kfree accepts only a live, unmodified original return pointer. */
void slub_init(void);
void *kmalloc(size_t size);
void kfree(void *ptr);
void slub_check(void);
#endif
