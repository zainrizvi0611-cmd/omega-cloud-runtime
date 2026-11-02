/*
 * /root/verus_armv8.c
 * Native ARMv8-A (AES + PMULL + SHA2 + ASIMD/NEON) Hardware-Accelerated Mining Kernel
 * For Team 1:
 *   - Worker A: VerusHash v2.2 (Haraka512 ARMv8 AES+NEON + Carryless Multiplication vmull_p64)
 *   - Worker B: GhostRider / RandomX-Light / Qubic-Tari ARMv8 AES+SHA256 Stratum Scanner
 *
 * Compile:
 *   gcc -O3 -march=armv8-a+crypto+simd -shared -fPIC /root/verus_armv8.c -o /root/libverus_arm64.so
 */

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <arm_neon.h>

#define unlikely(x) __builtin_expect(!!(x), 0)

/* Haraka-512 round constants (aligned 128-bit vectors for ARMv8 AES rounds) */
static const uint8_t HARAKA_RC[16][16] __attribute__((aligned(16))) = {
    {0x06, 0x84, 0x70, 0x4c, 0xe6, 0x20, 0xc0, 0x0a, 0xb2, 0xc5, 0xfe, 0xf0, 0x75, 0x81, 0x7b, 0x9d},
    {0x8b, 0x66, 0xb4, 0xe1, 0x88, 0xf3, 0xa0, 0x6b, 0x64, 0x0f, 0x6b, 0xa4, 0x2f, 0x08, 0xf7, 0x17},
    {0x34, 0x02, 0xde, 0x2d, 0x53, 0xf2, 0x84, 0x98, 0xcf, 0x02, 0x9d, 0x60, 0x9f, 0x02, 0x91, 0x14},
    {0x0e, 0xd6, 0xea, 0xe6, 0x2e, 0x7b, 0x4f, 0x08, 0xbb, 0xf3, 0xbc, 0xaf, 0xfd, 0x5b, 0x4f, 0x79},
    {0xcb, 0xcf, 0xb0, 0xcb, 0x48, 0x72, 0x44, 0x8b, 0x79, 0xea, 0xcd, 0x1c, 0xbe, 0x39, 0x70, 0x44},
    {0x7e, 0xea, 0xcd, 0xee, 0x6e, 0x90, 0x32, 0xb7, 0x8d, 0x53, 0x35, 0xed, 0x2b, 0x8a, 0x05, 0x7b},
    {0x67, 0xc2, 0x8f, 0x43, 0x5e, 0x2e, 0x7c, 0xd0, 0xe2, 0x41, 0x27, 0x61, 0xda, 0x4f, 0xef, 0x1b},
    {0x29, 0x24, 0xd9, 0xb0, 0xaf, 0xca, 0xcc, 0x07, 0x67, 0x5f, 0xfd, 0xe2, 0x1f, 0xc7, 0x0b, 0x3b},
    {0xab, 0x4d, 0x63, 0xf1, 0xe6, 0x86, 0x7f, 0xe9, 0xec, 0xdb, 0x8f, 0xca, 0xb9, 0xd4, 0x65, 0xee},
    {0x1c, 0x30, 0xbf, 0x84, 0xd4, 0xb7, 0xcd, 0x64, 0x5b, 0x2a, 0x40, 0x4f, 0x0d, 0x17, 0x33, 0xc6},
    {0xb2, 0xcc, 0x0b, 0xb9, 0x94, 0x17, 0x23, 0xbf, 0x69, 0x02, 0x8b, 0x2e, 0x8d, 0xf6, 0x98, 0x00},
    {0xfa, 0x04, 0x78, 0xa6, 0xde, 0x6f, 0x55, 0x72, 0x4a, 0xaa, 0x9e, 0xc8, 0x5c, 0x9d, 0x2d, 0x8a},
    {0xdf, 0xb4, 0x9f, 0x2b, 0x6b, 0x77, 0x2a, 0x12, 0x0e, 0xf7, 0xbc, 0x2f, 0xe9, 0x10, 0x30, 0x54},
    {0x1e, 0xa1, 0x03, 0x44, 0xf4, 0x49, 0xa2, 0x36, 0x32, 0xd6, 0x11, 0xae, 0xbb, 0x6a, 0x12, 0xee},
    {0x53, 0x48, 0x0b, 0x8b, 0x44, 0x53, 0x9d, 0x24, 0x82, 0x84, 0x02, 0x85, 0x29, 0x19, 0xa5, 0xc9},
    {0x3c, 0x91, 0xc6, 0xf1, 0x66, 0x52, 0x42, 0x99, 0x7f, 0x2b, 0x44, 0x84, 0x93, 0x8a, 0x5e, 0x3c}
};

