/* gpa_decoder.c - Decodificador de referencia do GhostPredict em C, sem alocacao.
 * Porte bit-exato de ghost_core.rs (caminho de descompressao). Todo o estado e
 * estatico (.bss/.data); nenhuma chamada a malloc.
 */
#include "gpa_decoder.h"
#include <string.h>

/* ----------------------------- constantes (== ghost_core.rs) ------------- */
#define MAX_VALUE 0xFFFFFFFFu
#define HALF      0x80000000u
#define Q1        0x40000000u
#define Q3        0xC0000000u
#define ALPHABET_SIZE   18
#define EOF_SYMBOL      16
#define MATCH_SYMBOL    17
#define FLAG_TOTAL      64
#define FLAG_STORED_LOW 63
#define DIST_BUCKETS    16
#define LEN_BUCKETS     7
#define DIST_CODE_SIZE  19   /* 3 + DIST_BUCKETS */
#define LEN_CODE_SIZE   8    /* 1 + LEN_BUCKETS  */
#define RESCALE         2048

static const uint16_t ASCII_PRIOR[ALPHABET_SIZE] = {1,2,2,2,2,2,2,2,1,1,1,1,1,1,1,1,1,1};
static const size_t DIST_BASE[DIST_BUCKETS]  = {1,2,3,5,9,17,33,65,129,257,513,1025,2049,4097,8193,16385};
static const uint32_t DIST_EXTRA[DIST_BUCKETS] = {0,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14};
static const size_t LEN_BASE[LEN_BUCKETS]  = {4,5,6,8,12,20,36};
static const uint32_t LEN_EXTRA[LEN_BUCKETS] = {0,0,1,2,3,4,5};

/* ----------------------------- modelo (estado estatico) ------------------ */
typedef struct {
    uint16_t graph[256][ALPHABET_SIZE];
    uint16_t graph_cum[256][ALPHABET_SIZE + 1];
    uint16_t graph_totals[256];
    uint16_t o0_counts[ALPHABET_SIZE];
    uint16_t o0_cum[ALPHABET_SIZE + 1];
    size_t   current_node;
    uint16_t dist_code_counts[DIST_CODE_SIZE];
    uint16_t dist_code_cum[DIST_CODE_SIZE + 1];
    size_t   last_offsets[3];
    uint16_t len_code_counts[LEN_CODE_SIZE];
    uint16_t len_code_cum[LEN_CODE_SIZE + 1];
    size_t   last_length;
} gpa_model_t;

static gpa_model_t M;

static void rebuild_cum(uint16_t *cum, const uint16_t *counts, int n) {
    uint16_t acc = 0; cum[0] = 0;
    for (int k = 0; k < n; k++) { acc += counts[k]; cum[k + 1] = acc; }
}

static void model_init(void) {
    memset(&M, 0, sizeof(M));
    for (int i = 0; i < ALPHABET_SIZE; i++) M.o0_counts[i] = ASCII_PRIOR[i];
    rebuild_cum(M.o0_cum, M.o0_counts, ALPHABET_SIZE);
    for (int i = 0; i < DIST_CODE_SIZE; i++) M.dist_code_counts[i] = 1;
    rebuild_cum(M.dist_code_cum, M.dist_code_counts, DIST_CODE_SIZE);
    for (int i = 0; i < LEN_CODE_SIZE; i++) M.len_code_counts[i] = 1;
    rebuild_cum(M.len_code_cum, M.len_code_counts, LEN_CODE_SIZE);
}

/* localiza o simbolo s com cum[s] <= target < cum[s+1] (intervalo de contagem > 0) */
static int find_sym(const uint16_t *cum, int n, uint32_t target) {
    int s = 0;
    while (s < n - 1 && cum[s + 1] <= target) s++;
    return s;
}

static int bucket_dist(size_t d) { for (int i = DIST_BUCKETS - 1; i >= 0; i--) if (d >= DIST_BASE[i]) return i; return 0; }
static int bucket_len(size_t l)  { for (int i = LEN_BUCKETS - 1;  i >= 0; i--) if (l >= LEN_BASE[i])  return i; return 0; }

static void mtf_offsets(size_t dist) {
    int idx = -1;
    for (int i = 0; i < 3; i++) if (M.last_offsets[i] == dist) { idx = i; break; }
    if (idx >= 0) {
        if (idx > 0) {
            size_t tmp = M.last_offsets[idx];
            for (int i = idx; i >= 1; i--) M.last_offsets[i] = M.last_offsets[i - 1];
            M.last_offsets[0] = tmp;
        }
    } else {
        M.last_offsets[2] = M.last_offsets[1];
        M.last_offsets[1] = M.last_offsets[0];
        M.last_offsets[0] = dist;
    }
}

