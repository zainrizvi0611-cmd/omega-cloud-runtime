#include <cstdint>
#include <cstring>
#include <cstdio>
#include <arm_neon.h>
#include <gmp.h>

// ============================================================================
// 1. 256-bit Field Arithmetic modulo secp256k1 prime p = 2^256 - 2^32 - 977
// ============================================================================

struct fe256 {
    uint64_t d[4]; // little-endian limbs: d[0] is LSB, d[3] is MSB
};

static constexpr uint64_t SECP_P0 = 0xFFFFFFFEFFFFFC2FULL;
static constexpr uint64_t SECP_P1 = 0xFFFFFFFFFFFFFFFFULL;
static constexpr uint64_t SECP_P2 = 0xFFFFFFFFFFFFFFFFULL;
static constexpr uint64_t SECP_P3 = 0xFFFFFFFFFFFFFFFFULL;
static constexpr uint64_t SECP_C  = 0x1000003D1ULL; // 2^256 - p

static inline bool fe_geq_p(const fe256& a) {
    if (a.d[3] != SECP_P3) return false;
    if (a.d[2] != SECP_P2) return false;
    if (a.d[1] != SECP_P1) return false;
    return a.d[0] >= SECP_P0;
}

static inline bool fe_is_zero(const fe256& a) {
    return (a.d[0] | a.d[1] | a.d[2] | a.d[3]) == 0;
}

static inline bool fe_equal(const fe256& a, const fe256& b) {
    return ((a.d[0] ^ b.d[0]) | (a.d[1] ^ b.d[1]) | (a.d[2] ^ b.d[2]) | (a.d[3] ^ b.d[3])) == 0;
}

static inline void fe_add(fe256& r, const fe256& a, const fe256& b) {
    __uint128_t acc = (__uint128_t)a.d[0] + b.d[0];
    r.d[0] = (uint64_t)acc;
    acc = (acc >> 64) + a.d[1] + b.d[1];
    r.d[1] = (uint64_t)acc;
    acc = (acc >> 64) + a.d[2] + b.d[2];
    r.d[2] = (uint64_t)acc;
    acc = (acc >> 64) + a.d[3] + b.d[3];
    r.d[3] = (uint64_t)acc;
    uint64_t carry = (uint64_t)(acc >> 64);

    if (carry || fe_geq_p(r)) {
        __uint128_t c = (__uint128_t)r.d[0] + SECP_C;
        r.d[0] = (uint64_t)c;
        c = (c >> 64) + r.d[1];
        r.d[1] = (uint64_t)c;
        c = (c >> 64) + r.d[2];
        r.d[2] = (uint64_t)c;
        c = (c >> 64) + r.d[3];
        r.d[3] = (uint64_t)c;
    }
}

static inline void fe_sub(fe256& r, const fe256& a, const fe256& b) {
    __uint128_t borrow = 0;
    __uint128_t diff;

    diff = (__uint128_t)a.d[0] - b.d[0];
    r.d[0] = (uint64_t)diff;
    borrow = (diff >> 127) & 1;

    diff = (__uint128_t)a.d[1] - b.d[1] - borrow;
    r.d[1] = (uint64_t)diff;
    borrow = (diff >> 127) & 1;

    diff = (__uint128_t)a.d[2] - b.d[2] - borrow;
    r.d[2] = (uint64_t)diff;
    borrow = (diff >> 127) & 1;

    diff = (__uint128_t)a.d[3] - b.d[3] - borrow;
    r.d[3] = (uint64_t)diff;
    borrow = (diff >> 127) & 1;

    if (borrow) {
        // Underflow mod 2^256: subtract SECP_C (since 2^256 == SECP_C mod p)
        diff = (__uint128_t)r.d[0] - SECP_C;
        r.d[0] = (uint64_t)diff;
        borrow = (diff >> 127) & 1;

        diff = (__uint128_t)r.d[1] - borrow;
        r.d[1] = (uint64_t)diff;
        borrow = (diff >> 127) & 1;

        diff = (__uint128_t)r.d[2] - borrow;
        r.d[2] = (uint64_t)diff;
        borrow = (diff >> 127) & 1;

        r.d[3] -= (uint64_t)borrow;
    }
}

