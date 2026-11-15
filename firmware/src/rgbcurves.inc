/* ------------------------------------------------------------------ per-film R / G / B tone curves (feature/rgb-curves)
 * Each COLOR k has three curves (red, green, blue), 6 points each at input 0 / 10 / 25 / 50 / 75 / 100 % of the gamma
 * tables' 12-bit output, an offset -7..+7 of CV_STEP each (research/rgbcurves/model.py is the exact model). st_run
 * (split toning's pass over the job's R / G / B tables, camera-tested since v0.26) adds the curve's delta D(t) to each
 * entry of its channel, with split toning's own delta, then its clamp and running max. All zero = no work.
 * Values (cv_ram, a RAM image of record 'OM3R' at M + 0x3B100, which older firmware never reads):
 *   +0 magic 'OM3R', +4 u16 version 1, +6 u16 length CV_LEN, +8 CRC-32 of 12.., +12 the films block's generation
 *   when written (the record is used only with that block: a block written by older firmware drops the curves)
 *   +16 live[4][18]: COLOR k's curves now (R 6, G 6, B 6), as COLOR k's slot is its other rows now
 *   +88 ed[24][18]: the curves of EDITS record r (film j, COLOR k's own 20 + k), kept and used with that record
 *   +520 sets[6] {live[4][18], ed[24][18]}: per-mode settings, as the 'OM3S' sets (C1..C5, P group)
 * The curves follow the slot: whatever puts a record into COLOR k's slot (pf_put1, ss_slot) puts that record's
 * curves into live[k] (cv_rec: an EDITS record -> its ed[r], anything else -> flat); fl_sw's capture copies live[k]
 * into ed[r] (cv_cap); ss_put / ss_get / ss_ed copy them with the sets; e_rst clears them. */
 .set CV_LV, 16
 .set CV_ED, 88
 .set CV_SS, 520
 .set CV_SSZ, 504
 .set CV_LEN, CV_SS + 6 * CV_SSZ  /* 3544 */
 .set CV_C, 0x6295b800            /* M image 0x62920700 + 0x3B100 (after 'OM3C' at +0x3B000, before +0x3C000) */
 .set CV_U, 0xa295b800
 .set CV_MAGIC, 0x52334d4f        /* "OM3R" */
 .set CV_STEP, 48

.section .ext12,"ax"

/* cv_any: `call cv_any,[d2],8` -> d0 != 0 when any COLOR has a curve point set. Uses d0, d1, a0. */
cv_any:
 mov cv_ram + CV_LV,a0
 mov 18,d1
 clr d0
1:
 mov (a0),d2
 or d2,d0
 add 4,a0
 add -1,d1
 bne 1b
 ret [d2],8

/* cv_prm: `call cv_prm,[d2,d3,a2,a3],64`, a0 = a channel's 6 offsets (s8), a1 = its 16-word block: Y[6] (offset x
 * CV_STEP), A[5] (+24), B[5] (+44): each segment's Hermite tangent terms h m_i, h m_i+1 (>> 12). Tangents: the
 * harmonic mean of the two slopes (0 when they differ in sign or one is 0), the end ones the end slopes. Locals
 * (4..23) the slopes dQ[5] (Q12), (24..47) the tangents m[6]. Uses d0, d1, a0, a1, MDR. */
cv_prm:
 mov a0,a2
 mov a1,a3
 clr d2
1:
 movbu (d2,a2),d0
 extb d0
 cmp -7,d0
 bge 2f
 mov -7,d0
2:
 cmp 7,d0
 ble 3f
 mov 7,d0
3:
 mov CV_STEP,d1
 mul d1,d0
 mov d2,d1
 asl2 d1
 mov d0,(d1,a3)                   /* Y[i] */
 inc d2
 cmp 6,d2
 bne 1b
 mov a3,a0
 mov cv_h,a1
 mov sp,a2
 add 4,a2
 mov 5,d2
4:
 mov (4,a0),d0
 mov (a0),d1
 sub d1,d0
 asl 12,d0
 mov (a1),d1
 ext d0
 div d1,d0                        /* dQ[i] = (Y[i+1] - Y[i]) 4096 / h (truncated) */
 mov d0,(a2)
 add 4,a0
 add 4,a1
 add 4,a2
 add -1,d2
 bne 4b
 mov (4,sp),d0
 mov d0,(24,sp)                   /* m[0] = dQ[0] */
 mov (20,sp),d0
 mov d0,(44,sp)                   /* m[5] = dQ[4] */
 mov sp,a2
 add 4,a2
 mov 4,d3