/* ----------------------------- bit reader + decoder aritmetico ----------- */
static const uint8_t *BR_bytes; static size_t BR_len; static size_t BR_bitidx;
static void br_init(const uint8_t *b, size_t n) { BR_bytes = b; BR_len = n; BR_bitidx = 0; }
static uint32_t br_read_bit(void) {
    size_t bp = BR_bitidx >> 3;
    if (bp >= BR_len) { BR_bitidx++; return 0; }
    uint32_t bit = (BR_bytes[bp] >> (7 - (BR_bitidx & 7))) & 1u;
    BR_bitidx++; return bit;
}

static uint32_t DL_low, DL_high, DL_value;
static void dec_init(void) {
    DL_low = 0; DL_high = MAX_VALUE; DL_value = 0;
    for (int i = 0; i < 32; i++) DL_value = (DL_value << 1) | br_read_bit();
}
static uint32_t dec_get_target(uint32_t total) {
    uint64_t range = (uint64_t)DL_high - (uint64_t)DL_low + 1;
    return (uint32_t)((((uint64_t)DL_value - (uint64_t)DL_low + 1) * total - 1) / range);
}
static void dec_decode(uint32_t low_c, uint32_t high_c, uint32_t total) {
    uint64_t range = (uint64_t)DL_high - (uint64_t)DL_low + 1;
    DL_high = DL_low + (uint32_t)((range * high_c) / total) - 1;
    DL_low  = DL_low + (uint32_t)((range * low_c)  / total);
    for (;;) {
        if (DL_high < HALF) { /* pass */ }
        else if (DL_low >= HALF) { DL_low -= HALF; DL_high -= HALF; DL_value -= HALF; }
        else if (DL_low >= Q1 && DL_high < Q3) { DL_low -= Q1; DL_high -= Q1; DL_value -= Q1; }
        else break;
        DL_low  = (DL_low << 1);
        DL_high = (DL_high << 1) | 1u;
        DL_value = (DL_value << 1) | br_read_bit();
    }
}
static uint32_t dec_decode_bit(void) {
    uint32_t target = dec_get_target(2);
    uint32_t bit = (target >= 1) ? 1u : 0u;
    dec_decode(bit, bit + 1, 2);
    return bit;
}

/* ----------------------------- decode_symbol (PPM com escape/exclusao) --- */
static int decode_symbol(void) {
    size_t node = M.current_node;
    uint16_t t = M.graph_totals[node];
    int symbol;
    if (t == 0) {
        uint16_t total = M.o0_cum[ALPHABET_SIZE];
        uint32_t target = dec_get_target(total);
        symbol = find_sym(M.o0_cum, ALPHABET_SIZE, target);
        dec_decode(M.o0_cum[symbol], M.o0_cum[symbol + 1], total);
    } else {
        uint16_t adjusted = t + 1;
        uint32_t target = dec_get_target(adjusted);
        if (target == t) {
            dec_decode(t, adjusted, adjusted);
            uint16_t masked_total = M.o0_cum[ALPHABET_SIZE];
            for (int j = 0; j < ALPHABET_SIZE; j++)
                if (M.graph[node][j] > 0) masked_total -= M.o0_counts[j];
            uint32_t target_m = dec_get_target(masked_total);
            uint16_t acc = 0, low_s = 0, high_s = 0; int sym = 0;
            for (int s = 0; s < ALPHABET_SIZE; s++) {
                if (M.graph[node][s] > 0) continue;
                uint16_t w = M.o0_counts[s];
                if ((uint32_t)acc + w > target_m) { sym = s; low_s = acc; high_s = acc + w; break; }
                acc += w;
            }
            dec_decode(low_s, high_s, masked_total);
            symbol = sym;
        } else {
            symbol = find_sym(M.graph_cum[node], ALPHABET_SIZE, target);
            dec_decode(M.graph_cum[node][symbol], M.graph_cum[node][symbol + 1], adjusted);
        }
    }
    /* aprendizado (identico a encode_token) */
    uint16_t edge_x = M.graph[node][symbol];
    M.graph[node][symbol] = edge_x + 1;
    M.graph_totals[node] = t + 1;
    if (M.graph_totals[node] >= RESCALE) {
        uint16_t sum = 0;
        for (int s = 0; s < ALPHABET_SIZE; s++)
            if (M.graph[node][s] > 0) { M.graph[node][s] = (M.graph[node][s] >> 1) | 1; sum += M.graph[node][s]; }
        M.graph_totals[node] = sum;
    }
    rebuild_cum(M.graph_cum[node], M.graph[node], ALPHABET_SIZE);
    M.o0_counts[symbol] += 1;
    uint32_t o0sum = 0; for (int s = 0; s < ALPHABET_SIZE; s++) o0sum += M.o0_counts[s];
    if (o0sum >= RESCALE) for (int s = 0; s < ALPHABET_SIZE; s++) M.o0_counts[s] = (M.o0_counts[s] >> 1) | 1;
    rebuild_cum(M.o0_cum, M.o0_counts, ALPHABET_SIZE);
    return symbol;
}

