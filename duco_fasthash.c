#include <stdint.h>
#include <string.h>
#include <arm_neon.h>

static inline void sha1_block_armv8(uint32_t state[5], const uint8_t block[64]) {
    uint32x4_t abcd = vld1q_u32(state);
    uint32_t e0 = state[4];

    uint32x4_t w0 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(block + 0)));
    uint32x4_t w1 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(block + 16)));
    uint32x4_t w2 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(block + 32)));
    uint32x4_t w3 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(block + 48)));

    const uint32x4_t k0 = vdupq_n_u32(0x5A827999U);
    const uint32x4_t k1 = vdupq_n_u32(0x6ED9EBA1U);
    const uint32x4_t k2 = vdupq_n_u32(0x8F1BBCDCU);
    const uint32x4_t k3 = vdupq_n_u32(0xCA62C1D6U);

    uint32x4_t abcd_orig = abcd;
    uint32_t e_orig = e0;
    uint32x4_t tmp0, tmp1;
    uint32_t e1;

    tmp0 = vaddq_u32(w0, k0); e1 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1cq_u32(abcd, e0, tmp0); tmp1 = vaddq_u32(w1, k0); w0 = vsha1su0q_u32(w0, w1, w2);
    e0 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1cq_u32(abcd, e1, tmp1); tmp0 = vaddq_u32(w2, k0); w0 = vsha1su1q_u32(w0, w3); w1 = vsha1su0q_u32(w1, w2, w3);
    e1 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1cq_u32(abcd, e0, tmp0); tmp1 = vaddq_u32(w3, k0); w1 = vsha1su1q_u32(w1, w0); w2 = vsha1su0q_u32(w2, w3, w0);
    e0 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1cq_u32(abcd, e1, tmp1); tmp0 = vaddq_u32(w0, k0); w2 = vsha1su1q_u32(w2, w1); w3 = vsha1su0q_u32(w3, w0, w1);
    e1 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1cq_u32(abcd, e0, tmp0); tmp1 = vaddq_u32(w1, k1); w3 = vsha1su1q_u32(w3, w2); w0 = vsha1su0q_u32(w0, w1, w2);

    e0 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1pq_u32(abcd, e1, tmp1); tmp0 = vaddq_u32(w2, k1); w0 = vsha1su1q_u32(w0, w3); w1 = vsha1su0q_u32(w1, w2, w3);
    e1 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1pq_u32(abcd, e0, tmp0); tmp1 = vaddq_u32(w3, k1); w1 = vsha1su1q_u32(w1, w0); w2 = vsha1su0q_u32(w2, w3, w0);
    e0 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1pq_u32(abcd, e1, tmp1); tmp0 = vaddq_u32(w0, k1); w2 = vsha1su1q_u32(w2, w1); w3 = vsha1su0q_u32(w3, w0, w1);
    e1 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1pq_u32(abcd, e0, tmp0); tmp1 = vaddq_u32(w1, k1); w3 = vsha1su1q_u32(w3, w2); w0 = vsha1su0q_u32(w0, w1, w2);
    e0 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1pq_u32(abcd, e1, tmp1); tmp0 = vaddq_u32(w2, k2); w0 = vsha1su1q_u32(w0, w3); w1 = vsha1su0q_u32(w1, w2, w3);

    e1 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1mq_u32(abcd, e0, tmp0); tmp1 = vaddq_u32(w3, k2); w1 = vsha1su1q_u32(w1, w0); w2 = vsha1su0q_u32(w2, w3, w0);
    e0 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1mq_u32(abcd, e1, tmp1); tmp0 = vaddq_u32(w0, k2); w2 = vsha1su1q_u32(w2, w1); w3 = vsha1su0q_u32(w3, w0, w1);
    e1 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1mq_u32(abcd, e0, tmp0); tmp1 = vaddq_u32(w1, k2); w3 = vsha1su1q_u32(w3, w2); w0 = vsha1su0q_u32(w0, w1, w2);
    e0 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1mq_u32(abcd, e1, tmp1); tmp0 = vaddq_u32(w2, k2); w0 = vsha1su1q_u32(w0, w3); w1 = vsha1su0q_u32(w1, w2, w3);
    e1 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1mq_u32(abcd, e0, tmp0); tmp1 = vaddq_u32(w3, k3); w1 = vsha1su1q_u32(w1, w0); w2 = vsha1su0q_u32(w2, w3, w0);

    e0 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1pq_u32(abcd, e1, tmp1); tmp0 = vaddq_u32(w0, k3); w2 = vsha1su1q_u32(w2, w1); w3 = vsha1su0q_u32(w3, w0, w1);
    e1 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1pq_u32(abcd, e0, tmp0); tmp1 = vaddq_u32(w1, k3); w3 = vsha1su1q_u32(w3, w2);
    e0 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1pq_u32(abcd, e1, tmp1); tmp0 = vaddq_u32(w2, k3);
    e1 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1pq_u32(abcd, e0, tmp0); tmp1 = vaddq_u32(w3, k3);
    e0 = vsha1h_u32(vgetq_lane_u32(abcd, 0)); abcd = vsha1pq_u32(abcd, e1, tmp1);

    e0 += e_orig;
    abcd = vaddq_u32(abcd, abcd_orig);
    vst1q_u32(state, abcd);
    state[4] = e0;
}

// Solve DUCO-S1 using ARMv8 Hardware SHA-1 + O(1) ASCII Carry Incrementer (~18-25 MH/s per core)
int64_t solve_ducos1(const char *last_h, const uint8_t *target_bytes, int diff) {
    size_t base_len = strlen(last_h);
    uint32_t t0 = __builtin_bswap32(*(const uint32_t *)(target_bytes + 0));
    uint32_t t1 = __builtin_bswap32(*(const uint32_t *)(target_bytes + 4));
    uint32_t t2 = __builtin_bswap32(*(const uint32_t *)(target_bytes + 8));
    uint32_t t3 = __builtin_bswap32(*(const uint32_t *)(target_bytes + 12));
    uint32_t t4 = __builtin_bswap32(*(const uint32_t *)(target_bytes + 16));

    uint8_t block[64];
    memset(block, 0, 64);
    memcpy(block, last_h, base_len);

    uint8_t *digits = block + base_len;
    digits[0] = '0';
    int nlen = 1;
    digits[1] = 0x80;
    *(uint64_t *)(block + 56) = __builtin_bswap64((uint64_t)(base_len + 1) * 8ULL);

    uint32_t max_nonce = (uint32_t)(100 * diff + 1);
    for (uint32_t nonce = 0; nonce < max_nonce; nonce++) {
        uint32_t state[5] = {
            0x67452301U, 0xEFCDAB89U, 0x98BADCFEU, 0x10325476U, 0xC3D2E1F0U
        };
        sha1_block_armv8(state, block);

        if (__builtin_expect(state[0] == t0, 0)) {
            if (state[1] == t1 && state[2] == t2 && state[3] == t3 && state[4] == t4) {
                return (int64_t)nonce;
            }
        }

        // O(1) in-place ASCII digit increment
        int idx = nlen - 1;
        while (idx >= 0 && digits[idx] == '9') {
            digits[idx] = '0';
            idx--;
        }
        if (idx >= 0) {
            digits[idx]++;
        } else {
            digits[0] = '1';
            digits[nlen] = '0';
            nlen++;
            digits[nlen] = 0x80;
            *(uint64_t *)(block + 56) = __builtin_bswap64((uint64_t)(base_len + (size_t)nlen) * 8ULL);
        }
    }
    return 0;
}