5:
 mov (a2),d0                      /* a = dQ[i - 1] */
 mov (4,a2),d1                    /* b = dQ[i] */
 mov d0,d2
 xor d1,d2
 cmp 0,d2
 blt 6f                           /* signs differ */
 cmp 0,d0
 beq 6f
 cmp 0,d1
 beq 6f
 mov d0,d2
 add d1,d2
 mul d1,d0
 add d0,d0
 ext d0
 div d2,d0                        /* m[i] = 2 a b / (a + b) */
 bra 7f
6:
 clr d0
7:
 mov d0,(24,a2)                   /* m[i] at (24 + 4 i, sp) */
 add 4,a2
 add -1,d3
 bne 5b
 mov cv_h,a1
 mov sp,a2
 add 24,a2
 mov a3,a0
 add 24,a0
 mov 5,d3
8:
 mov (a1),d1
 mov (a2),d0
 mul d1,d0
 asr 12,d0
 mov d0,(a0)                      /* A[i] = h m[i] >> 12 */
 mov (4,a2),d0
 mul d1,d0
 asr 12,d0
 mov d0,(20,a0)                   /* B[i] = h m[i + 1] >> 12 */
 add 4,a1
 add 4,a2
 add 4,a0
 add -1,d3
 bne 8b
 ret [d2,d3,a2,a3],64

/* cv_d: `call cv_d,[d2,d3,a2,a3],44`, d0 = t (0..4095), d1 = a channel's block (cv_prm) -> d0 = D(t). Keeps a0, a1
 * (locals (4), (8)); (12) sum, (16) s, (20) s2, (24) s3. Uses d0, d1, MDR. */
cv_d:
 mov a0,(4,sp)
 mov a1,(8,sp)
 mov d1,a2
 cmp 410,d0
 bcc 1f
 clr d2
 clr d3
 bra 3f
1:
 cmp 1024,d0
 bcc 2f
 mov 1,d2
 mov 410,d3
 bra 3f
2:
 mov d0,d2
 lsr 10,d2
 inc d2                           /* i = 1 + (t >> 10) */
 mov d2,d3
 add -1,d3
 asl 10,d3                        /* X[i] */
3:
 sub d3,d0                        /* x */
 mov d2,d1
 asl2 d1
 mov cv_inv,a3
 add d1,a3
 mov (a3),d1
 mul d1,d0
 lsr 12,d0                        /* s (Q12) */
 mov d0,(16,sp)
 mov d0,d3
 mul d0,d0
 lsr 12,d0                        /* s2 */
 mov d0,(20,sp)
 mul d3,d0
 lsr 12,d0                        /* s3 */
 mov d0,(24,sp)
 asl2 d2
 add d2,a2                        /* &Y[i] */
 mov (20,sp),d1
 mov d0,d2                        /* h00 = 2 s3 - 3 s2 + 4096 */
 add d2,d2
 sub d1,d2
 sub d1,d2
 sub d1,d2
 add 4096,d2
 mov (a2),d3
 mul d3,d2
 mov d2,(12,sp)
 mov (20,sp),d2                   /* h01 = 3 s2 - 2 s3 */
 mov d2,d1
 add d1,d1
 add d1,d2
 mov (24,sp),d1
 sub d1,d2
 sub d1,d2
 mov (4,a2),d3
 mul d3,d2
 mov (12,sp),d3
 add d3,d2
 mov d2,(12,sp)
 mov (24,sp),d2                   /* h10 = s3 - 2 s2 + s */
 mov (20,sp),d1
 sub d1,d2
 sub d1,d2
 mov (16,sp),d1
 add d1,d2
 mov (24,a2),d3
 mul d3,d2
 mov (12,sp),d3
 add d3,d2
 mov d2,(12,sp)
 mov (24,sp),d2                   /* h11 = s3 - s2 */
 mov (20,sp),d1
 sub d1,d2
 mov (44,a2),d3
 mul d3,d2
 mov (12,sp),d3
 add d3,d2
 asr 12,d2
 mov d2,d0
 mov (4,sp),a0
 mov (8,sp),a1
 ret [d2,d3,a2,a3],44

/* cv_set: `call cv_set,[d2,d3,a2,a3],20`, d0 = COLOR k (0..3) -> d0 = its channels with a point set (bit c); their
 * blocks into cv_pb + 64 c and cv_pp[c] = that block, else 0. Uses d0, d1, a0, a1, MDR. */