static void decode_match(size_t *out_dist, size_t *out_len) {
    uint32_t d_total = M.dist_code_cum[DIST_CODE_SIZE];
    uint32_t d_target = dec_get_target(d_total);
    int dist_code = find_sym(M.dist_code_cum, DIST_CODE_SIZE, d_target);
    dec_decode(M.dist_code_cum[dist_code], M.dist_code_cum[dist_code + 1], d_total);
    M.dist_code_counts[dist_code] += 1;
    { uint32_t sum = 0; for (int s = 0; s < DIST_CODE_SIZE; s++) sum += M.dist_code_counts[s];
      if (sum >= RESCALE) for (int s = 0; s < DIST_CODE_SIZE; s++) M.dist_code_counts[s] = (M.dist_code_counts[s] >> 1) | 1; }
    rebuild_cum(M.dist_code_cum, M.dist_code_counts, DIST_CODE_SIZE);
    size_t dist;
    if (dist_code < 3) dist = M.last_offsets[dist_code];
    else {
        int db = dist_code - 3; uint32_t eb = DIST_EXTRA[db]; uint32_t extra = 0;
        for (uint32_t k = 0; k < eb; k++) extra = (extra << 1) | dec_decode_bit();
        dist = DIST_BASE[db] + extra;
    }
    mtf_offsets(dist);

    uint32_t l_total = M.len_code_cum[LEN_CODE_SIZE];
    uint32_t l_target = dec_get_target(l_total);
    int len_code = find_sym(M.len_code_cum, LEN_CODE_SIZE, l_target);
    dec_decode(M.len_code_cum[len_code], M.len_code_cum[len_code + 1], l_total);
    M.len_code_counts[len_code] += 1;
    { uint32_t sum = 0; for (int s = 0; s < LEN_CODE_SIZE; s++) sum += M.len_code_counts[s];
      if (sum >= RESCALE) for (int s = 0; s < LEN_CODE_SIZE; s++) M.len_code_counts[s] = (M.len_code_counts[s] >> 1) | 1; }
    rebuild_cum(M.len_code_cum, M.len_code_counts, LEN_CODE_SIZE);
    size_t len;
    if (len_code == 0) len = M.last_length;
    else {
        int lb = len_code - 1; uint32_t eb = LEN_EXTRA[lb]; uint32_t extra = 0;
        for (uint32_t k = 0; k < eb; k++) extra = (extra << 1) | dec_decode_bit();
        len = LEN_BASE[lb] + extra;
    }
    M.last_length = len;
    *out_dist = dist; *out_len = len;
}

/* ----------------------------- API: descompressao normal ----------------- */
int gpa_decompress(const uint8_t *in, size_t in_len, uint8_t *out, size_t out_cap) {
    if (in_len == 0) return 0;
    model_init();
    br_init(in, in_len);
    dec_init();
    size_t outn = 0;
    if (dec_get_target(FLAG_TOTAL) >= FLAG_STORED_LOW) {          /* modo armazenado */
        dec_decode(FLAG_STORED_LOW, FLAG_TOTAL, FLAG_TOTAL);
        for (;;) {
            uint32_t tg = dec_get_target(257);
            if (tg == 256) { dec_decode(256, 257, 257); break; }
            dec_decode(tg, tg + 1, 257);
            if (outn >= out_cap) return -1;
            out[outn++] = (uint8_t)tg;
        }
        return (int)outn;
    }
    dec_decode(0, FLAG_STORED_LOW, FLAG_TOTAL);                    /* modo comprimido */
    int nibble_hi = -1;
    for (;;) {
        int symbol = decode_symbol();
        if (symbol == EOF_SYMBOL) break;
        if (symbol == MATCH_SYMBOL) {
            size_t dist, len; decode_match(&dist, &len);
            if (dist > outn) return -1;
            size_t start = outn - dist;
            for (size_t k = 0; k < len; k++) { if (outn >= out_cap) return -1; out[outn] = out[start + k]; outn++; }
        } else {
            if (nibble_hi < 0) nibble_hi = symbol;
            else { if (outn >= out_cap) return -1; out[outn++] = (uint8_t)((nibble_hi << 4) | symbol); nibble_hi = -1; }
            M.current_node = ((M.current_node & 0x0F) << 4) | (size_t)symbol;
        }
    }
    return (int)outn;
}

