/* ------------------------------------------------------------------ per-film colour mix (feature/rgb-curves, m1)
 * A 3 x 3 colour matrix of ours per COLOR / film, put into the camera's own colour matrix for COLOR jobs.
 * The matrix function 0x605147a2 (research/NOTES.md, "Colour matrix per film") builds the job's matrix from the
 * camera's base matrix (a filter's, a picture mode's), then 0x605144ef scales each row to sum 128 and writes the job's
 * nine values. .hook_mx takes that last call (0x6051485a): for a COLOR job (key 11, or 12 with no filter, as split
 * toning) of the development function split toning runs in (its caller 0x605196f6: photos and live view; the other
 * caller 0x6051a6fb is left stock), when COLOR k has a mix, ours x the matrix so far (the camera's own 3 x 3 multiply
 * 0x60514290: ours acts on the camera's colours), then the camera's row scaling, so greys stay grey.
 * The mix: the 8 bytes each slot kept since test 1b (cv_ram slot + 18): six s8 off-diagonal values, R row (G, B),
 * G row (R, B), B row (R, G), each MX_UNIT / 256; the diagonal makes each row 256. Bytes 6, 7 stay 0. All 0 = stock.
 * Nothing before the films are read at the first half-press (cv_ok), as split toning. MX_PROBE (test m1): COLOR
 * MX_PK uses the fixed probe mix mx_pr instead (nothing stored). */
 .set MX_UNIT, 4                  /* one step = 4 / 256 */
 .set MX_PROBE, 1                 /* m1: the camera probe */
 .set MX_PK, 2                    /* m1: COLOR 3 */

.section .hook_mx,"ax"
 jmp mx_go                        /* stock 0x6051485a: call 0x605144ef,[d2,d3,a2,a3],20 */

.section .ext12,"ax"
/* mx_go <- .hook_mx, in the matrix function's frame F (84: (84,F) its return address, (96,F) the request R for the
 * caller 0x605196f6); d3 the key, a2 the matrix so far, a0 = d2 = F + 48 the output. Ends as the stock call, then
 * MX_BACK with d2, d3 as they came (the rest of the function uses them). Our frame: movm 16 B, then 32: (0) call slot,
 * (4..21) our matrix, (24) the matrix so far, (28) the free work matrix. Uses d0, d1, a0, a1, MDR. */
 .set MXF, 48                     /* (x, F) = (x + MXF, sp) */
mx_go:
 movm [d2,d3,a2,a3],(sp)
 add -32,sp
 mov a2,(24,sp)
 movbu (cv_ok),d0                 /* nothing before the films are read (first half-press) */
 cmp 0,d0
 beq 80f
 mov (84 + MXF,sp),d0             /* the development function split toning runs in */
 cmp MX_RET,d0
 bne 80f
 cmp 11,d3
 beq 1f
 cmp 12,d3
 bne 80f
 mov (96 + MXF,sp),a0             /* 12: only with no filter (as split toning) */
 movbu (1731,a0),d0
 cmp 0,d0
 bne 80f
1:
 .if MX_PROBE == 0
 call mx_any,[d2],8               /* no mix on any COLOR: no getter call */
 cmp 0,d0
 beq 80f
 .endif
 mov 63153,d0                     /* effective COLOR profile number (as st_run) */
 clr d1
 mov 0,a0
 call getter,[d2,d3],12
 add -1,d0
 cmp 4,d0
 bcc 80f
 mov CV_ESZ,d1                    /* COLOR k's six values */
 mul d0,d1
 mov cv_ram + CV_LV + 18,a1
 add d1,a1
 .if MX_PROBE
 cmp MX_PK,d0
 bne 2f
 mov mx_pr,a1
2:
 .endif
 mov a1,a0
 clr d0
 mov 6,d1
3:
 movbu (a0),d2
 or d2,d0
 inc a0
 add -1,d1
 bne 3b
 cmp 0,d0
 beq 80f                          /* no mix: stock */
 mov sp,a0                        /* our matrix at (4,sp), s16, 256 = 1.0 */
 add 4,a0
 clr d3                           /* row r: its two values at a1 + 2r, the diagonal at column r */
4:
 movbu (a1),d0
 extb d0
 mov MX_UNIT,d2
 mul d2,d0
 movbu (1,a1),d1
 extb d1
 mul d2,d1
 mov 256,d2
 sub d0,d2
 sub d1,d2                        /* the diagonal */
 cmp 0,d3
 bne 5f
 movhu d2,(a0)                    /* R row: d, G, B */
 movhu d0,(2,a0)
 movhu d1,(4,a0)
 bra 7f
5:
 cmp 1,d3
 bne 6f
 movhu d0,(a0)                    /* G row: R, d, B */
 movhu d2,(2,a0)
 movhu d1,(4,a0)
 bra 7f
6:
 movhu d0,(a0)                    /* B row: R, G, d */
 movhu d1,(2,a0)
 movhu d2,(4,a0)
7:
 add 6,a0
 add 2,a1
 inc d3
 cmp 3,d3
 bcs 4b
 mov sp,a0                        /* the free work matrix of the function: F + 8, or F + 28 when the matrix so far */
 mov a0,d0                        /* is there */
 add MXF + 8,d0
 mov (24,sp),d1
 cmp d0,d1
 bne 8f
 add 20,d0
8:
 mov d0,(28,sp)
 mov d0,a0                        /* ours x the matrix so far (ours acts on the camera's colours) */
 mov sp,a1
 add 4,a1
 mov (24,sp),d0
 call mx_mul,[d2,d3,a2,a3],116
 mov (28,sp),d0
 mov d0,(24,sp)
 mov (mx_n),d0
 inc d0
 mov d0,(mx_n)
80:
 mov sp,a0                        /* the stock call: a0 = F + 48, a1 = the matrix */
 add MXF + 48,a0
 mov (24,sp),a1
 call mx_row,[d2,d3,a2,a3],20
 add 32,sp
 movm (sp),[d2,d3,a2,a3]
 jmp MX_BACK

/* mx_any: `call mx_any,[d2],8` -> d0 != 0 when any COLOR has a mix. Uses d0, d1, a0, a1. */
mx_any:
 mov cv_ram + CV_LV + 18,a1
 clr d0
 mov 4,d1
1:
 mov a1,a0
 movbu (a0),d2
 or d2,d0
 movbu (1,a0),d2
 or d2,d0
 movbu (2,a0),d2
 or d2,d0
 movbu (3,a0),d2
 or d2,d0
 movbu (4,a0),d2
 or d2,d0
 movbu (5,a0),d2
 or d2,d0
 add CV_ESZ,a1
 add -1,d1
 bne 1b
 ret [d2],8

 .balign 4
mx_n:                             /* matrices put in (a count, for om-emu) */
 .long 0
mx_pr:                            /* m1 probe: R' = 1.6 R - 0.6 G, G' = 1.6 G - 0.6 B, B' = 1.6 B - 0.6 R (each row
                                   * 256: greys stay grey; colours strongly moved; noise gain ~1.7, the worst case) */
 .byte -38, 0, 0, -38, -38, 0
 .balign 4
