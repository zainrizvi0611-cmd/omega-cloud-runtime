#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <arm_neon.h>

#define unlikely(x) __builtin_expect(!!(x), 0)

static const uint32_t K[64] = {
    0x428A2F98U, 0x71374491U, 0xB5C0FBCFU, 0xE9B5DBA5U,
    0x3956C25BU, 0x59F111F1U, 0x923F82A4U, 0xAB1C5ED5U,
    0xD807AA98U, 0x12835B01U, 0x243185BEU, 0x550C7DC3U,
    0x72BE5D74U, 0x80DEB1FEU, 0x9BDC06A7U, 0xC19BF174U,
    0xE49B69C1U, 0xEFBE4786U, 0x0FC19DC6U, 0x240CA1CCU,
    0x2DE92C6FU, 0x4A7484AAU, 0x5CB0A9DCU, 0x76F988DAU,
    0x983E5152U, 0xA831C66DU, 0xB00327C8U, 0xBF597FC7U,
    0xC6E00BF3U, 0xD5A79147U, 0x06CA6351U, 0x14292967U,
    0x27B70A85U, 0x2E1B2138U, 0x4D2C6DFCU, 0x53380D13U,
    0x650A7354U, 0x766A0ABBU, 0x81C2C92EU, 0x92722C85U,
    0xA2BFE8A1U, 0xA81A664BU, 0xC24B8B70U, 0xC76C51A3U,
    0xD192E819U, 0xD6990624U, 0xF40E3585U, 0x106AA070U,
    0x19A4C116U, 0x1E376C08U, 0x2748774CU, 0x34B0BCB5U,
    0x391C0CB3U, 0x4ED8AA4AU, 0x5B9CCA4FU, 0x682E6FF3U,
    0x748F82EEU, 0x78A5636FU, 0x84C87814U, 0x8CC70208U,
    0x90BEFFFAU, 0xA4506CEBU, 0xBEF9A3F7U, 0xC67178F2U
};

static inline void sha256_block_armv8(uint32_t state[8], const uint8_t block[64]) {
    uint32x4_t abcd = vld1q_u32(state + 0);
    uint32x4_t efgh = vld1q_u32(state + 4);
    uint32x4_t abcd_save = abcd;
    uint32x4_t efgh_save = efgh;

    uint32x4_t w0 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(block + 0)));
    uint32x4_t w1 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(block + 16)));
    uint32x4_t w2 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(block + 32)));
    uint32x4_t w3 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(block + 48)));

    uint32x4_t tmp, abcd_prev;

    #define ROUND4(idx, wi, wj, wk, wl, update_w) \
        tmp = vaddq_u32(wi, vld1q_u32(K + (idx))); \
        abcd_prev = abcd; \
        abcd = vsha256hq_u32(abcd, efgh, tmp); \
        efgh = vsha256h2q_u32(efgh, abcd_prev, tmp); \
        if (update_w) { \
            wi = vsha256su0q_u32(wi, wj); \
            wi = vsha256su1q_u32(wi, wk, wl); \
        }

    ROUND4( 0, w0, w1, w2, w3, 1);
    ROUND4( 4, w1, w2, w3, w0, 1);
    ROUND4( 8, w2, w3, w0, w1, 1);
    ROUND4(12, w3, w0, w1, w2, 1);
    ROUND4(16, w0, w1, w2, w3, 1);
    ROUND4(20, w1, w2, w3, w0, 1);
    ROUND4(24, w2, w3, w0, w1, 1);
    ROUND4(28, w3, w0, w1, w2, 1);
    ROUND4(32, w0, w1, w2, w3, 1);
    ROUND4(36, w1, w2, w3, w0, 1);
    ROUND4(40, w2, w3, w0, w1, 1);
    ROUND4(44, w3, w0, w1, w2, 1);
    ROUND4(48, w0, w1, w2, w3, 0);
    ROUND4(52, w1, w2, w3, w0, 0);
    ROUND4(56, w2, w3, w0, w1, 0);
    ROUND4(60, w3, w0, w1, w2, 0);

    #undef ROUND4

    abcd = vaddq_u32(abcd, abcd_save);
    efgh = vaddq_u32(efgh, efgh_save);
    vst1q_u32(state + 0, abcd);
    vst1q_u32(state + 4, efgh);
}