/* ===================================================================== */
/* MODO COM PRIOR (opcional): aquece o modelo com o primer via LZ77        */
/* ===================================================================== */
#ifdef GPA_ENABLE_PRIMED
#define LZ_WINDOW     32768
#define LZ_WIN_MASK   (LZ_WINDOW - 1)
#define LZ_HASH_SIZE  16381
#define LZ_MIN_MATCH  4
#define LZ_MAX_MATCH  67
#define LZ_MAX_CHAIN  128
#ifndef GPA_WORK_SIZE
#define GPA_WORK_SIZE (32768 + 16384)   /* primer (<=32 KB) + mensagem reconstruida */
#endif

static int32_t LZ_head[LZ_HASH_SIZE];
static int32_t LZ_prev[LZ_WINDOW];
static uint8_t WORK[GPA_WORK_SIZE];

static size_t lz_hash(const uint8_t *raw, size_t p) {
    size_t h = ((size_t)raw[p] << 16) ^ ((size_t)raw[p + 1] << 8) ^ (size_t)raw[p + 2];
    return h % LZ_HASH_SIZE;
}
static void lz_insert(const uint8_t *raw, size_t p, size_t n) {
    if (p + 2 >= n) return;
    size_t hv = lz_hash(raw, p);
    LZ_prev[p & LZ_WIN_MASK] = LZ_head[hv];
    LZ_head[hv] = (int32_t)p;
}
static void lz_find(const uint8_t *raw, size_t i, size_t n, size_t *bl, size_t *bd) {
    size_t best_len = 0, best_dist = 0;
    if (i + LZ_MIN_MATCH > n) { *bl = 0; *bd = 0; return; }
    size_t hv = lz_hash(raw, i);
    int32_t cand = LZ_head[hv];
    int attempts = 0;
    size_t limit = (LZ_MAX_MATCH < (n - i)) ? LZ_MAX_MATCH : (n - i);
    while (cand >= 0 && (i - (size_t)cand) <= LZ_WINDOW && attempts < LZ_MAX_CHAIN) {
        size_t c = (size_t)cand;
        if (best_len > 0) {
            if (i + best_len >= n) break;
            if (raw[c + best_len] != raw[i + best_len]) { cand = LZ_prev[c & LZ_WIN_MASK]; attempts++; continue; }
        }
        size_t l = 0;
        while (l < limit && raw[c + l] == raw[i + l]) l++;
        if (l > best_len && l >= LZ_MIN_MATCH) { best_len = l; best_dist = i - c; if (l >= limit) break; }
        cand = LZ_prev[c & LZ_WIN_MASK]; attempts++;
    }
    *bl = best_len; *bd = best_dist;
}

/* aprendizado de um token (espelha encode_token, sem codificar) */
static void learn_token(int symbol, int is_match, size_t dist, size_t len) {
    size_t node = M.current_node;
    uint16_t t = M.graph_totals[node];
    uint16_t edge_x = M.graph[node][symbol];
    M.graph[node][symbol] = edge_x + 1;
    M.graph_totals[node] = t + 1;
    if (M.graph_totals[node] >= RESCALE) {
        uint16_t sum = 0;
        for (int s = 0; s < ALPHABET_SIZE; s++)
            if (M.graph[node][s] > 0) { M.graph[node][s] = (M.graph[node][s] >> 1) | 1; sum += M.graph[node][s]; }
        M.graph_totals[node] = sum;
    }
    rebuild_cum(M.graph_cum[node], M.graph[node], ALPHABET_SIZE);
    M.o0_counts[symbol] += 1;
    uint32_t o0sum = 0; for (int s = 0; s < ALPHABET_SIZE; s++) o0sum += M.o0_counts[s];
    if (o0sum >= RESCALE) for (int s = 0; s < ALPHABET_SIZE; s++) M.o0_counts[s] = (M.o0_counts[s] >> 1) | 1;
    rebuild_cum(M.o0_cum, M.o0_counts, ALPHABET_SIZE);
    if (is_match) {
        int dc = (dist == M.last_offsets[0]) ? 0 : (dist == M.last_offsets[1]) ? 1 :
                 (dist == M.last_offsets[2]) ? 2 : (3 + bucket_dist(dist));
        M.dist_code_counts[dc] += 1;
        { uint32_t sum = 0; for (int s = 0; s < DIST_CODE_SIZE; s++) sum += M.dist_code_counts[s];
          if (sum >= RESCALE) for (int s = 0; s < DIST_CODE_SIZE; s++) M.dist_code_counts[s] = (M.dist_code_counts[s] >> 1) | 1; }
        rebuild_cum(M.dist_code_cum, M.dist_code_counts, DIST_CODE_SIZE);
        mtf_offsets(dist);
        int lc = (len == M.last_length) ? 0 : (1 + bucket_len(len));
        M.len_code_counts[lc] += 1;
        { uint32_t sum = 0; for (int s = 0; s < LEN_CODE_SIZE; s++) sum += M.len_code_counts[s];
          if (sum >= RESCALE) for (int s = 0; s < LEN_CODE_SIZE; s++) M.len_code_counts[s] = (M.len_code_counts[s] >> 1) | 1; }
        rebuild_cum(M.len_code_cum, M.len_code_counts, LEN_CODE_SIZE);
        M.last_length = len;
    } else if (symbol != EOF_SYMBOL) {
        M.current_node = ((M.current_node & 0x0F) << 4) | (size_t)symbol;
    }
}
static void learn_nib(uint8_t s) { learn_token((int)s, 0, 0, 0); }