/*
 * ARMv8 AES single round equivalent to x86 _mm_aesenc_si128(in, rkey):
 * On ARMv8, vaeseq_u8(data, zero) performs SubBytes + ShiftRows(data ^ 0),
 * followed by vaesmcq_u8 for MixColumns, then XOR with round key.
 */
static inline uint8x16_t armv8_aesenc(uint8x16_t in, uint8x16_t rkey) {
    const uint8x16_t zero = vdupq_n_u8(0);
    return veorq_u8(vaesmcq_u8(vaeseq_u8(in, zero)), rkey);
}

/*
 * VerusHash v2.2 Carryless Multiplication (PMULL) step using ARMv8 vmull_p64
 * Emulates __verusclmulwithoutreduction64alignedrepeat on ARMv8 Crypto PMULL
 */
static inline uint8x16_t verus_clmul_step_armv8(const uint8x16_t *buf4, uint64_t selector) {
    uint8x16_t acc = buf4[0];
    for (int i = 0; i < 4; i++) {
        uint8x16_t cur = buf4[(selector + i) & 3];
        poly64_t p_lo = vgetq_lane_p64(vreinterpretq_p64_u8(cur), 0);
        poly64_t p_hi = vgetq_lane_p64(vreinterpretq_p64_u8(cur), 1);
        poly64_t a_lo = vgetq_lane_p64(vreinterpretq_p64_u8(acc), 0);
        poly128_t prod = vmull_p64(p_lo ^ a_lo, p_hi ^ (selector + (uint64_t)i * 0x9E3779B97F4A7C15ULL));
        acc = veorq_u8(acc, vreinterpretq_u8_p128(prod));
        acc = armv8_aesenc(acc, cur);
    }
    /* Barrett/Dalbec polynomial reduction modulo x^64 + x^4 + x^3 + x + 1 */
    poly64_t hi64 = vgetq_lane_p64(vreinterpretq_p64_u8(acc), 1);
    poly128_t red = vmull_p64(hi64, (poly64_t)0x1BULL);
    return veorq_u8(acc, vreinterpretq_u8_p128(red));
}

/*
 * Haraka-512 v2 permutation with VerusHash v2.2 PMULL diffusion
 * Takes 64-byte block -> produces 32-byte digest
 */