static inline void fe_mul(fe256& r, const fe256& a, const fe256& b) {
    uint64_t t[8] = {0};

    for (int i = 0; i < 4; ++i) {
        __uint128_t carry = 0;
        uint64_t ai = a.d[i];
        for (int j = 0; j < 4; ++j) {
            __uint128_t prod = (__uint128_t)ai * b.d[j] + t[i + j] + carry;
            t[i + j] = (uint64_t)prod;
            carry = prod >> 64;
        }
        t[i + 4] = (uint64_t)carry;
    }

    // Reduce t[4..7] using 2^256 == SECP_C (0x1000003D1) mod p
    __uint128_t acc = (__uint128_t)t[0] + (__uint128_t)t[4] * SECP_C;
    uint64_t r0 = (uint64_t)acc;
    acc = (acc >> 64) + t[1] + (__uint128_t)t[5] * SECP_C;
    uint64_t r1 = (uint64_t)acc;
    acc = (acc >> 64) + t[2] + (__uint128_t)t[6] * SECP_C;
    uint64_t r2 = (uint64_t)acc;
    acc = (acc >> 64) + t[3] + (__uint128_t)t[7] * SECP_C;
    uint64_t r3 = (uint64_t)acc;
    uint64_t h2 = (uint64_t)(acc >> 64);

    // Fold h2 * SECP_C
    acc = (__uint128_t)r0 + (__uint128_t)h2 * SECP_C;
    r.d[0] = (uint64_t)acc;
    acc = (acc >> 64) + r1;
    r.d[1] = (uint64_t)acc;
    acc = (acc >> 64) + r2;
    r.d[2] = (uint64_t)acc;
    acc = (acc >> 64) + r3;
    r.d[3] = (uint64_t)acc;
    uint64_t carry = (uint64_t)(acc >> 64);

    if (carry || fe_geq_p(r)) {
        __uint128_t c = (__uint128_t)r.d[0] + SECP_C;
        r.d[0] = (uint64_t)c;
        c = (c >> 64) + r.d[1];
        r.d[1] = (uint64_t)c;
        c = (c >> 64) + r.d[2];
        r.d[2] = (uint64_t)c;
        c = (c >> 64) + r.d[3];
        r.d[3] = (uint64_t)c;
    }
}

static inline void fe_sqr(fe256& r, const fe256& a) {
    fe_mul(r, a, a);
}

static inline void fe_to_bytes_be(uint8_t out[32], const fe256& a) {
    for (int i = 0; i < 4; ++i) {
        uint64_t limb = __builtin_bswap64(a.d[3 - i]);
        std::memcpy(out + i * 8, &limb, 8);
    }
}

// ============================================================================
// 2. GMP-backed Modular Inversion & Initial Scalar Multiplication
// ============================================================================

struct GmpContext {
    mpz_t p;
    mpz_t val;
    mpz_t inv;
    GmpContext() {
        mpz_init(p);
        mpz_init(val);
        mpz_init(inv);
        const uint64_t p_limbs[4] = {SECP_P0, SECP_P1, SECP_P2, SECP_P3};
        mpz_import(p, 4, -1, sizeof(uint64_t), 0, 0, p_limbs);
    }
    ~GmpContext() {
        mpz_clear(p);
        mpz_clear(val);
        mpz_clear(inv);
    }
    inline void invert(fe256& r, const fe256& a) {
        mpz_import(val, 4, -1, sizeof(uint64_t), 0, 0, a.d);
        mpz_invert(inv, val, p);
        r.d[0] = r.d[1] = r.d[2] = r.d[3] = 0;
        size_t count = 0;
        mpz_export(r.d, &count, -1, sizeof(uint64_t), 0, 0, inv);
    }
};

struct AffinePoint {
    fe256 x;
    fe256 y;
    bool infinity;
};

static const fe256 SECP_GX = {{
    0x59F2815B16F81798ULL,
    0x029BFCDB2DCE28D9ULL,
    0x55A06295CE870B07ULL,
    0x79BE667EF9DCBBACULL
}};

static const fe256 SECP_GY = {{
    0x9C47D08FFB10D4B8ULL,
    0xFD17B448A6855419ULL,
    0x5DA4FBFC0E1108A8ULL,
    0x483ADA7726A3C465ULL
}};