cv_set:
 mov 18,d1
 mul d1,d0
 mov cv_ram + CV_LV,a2
 add d0,a2                        /* live[k] */
 clr d3
 clr d2
1:
 mov a2,a0
 mov 6,d1
2:
 movbu (a0),d0
 cmp 0,d0
 bne 3f
 inc a0
 add -1,d1
 bne 2b
 clr d0                           /* flat: no block */
 bra 4f
3:
 mov d2,d0
 asl 6,d0
 mov cv_pb,a1
 add d0,a1
 mov a2,a0
 call cv_prm,[d2,d3,a2,a3],64
 mov d2,d0
 asl 6,d0
 add cv_pb,d0
 mov 1,d1
 asl d2,d1
 or d1,d3
4:
 mov d2,d1
 asl2 d1
 mov cv_pp,a0
 add d1,a0
 mov d0,(a0)
 add 6,a2
 inc d2
 cmp 3,d2
 bne 1b
 mov d3,d0
 ret [d2,d3,a2,a3],20

/* cv_rid: `call cv_rid,[],0`, a2 = P, a3 = a record -> d0 = r when a3 is record r (0..23) of the EDITS image in use,
 * else -1. Uses d0, d1, a1. */
cv_rid:
 mov -1,d0
 mov (TORG,a2),a1
 cmp 0,a1
 beq 9f
 add TWO + 16,a1
 clr d1
1:
 cmp a3,a1
 beq 2f
 add 68,a1
 inc d1
 cmp 24,d1
 bne 1b
 ret [],0
2:
 mov d1,d0
9:
 ret [],0

/* cv_lk: `call cv_lk,[],0`, d0 = k -> a0 = live[k]. Uses d0, d1, a0, MDR. */
cv_lk:
 mov 18,d1
 mul d1,d0
 mov cv_ram + CV_LV,a0
 add d0,a0
 ret [],0

/* cv_rec: `call cv_rec,[d2,d3,a2,a3],20` (pf_put1, ss_slot: COLOR k's slot <- a record), a2 = P, d2 = k, a3 = the
 * record or 0 -> live[k] <- that record's curves: ed[r] for EDITS record r, else flat. Uses d0, d1, a0, a1, MDR. */
cv_rec:
 call cv_rid,[],0
 mov d0,d3
 mov d2,d0
 call cv_lk,[],0
 mov 0,a1
 cmp 0,d3
 blt 1f
 mov 18,d0
 mul d3,d0
 mov cv_ram + CV_ED,a1
 add d0,a1
1:
 mov 18,d1
2:
 clr d0
 cmp 0,a1
 beq 3f
 movbu (a1),d0
 inc a1
3:
 movbu d0,(a0)
 inc a0
 add -1,d1
 bne 2b
 ret [d2,d3,a2,a3],20

/* cv_cap: `call cv_cap,[d2,d3,a2,a3],20` (fl_sw, after pf_capto put COLOR k into EDITS record a3), a2 = P, d2 = k:
 * ed[r] <- live[k]. Uses d0, d1, a0, a1, MDR. */
cv_cap:
 call cv_rid,[],0
 cmp 0,d0
 blt 9f
 mov 18,d1
 mul d1,d0
 mov cv_ram + CV_ED,a1
 add d0,a1
 mov d2,d0
 call cv_lk,[],0
 mov 18,d1
1:
 movbu (a0),d0
 movbu d0,(a1)
 inc a0
 inc a1
 add -1,d1
 bne 1b
9:
 ret [d2,d3,a2,a3],20

/* cv_zk: `call cv_zk,[d2],8`, d0 = k: live[k] flat (e_rst; the RGB page's reset). Uses d0, d1, a0, MDR. */
cv_zk:
 call cv_lk,[],0
 clr d0
 mov 18,d1
1:
 movbu d0,(a0)
 inc a0
 add -1,d1
 bne 1b
 ret [d2],8

/* cv_sput: `call cv_sput,[d2,d3,a2,a3],20` (ss_put), d0 = a set: the set's live[4] and ed[24] <- ours; ss_chg = 1
 * when any byte differed (so the set is written). Uses d0, d1, a0, a1, MDR. */
cv_sput:
 mov CV_SSZ,d1
 mul d1,d0
 mov cv_ram + CV_SS,a0
 add d0,a0
 mov cv_ram + CV_LV,a1
 mov CV_SSZ,d1
 call ss_cc,[d2],8
 ret [d2,d3,a2,a3],20

