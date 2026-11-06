    .text
    .align 2
    .globl extended_register_context
extended_register_context:
    # Preserve our caller's ABI state while checking the interrupted state.
    addi sp, sp, -128
    sd s0, 0(sp)
    sd s1, 8(sp)
    sd s2, 16(sp)
    sd s3, 24(sp)
    sd s4, 32(sp)
    sd s5, 40(sp)
    sd s6, 48(sp)
    sd s7, 56(sp)
    sd s8, 64(sp)
    sd s9, 72(sp)
    sd s10, 80(sp)
    sd s11, 88(sp)
    sd ra, 96(sp)
    sd gp, 104(sp)
    sd tp, 112(sp)
    sd sp, 120(sp)
    li ra, 0x101
    li t0, 0x105
    li t1, 0x106
    li t2, 0x107
    li s0, 0x108
    li s1, 0x109
    li a0, 0x10a
    li a1, 0x10b
    li a2, 0x10c
    li a3, 0x10d
    li a4, 0x10e
    li a5, 0x10f
    li a6, 0x110
    li a7, 0x111
    li s2, 0x112
    li s3, 0x113
    li s4, 0x114
    li s5, 0x115
    li s6, 0x116
    li s7, 0x117
    li s8, 0x118
    li s9, 0x119
    li s10, 0x11a
    li s11, 0x11b
    li t3, 0x11c
    li t4, 0x11d
    li t5, 0x11e
    li t6, 0x11f
    .balign 4
    # Explicit encodings prevent the assembler from hiding a length error.
    # The 32-bit ebreak starts at an address congruent to 2 modulo 4.
    .2byte 0x9002
    .4byte 0x00100073

    addi t0, t0, -0x105
    bnez t0, .Lfail
    .macro CHECK reg, value
    li t0, \value
    bne \reg, t0, .Lfail
    .endm
    CHECK ra, 0x101
    CHECK t1, 0x106
    CHECK t2, 0x107
    CHECK s0, 0x108
    CHECK s1, 0x109
    CHECK a0, 0x10a
    CHECK a1, 0x10b
    CHECK a2, 0x10c
    CHECK a3, 0x10d
    CHECK a4, 0x10e
    CHECK a5, 0x10f
    CHECK a6, 0x110
    CHECK a7, 0x111
    CHECK s2, 0x112
    CHECK s3, 0x113
    CHECK s4, 0x114
    CHECK s5, 0x115
    CHECK s6, 0x116
    CHECK s7, 0x117
    CHECK s8, 0x118
    CHECK s9, 0x119
    CHECK s10, 0x11a
    CHECK s11, 0x11b
    CHECK t3, 0x11c
    CHECK t4, 0x11d
    CHECK t5, 0x11e
    CHECK t6, 0x11f
    ld t0, 104(sp)
    bne gp, t0, .Lfail
    ld t0, 112(sp)
    bne tp, t0, .Lfail
    ld t0, 120(sp)
    bne sp, t0, .Lfail
    li a0, 0
    j .Lreturn
.Lfail:
    li a0, 1
.Lreturn:
    ld s0, 0(sp)
    ld s1, 8(sp)
    ld s2, 16(sp)
    ld s3, 24(sp)
    ld s4, 32(sp)
    ld s5, 40(sp)
    ld s6, 48(sp)
    ld s7, 56(sp)
    ld s8, 64(sp)
    ld s9, 72(sp)
    ld s10, 80(sp)
    ld s11, 88(sp)
    ld ra, 96(sp)
    addi sp, sp, 128
    ret