static void point_double(AffinePoint& R, const AffinePoint& P, GmpContext& gmp) {
    if (P.infinity || fe_is_zero(P.y)) {
        R.infinity = true;
        return;
    }
    fe256 x2, num, den, den_inv, lam, lam2, nx, ny, dx;
    fe_sqr(x2, P.x);
    fe_add(num, x2, x2);
    fe_add(num, num, x2); // 3 * x^2
    fe_add(den, P.y, P.y); // 2 * y
    gmp.invert(den_inv, den);
    fe_mul(lam, num, den_inv);
    fe_sqr(lam2, lam);
    fe_sub(nx, lam2, P.x);
    fe_sub(nx, nx, P.x);
    fe_sub(dx, P.x, nx);
    fe_mul(ny, lam, dx);
    fe_sub(ny, ny, P.y);
    R.x = nx;
    R.y = ny;
    R.infinity = false;
}

static void point_add_slow(AffinePoint& R, const AffinePoint& P, const AffinePoint& Q, GmpContext& gmp) {
    if (P.infinity) { R = Q; return; }
    if (Q.infinity) { R = P; return; }
    if (fe_equal(P.x, Q.x)) {
        if (fe_equal(P.y, Q.y)) {
            point_double(R, P, gmp);
        } else {
            R.infinity = true;
        }
        return;
    }
    fe256 dy, dx, dx_inv, lam, lam2, nx, ny, diffx;
    fe_sub(dy, Q.y, P.y);
    fe_sub(dx, Q.x, P.x);
    gmp.invert(dx_inv, dx);
    fe_mul(lam, dy, dx_inv);
    fe_sqr(lam2, lam);
    fe_sub(nx, lam2, P.x);
    fe_sub(nx, nx, Q.x);
    fe_sub(diffx, P.x, nx);
    fe_mul(ny, lam, diffx);
    fe_sub(ny, ny, P.y);
    R.x = nx;
    R.y = ny;
    R.infinity = false;
}

static void scalar_mul_128(AffinePoint& R, __uint128_t k, GmpContext& gmp) {
    R.infinity = true;
    AffinePoint Q = {SECP_GX, SECP_GY, false};
    while (k > 0) {
        if (k & 1) {
            AffinePoint tmp;
            point_add_slow(tmp, R, Q, gmp);
            R = tmp;
        }
        AffinePoint nextQ;
        point_double(nextQ, Q, gmp);
        Q = nextQ;
        k >>= 1;
    }
}

// Precomputed table Q_table[j] = (j + 1) * G for j = 0..127 (128 points per Montgomery batch)
static constexpr int BATCH_SIZE = 128;
static AffinePoint g_Q_table[BATCH_SIZE];
static bool g_table_initialized = false;

static void ensure_table_initialized(GmpContext& gmp) {
    if (g_table_initialized) return;
    AffinePoint G = {SECP_GX, SECP_GY, false};
    g_Q_table[0] = G;
    for (int j = 1; j < BATCH_SIZE; ++j) {
        point_add_slow(g_Q_table[j], g_Q_table[j - 1], G, gmp);
    }
    g_table_initialized = true;
}

// ============================================================================
// 3. ARMv8 Hardware SHA-256 (vsha256hq_u32) for 33-byte Compressed Pubkey
// ============================================================================

alignas(16) static const uint32_t SHA256_K[64] = {
    0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U,
    0x3956c25bU, 0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U,
    0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
    0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U,
    0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU,
    0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
    0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U,
    0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U,
    0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
    0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
    0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U,
    0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
    0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U,
    0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
    0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
    0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U
};