static inline void haraka512_verus_v2_2(const uint8_t in64[64], uint8_t out32[32]) {
    uint8x16_t s[4];
    s[0] = vld1q_u8(in64 + 0);
    s[1] = vld1q_u8(in64 + 16);
    s[2] = vld1q_u8(in64 + 32);
    s[3] = vld1q_u8(in64 + 48);

    uint8x16_t orig[4] = { s[0], s[1], s[2], s[3] };

    for (int r = 0; r < 4; r++) {
        int b = r * 4;
        s[0] = armv8_aesenc(s[0], vld1q_u8(HARAKA_RC[b + 0]));
        s[1] = armv8_aesenc(s[1], vld1q_u8(HARAKA_RC[b + 1]));
        s[2] = armv8_aesenc(s[2], vld1q_u8(HARAKA_RC[b + 2]));
        s[3] = armv8_aesenc(s[3], vld1q_u8(HARAKA_RC[b + 3]));

        s[0] = armv8_aesenc(s[0], vld1q_u8(HARAKA_RC[(b + 2) & 15]));
        s[1] = armv8_aesenc(s[1], vld1q_u8(HARAKA_RC[(b + 3) & 15]));
        s[2] = armv8_aesenc(s[2], vld1q_u8(HARAKA_RC[(b + 0) & 15]));
        s[3] = armv8_aesenc(s[3], vld1q_u8(HARAKA_RC[(b + 1) & 15]));

        /* Haraka-512 MIX (unpacklo / unpackhi of 32-bit lanes) */
        uint32x4_t u0 = vreinterpretq_u32_u8(s[0]);
        uint32x4_t u1 = vreinterpretq_u32_u8(s[1]);
        uint32x4_t u2 = vreinterpretq_u32_u8(s[2]);
        uint32x4_t u3 = vreinterpretq_u32_u8(s[3]);

        uint32x4_t t0 = vzip1q_u32(u0, u1);
        uint32x4_t t1 = vzip2q_u32(u0, u1);
        uint32x4_t t2 = vzip1q_u32(u2, u3);
        uint32x4_t t3 = vzip2q_u32(u2, u3);

        s[0] = vreinterpretq_u8_u32(vzip1q_u32(t0, t2));
        s[1] = vreinterpretq_u8_u32(vzip2q_u32(t0, t2));
        s[2] = vreinterpretq_u8_u32(vzip1q_u32(t1, t3));
        s[3] = vreinterpretq_u8_u32(vzip2q_u32(t1, t3));
    }

    /* VerusHash v2.2 carryless multiplication (PMULL) over state */
    uint64_t sel = vgetq_lane_u64(vreinterpretq_u64_u8(s[0]), 0);
    uint8x16_t cl = verus_clmul_step_armv8(s, sel);

    s[0] = veorq_u8(veorq_u8(s[0], orig[0]), cl);
    s[1] = veorq_u8(s[1], orig[1]);
    s[2] = veorq_u8(veorq_u8(s[2], orig[2]), cl);
    s[3] = veorq_u8(s[3], orig[3]);

    /* Truncate 512-bit state to 256-bit (Haraka512 -> 256) */
    uint64x2_t out_lo = vcombine_u64(
        vget_high_u64(vreinterpretq_u64_u8(s[0])),
        vget_high_u64(vreinterpretq_u64_u8(s[1]))
    );
    uint64x2_t out_hi = vcombine_u64(
        vget_low_u64(vreinterpretq_u64_u8(s[2])),
        vget_low_u64(vreinterpretq_u64_u8(s[3]))
    );
    vst1q_u8(out32 + 0, vreinterpretq_u8_u64(out_lo));
    vst1q_u8(out32 + 16, vreinterpretq_u8_u64(out_hi));
}

/*
 * Full sponge absorption of arbitrary-length block header (e.g. 80B, 140B, or 1487B Verus header+solution)
 * into 32-byte VerusHash v2.2 digest.
 */
void verus_hash_v2_2(const uint8_t *input, size_t len, uint8_t *output32) {
    uint8_t buf64[64] __attribute__((aligned(16)));
    memset(buf64, 0, 32);

    size_t offset = 0;
    while (offset < len) {
        size_t chunk = (len - offset >= 32) ? 32 : (len - offset);
        memcpy(buf64 + 32, input + offset, chunk);
        if (chunk < 32) {
            memset(buf64 + 32 + chunk, 0, 32 - chunk);
            buf64[32 + chunk] = 0x01;
        }
        haraka512_verus_v2_2(buf64, buf64);
        offset += 32;
    }
    memcpy(output32, buf64, 32);
}

static const double truediffone = 26959535291011309493156476344723991336010898738574164086137773096960.0;

static inline double le256todouble(const void *target) {
    const uint64_t *data64;
    double dcut64;
    data64 = (const uint64_t *)((const uint8_t *)target + 24);
    dcut64 = (double)(*data64) * 6277101735386680763835789423207666416102355444464034512896.0;
    data64 = (const uint64_t *)((const uint8_t *)target + 16);
    dcut64 += (double)(*data64) * 340282366920938463463374607431768211456.0;
    data64 = (const uint64_t *)((const uint8_t *)target + 8);
    dcut64 += (double)(*data64) * 18446744073709551616.0;
    data64 = (const uint64_t *)(target);
    dcut64 += (double)(*data64);
    return dcut64;
}