/* cv_sget: `call cv_sget,[d2,d3,a2,a3],20` (ss_get, COLOR k's slot from the set), d0 = the set, d2 = k: live[k] <-
 * the set's. Uses d0, d1, a0, a1, MDR. */
cv_sget:
 mov CV_SSZ,d1
 mul d1,d0
 mov cv_ram + CV_SS,a1
 add d0,a1
 mov 18,d0
 mul d2,d0
 add d0,a1
 mov d2,d0
 call cv_lk,[],0
 mov 18,d1
1:
 movbu (a1),d0
 movbu d0,(a0)
 inc a0
 inc a1
 add -1,d1
 bne 1b
 ret [d2,d3,a2,a3],20

/* cv_sed: `call cv_sed,[d2,d3,a2,a3],20` (ss_ed: the set's film changes become the ones in use), d0 = the set:
 * ed[24] <- the set's. Uses d0, d1, a0, a1, MDR. */
cv_sed:
 mov CV_SSZ,d1
 mul d1,d0
 mov cv_ram + CV_SS + 72,a1
 add d0,a1
 mov cv_ram + CV_ED,a0
 mov 24 * 18,d1
 call ub_cpy,[],0
 ret [d2,d3,a2,a3],20

/* cv_load: `call cv_load,[d2,d3,a2,a3],20` (ub_pfl, the first half-press; once a power-on): the record in M when it
 * is valid and was written with the films block the camera had at power-on (ub_ok0, generation ub_gen0); else
 * every curve flat. */
cv_load:
 movbu (cv_ok),d0
 cmp 0,d0
 bne 9f
 mov 1,d0
 movbu d0,(cv_ok)
 movbu (ub_ok0),d0
 cmp 0,d0
 beq 8f
 mov CV_C,a3
 mov (a3),d0
 cmp CV_MAGIC,d0
 bne 8f
 movhu (4,a3),d0
 cmp 1,d0
 bne 8f
 movhu (6,a3),d0
 cmp CV_LEN,d0
 bne 8f
 mov (12,a3),d0
 mov (ub_gen0),d1
 cmp d1,d0
 bne 8f
 mov -1,d0
 mov a3,a0
 add 12,a0
 mov CV_LEN - 12,d1
 call sd_crc,[d2,d3],12
 not d0
 mov (8,a3),d1
 cmp d1,d0
 bne 8f
 mov cv_ram,a0
 mov a3,a1
 mov CV_LEN,d1
 call ub_cpy,[],0
 mov 1,d0
 movbu d0,(cv_v0)
 bra 9f
8:
 mov cv_ram + CV_LV,a0
 mov CV_LEN - CV_LV,d1
 call ub_zero,[],0
9:
 ret [d2,d3,a2,a3],20

/* cv_hdr: `call cv_hdr,[d2,d3,a2,a3],20`, d0 = the films block's generation it goes with: cv_ram's header and CRC
 * (before the locked copy, cv_put). */
cv_hdr:
 mov d0,(cv_ram + 12)
 mov CV_MAGIC,d0
 mov d0,(cv_ram)
 mov 1,d0
 movhu d0,(cv_ram + 4)
 mov CV_LEN,d0
 movhu d0,(cv_ram + 6)
 mov -1,d0
 mov cv_ram + 12,a0
 mov CV_LEN - 12,d1
 call sd_crc,[d2,d3],12
 not d0
 mov d0,(cv_ram + 8)
 ret [d2,d3,a2,a3],20

/* cv_put: `call cv_put,[d2],8` inside ub_wr's / ss_wr's locked write (the camera not saving M): cv_ram -> M, both
 * aliases. Uses d0, d1, a0, a1. */
cv_put:
 movbu (cv_ok),d0                 /* never before the record was read this power-on (it would be overwritten flat) */
 cmp 0,d0
 beq 9f
 mov CV_C,a0
 mov cv_ram,a1
 mov CV_LEN,d1
 call ub_cpy,[],0
 mov CV_U,a0
 mov cv_ram,a1
 mov CV_LEN,d1
 call ub_cpy,[],0
 mov (cv_nw),d0
 inc d0
 mov d0,(cv_nw)
9:
 ret [d2],8

 .balign 4
cv_h:
 .long 410, 614, 1024, 1024, 1024
cv_inv:
 .long 40920, 27324, 16384, 16384, 16384
cv_pp:
 .long 0, 0, 0
cv_nw:
 .long 0
cv_pb:
 .space 3 * 64
 .balign 4
cv_ram:
 .space CV_LEN
cv_ok:
 .byte 0
cv_v0:
 .byte 0
 .balign 4