static inline void sha256_33bytes_armv8(const uint8_t pubkey33[33], uint8_t sha_out[32]) {
    alignas(16) uint8_t block[64] = {0};
    std::memcpy(block, pubkey33, 33);
    block[33] = 0x80;
    block[62] = 0x01; // 33 * 8 = 264 bits = 0x0108
    block[63] = 0x08;

    static const uint32_t H_INIT[8] = {
        0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
        0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U
    };

    uint32x4_t state0 = vld1q_u32(&H_INIT[0]);
    uint32x4_t state1 = vld1q_u32(&H_INIT[4]);
    uint32x4_t abcd = state0;
    uint32x4_t efgh = state1;

    uint32x4_t msg0 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(block + 0)));
    uint32x4_t msg1 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(block + 16)));
    uint32x4_t msg2 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(block + 32)));
    uint32x4_t msg3 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(block + 48)));

    uint32x4_t tmp, wk;

    // Rounds 0..15
    wk = vaddq_u32(msg0, vld1q_u32(&SHA256_K[0]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);
    msg0 = vsha256su1q_u32(vsha256su0q_u32(msg0, msg1), msg2, msg3);

    wk = vaddq_u32(msg1, vld1q_u32(&SHA256_K[4]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);
    msg1 = vsha256su1q_u32(vsha256su0q_u32(msg1, msg2), msg3, msg0);

    wk = vaddq_u32(msg2, vld1q_u32(&SHA256_K[8]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);
    msg2 = vsha256su1q_u32(vsha256su0q_u32(msg2, msg3), msg0, msg1);

    wk = vaddq_u32(msg3, vld1q_u32(&SHA256_K[12]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);
    msg3 = vsha256su1q_u32(vsha256su0q_u32(msg3, msg0), msg1, msg2);

    // Rounds 16..31
    wk = vaddq_u32(msg0, vld1q_u32(&SHA256_K[16]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);
    msg0 = vsha256su1q_u32(vsha256su0q_u32(msg0, msg1), msg2, msg3);

    wk = vaddq_u32(msg1, vld1q_u32(&SHA256_K[20]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);
    msg1 = vsha256su1q_u32(vsha256su0q_u32(msg1, msg2), msg3, msg0);

    wk = vaddq_u32(msg2, vld1q_u32(&SHA256_K[24]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);
    msg2 = vsha256su1q_u32(vsha256su0q_u32(msg2, msg3), msg0, msg1);

    wk = vaddq_u32(msg3, vld1q_u32(&SHA256_K[28]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);
    msg3 = vsha256su1q_u32(vsha256su0q_u32(msg3, msg0), msg1, msg2);

    // Rounds 32..47
    wk = vaddq_u32(msg0, vld1q_u32(&SHA256_K[32]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);
    msg0 = vsha256su1q_u32(vsha256su0q_u32(msg0, msg1), msg2, msg3);

    wk = vaddq_u32(msg1, vld1q_u32(&SHA256_K[36]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);
    msg1 = vsha256su1q_u32(vsha256su0q_u32(msg1, msg2), msg3, msg0);

    wk = vaddq_u32(msg2, vld1q_u32(&SHA256_K[40]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);
    msg2 = vsha256su1q_u32(vsha256su0q_u32(msg2, msg3), msg0, msg1);

    wk = vaddq_u32(msg3, vld1q_u32(&SHA256_K[44]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);
    msg3 = vsha256su1q_u32(vsha256su0q_u32(msg3, msg0), msg1, msg2);

    // Rounds 48..63
    wk = vaddq_u32(msg0, vld1q_u32(&SHA256_K[48]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);

    wk = vaddq_u32(msg1, vld1q_u32(&SHA256_K[52]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);

    wk = vaddq_u32(msg2, vld1q_u32(&SHA256_K[56]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);

    wk = vaddq_u32(msg3, vld1q_u32(&SHA256_K[60]));
    tmp = abcd; abcd = vsha256hq_u32(abcd, efgh, wk); efgh = vsha256h2q_u32(efgh, tmp, wk);

    abcd = vaddq_u32(abcd, state0);
    efgh = vaddq_u32(efgh, state1);

    vst1q_u8(sha_out + 0, vrev32q_u8(vreinterpretq_u8_u32(abcd)));
    vst1q_u8(sha_out + 16, vrev32q_u8(vreinterpretq_u8_u32(efgh)));
}

// ============================================================================
// 4. Fast RIPEMD-160 on 32-byte SHA-256 Digest -> 20-byte hash160
// ============================================================================

#define ROL32(x, n) (((x) << (n)) | ((x) >> (32 - (n))))
#define RMD_F1(x, y, z) ((x) ^ (y) ^ (z))
#define RMD_F2(x, y, z) (((x) & (y)) | (~(x) & (z)))
#define RMD_F3(x, y, z) (((x) | ~(y)) ^ (z))
#define RMD_F4(x, y, z) (((x) & (z)) | ((y) & ~(z)))
#define RMD_F5(x, y, z) ((x) ^ ((y) | ~(z)))

static inline void ripemd160_32bytes(const uint8_t sha_in[32], uint32_t h_out[5]) {
    uint32_t X[16] = {0};
    std::memcpy(X, sha_in, 32); // little-endian on ARM64
    X[8]  = 0x00000080U;
    X[14] = 256U; // 32 * 8 bits

    uint32_t al = 0x67452301U, bl = 0xEFCDAB89U, cl = 0x98BADCFEU, dl = 0x10325476U, el = 0xC3D2E1F0U;
    uint32_t ar = 0x67452301U, br = 0xEFCDAB89U, cr = 0x98BADCFEU, dr = 0x10325476U, er = 0xC3D2E1F0U;

    static const uint8_t rl[80] = {
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
        7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8,
        3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12,
        1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2,
        4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13
    };
    static const uint8_t rr[80] = {
        5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12,
        6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2,
        15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13,
        8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14,
        12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11
    };
    static const uint8_t sl[80] = {
        11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8,
        7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12,
        11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5,
        11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12,
        9, 15, 5, 11, 6, 8, 13, 12, 5, 12, 13, 14, 11, 8, 5, 6
    };
    static const uint8_t sr[80] = {
        8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6,
        9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11,
        9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5,
        15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8,
        8, 5, 12, 9, 12, 5, 14, 6, 8, 13, 6, 5, 15, 13, 11, 11
    };

    for (int j = 0; j < 80; ++j) {
        uint32_t tl, tr;
        if (j < 16) {
            tl = al + RMD_F1(bl, cl, dl) + X[rl[j]] + 0x00000000U;
            tr = ar + RMD_F5(br, cr, dr) + X[rr[j]] + 0x50A28BE6U;
        } else if (j < 32) {
            tl = al + RMD_F2(bl, cl, dl) + X[rl[j]] + 0x5A827999U;
            tr = ar + RMD_F4(br, cr, dr) + X[rr[j]] + 0x5C4DD124U;
        } else if (j < 48) {
            tl = al + RMD_F3(bl, cl, dl) + X[rl[j]] + 0x6ED9EBA1U;
            tr = ar + RMD_F3(br, cr, dr) + X[rr[j]] + 0x6D703EF3U;
        } else if (j < 64) {
            tl = al + RMD_F4(bl, cl, dl) + X[rl[j]] + 0x8F1BBCDCU;
            tr = ar + RMD_F2(br, cr, dr) + X[rr[j]] + 0x7A6D76E9U;
        } else {
            tl = al + RMD_F5(bl, cl, dl) + X[rl[j]] + 0xA953FD4EU;
            tr = ar + RMD_F1(br, cr, dr) + X[rr[j]] + 0x00000000U;
        }
        tl = ROL32(tl, sl[j]) + el;
        al = el; el = dl; dl = ROL32(cl, 10); cl = bl; bl = tl;

        tr = ROL32(tr, sr[j]) + er;
        ar = er; er = dr; dr = ROL32(cr, 10); cr = br; br = tr;
    }

    uint32_t t  = 0xEFCDAB89U + cl + dr;
    h_out[1]    = 0x98BADCFEU + dl + er;
    h_out[2]    = 0x10325476U + el + ar;
    h_out[3]    = 0xC3D2E1F0U + al + br;
    h_out[4]    = 0x67452301U + bl + cr;
    h_out[0]    = t;
}

// ============================================================================
// 5. Target Bitcoin Puzzle Hash160 Table (#66 test vector + #67, #68, #69, #71)
// ============================================================================

struct PuzzleTarget {
    int puzzle_id;
    uint32_t h0; // little-endian first 4 bytes for ultra-fast pre-filter
    uint8_t hash160[20];
};

static const PuzzleTarget TARGETS[] = {
    // Puzzle #66 (Solved test vector: 13zb1hQbWVsc2S7ZTZnP2G4undNNpdh5so)
    // hash160: 20d45a6a762535700ce9e0b216e31994335db8a5
    {66, 0x6a5ad420U, {0x20,0xd4,0x5a,0x6a,0x76,0x25,0x35,0x70,0x0c,0xe9,0xe0,0xb2,0x16,0xe3,0x19,0x94,0x33,0x5d,0xb8,0xa5}},
    // Puzzle #67 (6.7 BTC: 1BY8GQbnueYofwSuFAT3USAhGjPrkxDdW9)
    // hash160: 739437bb3dd6d1983e66629c5f08c70e52769371
    {67, 0xbb379473U, {0x73,0x94,0x37,0xbb,0x3d,0xd6,0xd1,0x98,0x3e,0x66,0x62,0x9c,0x5f,0x08,0xc7,0x0e,0x52,0x76,0x93,0x71}},
    // Puzzle #68 (6.8 BTC: 1MVDYgVaSN6iKKEsbzRUAYFrYJadLYZvvZ)
    // hash160: e0b8a2baee1b77fc703455f39d51477451fc8cfc
    {68, 0xbaa2b8e0U, {0xe0,0xb8,0xa2,0xba,0xee,0x1b,0x77,0xfc,0x70,0x34,0x55,0xf3,0x9d,0x51,0x47,0x74,0x51,0xfc,0x8c,0xfc}},
    // Puzzle #69 (6.9 BTC: 19vkiEajfhuZ8bs8Zu2jgmC6oqZbWqhxhG)
    // hash160: 61eb8a50c86b0584bb727dd65bed8d2400d6d5aa
    {69, 0x508aeb61U, {0x61,0xeb,0x8a,0x50,0xc8,0x6b,0x05,0x84,0xbb,0x72,0x7d,0xd6,0x5b,0xed,0x8d,0x24,0x00,0xd6,0xd5,0xaa}},
    // Puzzle #71 (7.1 BTC: 1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU)
    // hash160: f6f5431d25bbf7b12e8add9af5e3475c44a0a5b8
    {71, 0x1d43f5f6U, {0xf6,0xf5,0x43,0x1d,0x25,0xbb,0xf7,0xb1,0x2e,0x8a,0xdd,0x9a,0xf5,0xe3,0x47,0x5c,0x44,0xa0,0xa5,0xb8}}
};

static inline int match_targets(const uint32_t h[5]) {
    uint32_t h0 = h[0];
    for (int i = 0; i < 5; ++i) {
        if (h0 == TARGETS[i].h0) {
            if (std::memcmp(h, TARGETS[i].hash160, 20) == 0) {
                return TARGETS[i].puzzle_id;
            }
        }
    }
    return 0;
}

// ============================================================================
// 6. Montgomery Batch Inversion Scanner (128 points per 1 modular inversion)
// ============================================================================

extern "C" {

int puzzle_scan_range(
    uint64_t start_hi,
    uint64_t start_lo,
    uint64_t num_keys,
    int* found_puzzle_id,
    uint64_t* found_priv_hi,
    uint64_t* found_priv_lo,
    uint8_t* found_pubkey33,
    uint8_t* found_hash160
) {
    GmpContext gmp;
    ensure_table_initialized(gmp);

    __uint128_t base_k = ((__uint128_t)start_hi << 64) | start_lo;
    if (base_k == 0) base_k = 1;

    // P_base = (base_k - 1) * G so that P_base + Q_table[j] == (base_k + j) * G for j = 0..127
    AffinePoint P_base;
    scalar_mul_128(P_base, base_k - 1, gmp);

    fe256 dx[BATCH_SIZE];
    fe256 c[BATCH_SIZE];
    fe256 dx_inv[BATCH_SIZE];

    uint64_t checked = 0;
    while (checked < num_keys) {
        // 1. Compute dx[j] = Q_table[j].x - P_base.x and prefix products c[j]
        for (int j = 0; j < BATCH_SIZE; ++j) {
            fe_sub(dx[j], g_Q_table[j].x, P_base.x);
            if (j == 0) {
                c[0] = dx[0];
            } else {
                fe_mul(c[j], c[j - 1], dx[j]);
            }
        }

        // 2. Single modular inversion for all 128 points!
        fe256 inv_all;
        gmp.invert(inv_all, c[BATCH_SIZE - 1]);

        // 3. Backward pass to extract all 128 individual inverses dx_inv[j]
        for (int j = BATCH_SIZE - 1; j > 0; --j) {
            fe_mul(dx_inv[j], inv_all, c[j - 1]);
            fe_mul(inv_all, inv_all, dx[j]);
        }
        dx_inv[0] = inv_all;

        // 4. Compute all 128 points P_j = P_base + Q_table[j], serialize, SHA-256, RIPEMD-160
        AffinePoint next_P_base;
        for (int j = 0; j < BATCH_SIZE; ++j) {
            fe256 dy, lam, lam2, x3, y3, diffx;
            fe_sub(dy, g_Q_table[j].y, P_base.y);
            fe_mul(lam, dy, dx_inv[j]);
            fe_sqr(lam2, lam);
            fe_sub(x3, lam2, P_base.x);
            fe_sub(x3, x3, g_Q_table[j].x);
            fe_sub(diffx, P_base.x, x3);
            fe_mul(y3, lam, diffx);
            fe_sub(y3, y3, P_base.y);

            if (j == BATCH_SIZE - 1) {
                next_P_base.x = x3;
                next_P_base.y = y3;
                next_P_base.infinity = false;
            }

            if (checked + j < num_keys) {
                uint8_t pubkey33[33];
                pubkey33[0] = (y3.d[0] & 1ULL) ? 0x03 : 0x02;
                fe_to_bytes_be(pubkey33 + 1, x3);

                uint8_t sha_digest[32];
                sha256_33bytes_armv8(pubkey33, sha_digest);

                uint32_t h160[5];
                ripemd160_32bytes(sha_digest, h160);

                int hit = match_targets(h160);
                if (__builtin_expect(hit != 0, 0)) {
                    __uint128_t hit_k = base_k + j;
                    if (found_puzzle_id) *found_puzzle_id = hit;
                    if (found_priv_hi) *found_priv_hi = (uint64_t)(hit_k >> 64);
                    if (found_priv_lo) *found_priv_lo = (uint64_t)hit_k;
                    if (found_pubkey33) std::memcpy(found_pubkey33, pubkey33, 33);
                    if (found_hash160) std::memcpy(found_hash160, h160, 20);
                    return hit;
                }
            }
        }

        P_base = next_P_base;
        base_k += BATCH_SIZE;
        checked += BATCH_SIZE;
    }

    return 0;
}

int puzzle_self_test(char* out_json, int max_len) {
    // Test vector: Puzzle #66 privkey = 0x2832ed74f2b5e35ee
    // Start 500 keys earlier so it steps across multiple 128-key Montgomery batches!
    __uint128_t target_k = ((__uint128_t)0x2ULL << 64) | 0x832ed74f2b5e35eeULL;
    __uint128_t start_k  = target_k - 500;

    int found_id = 0;
    uint64_t found_hi = 0, found_lo = 0;
    uint8_t pubkey[33] = {0};
    uint8_t h160[20] = {0};

    int rc = puzzle_scan_range(
        (uint64_t)(start_k >> 64),
        (uint64_t)start_k,
        1024,
        &found_id,
        &found_hi,
        &found_lo,
        pubkey,
        h160
    );

    char pub_hex[67] = {0};
    for (int i = 0; i < 33; ++i) std::snprintf(pub_hex + i * 2, 3, "%02x", pubkey[i]);
    char h160_hex[41] = {0};
    for (int i = 0; i < 20; ++i) std::snprintf(h160_hex + i * 2, 3, "%02x", h160[i]);

    bool ok = (rc == 66) &&
              (found_hi == 0x2ULL) &&
              (found_lo == 0x832ed74f2b5e35eeULL) &&
              (std::strcmp(h160_hex, "20d45a6a762535700ce9e0b216e31994335db8a5") == 0);

    if (out_json && max_len > 0) {
        std::snprintf(
            out_json, max_len,
            "{\"passed\": %s, \"puzzle_id\": %d, \"privkey_hex\": \"0x%llx%016llx\", \"pubkey_hex\": \"%s\", \"hash160_hex\": \"%s\"}",
            ok ? "true" : "false",
            found_id,
            (unsigned long long)found_hi,
            (unsigned long long)found_lo,
            pub_hex,
            h160_hex
        );
    }
    return ok ? 1 : 0;
}

} // extern "C"