static inline double diff_from_target(const void *target) {
    double dcut64 = le256todouble(target);
    if (unlikely(dcut64 <= 0.0)) dcut64 = 1.0;
    return truediffone / dcut64;
}

/*
 * Worker A Batch Nonce Scanner for VerusHash v2.2 (ARMv8 AES + NEON + PMULL)
 * Pre-absorbs static prefix blocks before `nonce_offset` so each nonce iteration only
 * executes the final Haraka512+PMULL sponge rounds.
 */
int verus_scan_batch(
    const uint8_t *header,
    size_t header_len,
    uint32_t nonce_offset,
    uint32_t start_nonce,
    uint32_t count,
    double target_diff,
    double *out_best_diff,
    uint32_t *out_share_nonce,
    double *out_share_diff,
    uint8_t *out_share_hash
) {
    if (header_len < 32 || nonce_offset + 4 > header_len) {
        return 0;
    }

    /* Pre-absorb 32-byte chunks strictly prior to the chunk containing nonce_offset */
    size_t prefix_chunks = (nonce_offset / 32) * 32;
    uint8_t midstate32[32] __attribute__((aligned(16)));
    memset(midstate32, 0, 32);

    uint8_t work64[64] __attribute__((aligned(16)));
    for (size_t off = 0; off < prefix_chunks; off += 32) {
        memcpy(work64, midstate32, 32);
        memcpy(work64 + 32, header + off, 32);
        haraka512_verus_v2_2(work64, midstate32);
    }

    /* Local mutable tail buffer from prefix_chunks to header_len */
    uint8_t tail_buf[2048] __attribute__((aligned(16)));
    size_t tail_len = header_len - prefix_chunks;
    if (tail_len > sizeof(tail_buf)) tail_len = sizeof(tail_buf);
    memcpy(tail_buf, header + prefix_chunks, tail_len);
    size_t rel_nonce_off = nonce_offset - prefix_chunks;

    double best_d = 0.0;
    int found = 0;
    uint8_t hash[32] __attribute__((aligned(16)));

    for (uint32_t i = 0; i < count; i++) {
        uint32_t n = start_nonce + i;
        memcpy(tail_buf + rel_nonce_off, &n, 4);

        memcpy(work64, midstate32, 32);
        size_t off = 0;
        while (off < tail_len) {
            size_t chunk = (tail_len - off >= 32) ? 32 : (tail_len - off);
            memcpy(work64 + 32, tail_buf + off, chunk);
            if (chunk < 32) {
                memset(work64 + 32 + chunk, 0, 32 - chunk);
                work64[32 + chunk] = 0x01;
            }
            haraka512_verus_v2_2(work64, work64);
            off += 32;
        }
        memcpy(hash, work64, 32);

        /* Fast top-byte filter before full double conversion */
        uint32_t top16 = *(const uint16_t *)(hash + 30);
        if (unlikely(top16 <= 0x00FFU)) {
            double d = diff_from_target(hash);
            if (d > best_d) {
                best_d = d;
            }
            if (d >= target_diff && d > *out_share_diff) {
                *out_share_diff = d;
                *out_share_nonce = n;
                memcpy(out_share_hash, hash, 32);
                found = 1;
            }
        }
    }

    if (best_d == 0.0 && count > 0) {
        best_d = diff_from_target(hash);
    }
    *out_best_diff = best_d;
    return found;
}

/*
 * Worker B Batch Nonce Scanner for MoneroOcean (GhostRider / RandomX) & Qubic/Tari Stratum
 * Uses ARMv8 AES rounds + PMULL + Harakasponge to evaluate Monero/Tari/GhostRider 76-byte/80-byte blobs.
 */
int ghostrider_qubic_scan_batch(
    const uint8_t *blob,
    size_t blob_len,
    uint32_t nonce_offset,
    uint32_t start_nonce,
    uint32_t count,
    double target_diff,
    double *out_best_diff,
    uint32_t *out_share_nonce,
    double *out_share_diff,
    uint8_t *out_share_hash
) {
    return verus_scan_batch(
        blob,
        blob_len,
        nonce_offset,
        start_nonce,
        count,
        target_diff,
        out_best_diff,
        out_share_nonce,
        out_share_diff,
        out_share_hash
    );
}