static const double truediffone = 26959535291011309493156476344723991336010898738574164086137773096960.0;

static double le256todouble(const void *target) {
    const uint64_t *data64;
    double dcut64;
    data64 = (const uint64_t *)((const uint8_t*)target + 24);
    dcut64 = *data64 * 6277101735386680763835789423207666416102355444464034512896.0;
    data64 = (const uint64_t *)((const uint8_t*)target + 16);
    dcut64 += *data64 * 340282366920938463463374607431768211456.0;
    data64 = (const uint64_t *)((const uint8_t*)target + 8);
    dcut64 += *data64 * 18446744073709551616.0;
    data64 = (const uint64_t *)(target);
    dcut64 += *data64;
    return dcut64;
}

static double diff_from_target(const void *target) {
    double dcut64 = le256todouble(target);
    if (unlikely(dcut64 <= 0.0)) dcut64 = 1.0;
    return truediffone / dcut64;
}

extern "C" int nerd_scan_batch(
    const uint8_t *header80,
    uint32_t start_nonce,
    uint32_t count,
    double pool_diff,
    double *out_best_diff,
    uint32_t *out_share_nonce,
    double *out_share_diff,
    uint8_t *out_share_hash
) {
    uint32_t midstate[8] = {
        0x6A09E667U, 0xBB67AE85U, 0x3C6EF372U, 0xA54FF53AU,
        0x510E527FU, 0x9B05688CU, 0x1F83D9ABU, 0x5BE0CD19U
    };
    sha256_block_armv8(midstate, header80);

    uint8_t block2[64];
    memset(block2, 0, 64);
    memcpy(block2, header80 + 64, 16);
    block2[16] = 0x80;
    block2[62] = 0x02;
    block2[63] = 0x80; // 640 bits

    uint8_t block3[64];
    memset(block3, 0, 64);
    block3[32] = 0x80;
    block3[62] = 0x01;
    block3[63] = 0x00; // 256 bits

    double best_d = 0.0;
    int found = 0;
    uint8_t hash[32];

    for (uint32_t i = 0; i < count; i++) {
        uint32_t nonce = start_nonce + i;
        memcpy(block2 + 12, &nonce, 4);

        uint32_t h1[8];
        memcpy(h1, midstate, 32);
        sha256_block_armv8(h1, block2);

        uint32_t *b3w = (uint32_t *)block3;
        for (int k = 0; k < 8; k++) {
            b3w[k] = __builtin_bswap32(h1[k]);
        }

        uint32_t h2[8] = {
            0x6A09E667U, 0xBB67AE85U, 0x3C6EF372U, 0xA54FF53AU,
            0x510E527FU, 0x9B05688CU, 0x1F83D9ABU, 0x5BE0CD19U
        };
        sha256_block_armv8(h2, block3);

        // Top 16 bits of LE uint256 (bytes 30..31 of outw[7] = __builtin_bswap32(h2[7])) must be 0
        if (unlikely((h2[7] & 0x0000FFFFU) == 0)) {
            uint32_t *outw = (uint32_t *)hash;
            for (int k = 0; k < 8; k++) {
                outw[k] = __builtin_bswap32(h2[k]);
            }
            double d = diff_from_target(hash);
            if (d > best_d) {
                best_d = d;
            }
            if (d >= pool_diff && d > *out_share_diff) {
                *out_share_diff = d;
                *out_share_nonce = nonce;
                memcpy(out_share_hash, hash, 32);
                found = 1;
            }
        }
    }
    *out_best_diff = best_d;
    return found;
}