/* aquece o modelo com o primer (parse_streaming + learn_token, exceto EOF) */
static void prime_model(const uint8_t *raw, size_t n) {
    for (size_t k = 0; k < LZ_HASH_SIZE; k++) LZ_head[k] = -1;
    for (size_t k = 0; k < LZ_WINDOW; k++) LZ_prev[k] = -1;
    if (n < (size_t)(LZ_MIN_MATCH + 2)) {
        for (size_t k = 0; k < n; k++) { learn_nib((raw[k] >> 4) & 0x0F); learn_nib(raw[k] & 0x0F); }
        return;
    }
    size_t i = 0;
    while (i < n) {
        if (i + LZ_MIN_MATCH > n) {
            for (size_t k = i; k < n; k++) { learn_nib((raw[k] >> 4) & 0x0F); learn_nib(raw[k] & 0x0F); }
            break;
        }
        size_t cur_len, cur_dist;
        lz_find(raw, i, n, &cur_len, &cur_dist);
        lz_insert(raw, i, n);
        if (cur_len >= LZ_MIN_MATCH) {
            if (i + 1 < n && cur_len < LZ_MAX_MATCH) {
                size_t nl, nd; lz_find(raw, i + 1, n, &nl, &nd);
                if (nl > cur_len) { uint8_t b = raw[i]; learn_nib((b >> 4) & 0x0F); learn_nib(b & 0x0F); i += 1; continue; }
            }
            learn_token(MATCH_SYMBOL, 1, cur_dist, cur_len);
            for (size_t j = 1; j < cur_len; j++) lz_insert(raw, i + j, n);
            i += cur_len;
        } else {
            uint8_t b = raw[i]; learn_nib((b >> 4) & 0x0F); learn_nib(b & 0x0F); i += 1;
        }
    }
}

int gpa_decompress_primed(const uint8_t *in, size_t in_len,
                          const uint8_t *primer, size_t primer_len,
                          uint8_t *out, size_t out_cap) {
    if (in_len == 0) return 0;
    if (primer_len > GPA_WORK_SIZE) return -1;
    model_init();
    prime_model(primer, primer_len);
    br_init(in, in_len);
    dec_init();
    memcpy(WORK, primer, primer_len);
    size_t wn = primer_len;
    int nibble_hi = -1;
    for (;;) {
        int symbol = decode_symbol();
        if (symbol == EOF_SYMBOL) break;
        if (symbol == MATCH_SYMBOL) {
            size_t dist, len; decode_match(&dist, &len);
            if (dist > wn) return -1;
            size_t start = wn - dist;
            for (size_t k = 0; k < len; k++) { if (wn >= GPA_WORK_SIZE) return -1; WORK[wn] = WORK[start + k]; wn++; }
        } else {
            if (nibble_hi < 0) nibble_hi = symbol;
            else { if (wn >= GPA_WORK_SIZE) return -1; WORK[wn++] = (uint8_t)((nibble_hi << 4) | symbol); nibble_hi = -1; }
            M.current_node = ((M.current_node & 0x0F) << 4) | (size_t)symbol;
        }
    }
    size_t msglen = wn - primer_len;
    if (msglen > out_cap) return -1;
    memcpy(out, WORK + primer_len, msglen);
    return (int)msglen;
}
#endif /* GPA_ENABLE_PRIMED */
