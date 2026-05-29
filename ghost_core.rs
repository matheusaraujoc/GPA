// GhostPredict v9 - Engine de Compressão em Rust
// Implementação em conformidade estrita com a Especificação Algorítmica v9

use std::cmp::min;

// ============================================================================
// CONSTANTES FUNDAMENTAIS
// ============================================================================
pub const MAX_VALUE: u32 = 0xFFFFFFFF;
pub const HALF: u32      = 0x80000000;
pub const Q1: u32        = 0x40000000;
pub const Q3: u32        = 0xC0000000;

pub const ALPHABET_SIZE: usize = 18;
pub const EOF_SYMBOL: usize     = 16;
pub const MATCH_SYMBOL: usize   = 17;

pub const LZ_WINDOW: usize      = 4096;
pub const LZ_WIN_MASK: usize    = 4095;
pub const LZ_MIN_MATCH: usize   = 4;
pub const LZ_MAX_MATCH: usize   = 67;
pub const LZ_HASH_SIZE: usize   = 16381;
pub const LZ_MAX_CHAIN: usize   = 16;

pub const DIST_BUCKETS: usize = 13;
pub const DIST_BASE: [usize; 13] = [1, 2, 3, 5, 9, 17, 33, 65, 129, 257, 513, 1025, 2049];
pub const DIST_EXTRA: [u32; 13]  = [0, 0, 1, 2, 3,  4,  5,  6,   7,   8,   9,   10,   11];

pub const LEN_BUCKETS: usize = 7;
pub const LEN_BASE: [usize; 7] = [4, 5, 6, 8, 12, 20, 36];
pub const LEN_EXTRA: [u32; 7]  = [0, 0, 1, 2,  3,  4,  5];

pub const DIST_CODE_SIZE: usize = 3 + DIST_BUCKETS; // 16
pub const LEN_CODE_SIZE: usize  = 1 + LEN_BUCKETS;  // 8

pub const ASCII_PRIOR: [u32; 18] = [
    1, 2, 2, 2, 2, 2, 2, 2,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1,
];

// ============================================================================
// AUXILIARY UTILITIES
// ============================================================================
#[inline]
fn bucket_dist(d: usize) -> usize {
    for i in (0..DIST_BUCKETS).rev() {
        if d >= DIST_BASE[i] {
            return i;
        }
    }
    0
}

#[inline]
fn bucket_len(l: usize) -> usize {
    for i in (0..LEN_BUCKETS).rev() {
        if l >= LEN_BASE[i] {
            return i;
        }
    }
    0
}

fn mtf_offsets(last_offsets: &mut [usize; 3], dist: usize) {
    if let Some(idx) = last_offsets.iter().position(|&x| x == dist) {
        if idx > 0 {
            let tmp = last_offsets[idx];
            for i in (1..=idx).rev() {
                last_offsets[i] = last_offsets[i - 1];
            }
            last_offsets[0] = tmp;
        }
    } else {
        last_offsets[2] = last_offsets[1];
        last_offsets[1] = last_offsets[0];
        last_offsets[0] = dist;
    }
}

// ============================================================================
// BIT STREAM IO
// ============================================================================
pub struct BitWriter {
    pub bytes: Vec<u8>,
    bit_accum: u32,
    bit_count: u32,
}

impl BitWriter {
    pub fn new() -> Self {
        BitWriter {
            bytes: Vec::new(),
            bit_accum: 0,
            bit_count: 0,
        }
    }

    pub fn write_bit(&mut self, bit: u32) {
        self.bit_accum = (self.bit_accum << 1) | bit;
        self.bit_count += 1;
        if self.bit_count == 8 {
            self.bytes.push(self.bit_accum as u8);
            self.bit_accum = 0;
            self.bit_count = 0;
        }
    }

    pub fn flush(&mut self) {
        if self.bit_count > 0 {
            self.bit_accum <<= 8 - self.bit_count;
            self.bytes.push(self.bit_accum as u8);
            self.bit_accum = 0;
            self.bit_count = 0;
        }
    }
}

pub struct BitReader {
    bytes: Vec<u8>,
    bit_idx: usize,
}

impl BitReader {
    pub fn new(bytes: Vec<u8>) -> Self {
        BitReader { bytes, bit_idx: 0 }
    }

    pub fn read_bit(&mut self) -> u32 {
        let byte_pos = self.bit_idx / 8;
        if byte_pos >= self.bytes.len() {
            return 0;
        }
        let bit_pos = 7 - (self.bit_idx % 8);
        let bit = ((self.bytes[byte_pos] >> bit_pos) & 1) as u32;
        self.bit_idx += 1;
        bit
    }
}

// ============================================================================
// CODIFICADOR ARITMÉTICO
// ============================================================================
pub struct ArithmeticCoder {
    low: u32,
    high: u32,
    pending_bits: u32,
}

impl ArithmeticCoder {
    pub fn new() -> Self {
        ArithmeticCoder {
            low: 0,
            high: MAX_VALUE,
            pending_bits: 0,
        }
    }

    pub fn encode(&mut self, low_count: u32, high_count: u32, total_count: u32, writer: &mut BitWriter) {
        let range = (self.high as u64) - (self.low as u64) + 1;
        self.high = self.low + (((range * (high_count as u64)) / (total_count as u64)) as u32) - 1;
        self.low = self.low + (((range * (low_count as u64)) / (total_count as u64)) as u32);

        loop {
            if self.high < HALF {
                self.emit_bit(0, writer);
            } else if self.low >= HALF {
                self.emit_bit(1, writer);
                self.low -= HALF;
                self.high -= HALF;
            } else if self.low >= Q1 && self.high < Q3 {
                self.pending_bits += 1;
                self.low -= Q1;
                self.high -= Q1;
            } else {
                break;
            }
            self.low = (self.low << 1) & MAX_VALUE;
            self.high = ((self.high << 1) | 1) & MAX_VALUE;
        }
    }

    pub fn encode_bit(&mut self, bit: u32, writer: &mut BitWriter) {
        self.encode(bit, bit + 1, 2, writer);
    }

    fn emit_bit(&mut self, bit: u32, writer: &mut BitWriter) {
        writer.write_bit(bit);
        for _ in 0..self.pending_bits {
            writer.write_bit(bit ^ 1);
        }
        self.pending_bits = 0;
    }

    pub fn finish(&mut self, writer: &mut BitWriter) {
        self.pending_bits += 1;
        if self.low < Q1 {
            self.emit_bit(0, writer);
        } else {
            self.emit_bit(1, writer);
        }
        writer.flush();
    }
}

pub struct ArithmeticDecoder {
    low: u32,
    high: u32,
    value: u32,
}

impl ArithmeticDecoder {
    pub fn new(reader: &mut BitReader) -> Self {
        let mut value = 0;
        for _ in 0..32 {
            value = (value << 1) | reader.read_bit();
        }
        ArithmeticDecoder {
            low: 0,
            high: MAX_VALUE,
            value,
        }
    }

    pub fn get_target(&self, total_count: u32) -> u32 {
        let range = (self.high as u64) - (self.low as u64) + 1;
        ((((self.value as u64) - (self.low as u64) + 1) * (total_count as u64) - 1) / range) as u32
    }

    pub fn decode(&mut self, low_count: u32, high_count: u32, total_count: u32, reader: &mut BitReader) {
        let range = (self.high as u64) - (self.low as u64) + 1;
        self.high = self.low + (((range * (high_count as u64)) / (total_count as u64)) as u32) - 1;
        self.low = self.low + (((range * (low_count as u64)) / (total_count as u64)) as u32);

        loop {
            if self.high < HALF {
                // Pass
            } else if self.low >= HALF {
                self.low -= HALF;
                self.high -= HALF;
                self.value -= HALF;
            } else if self.low >= Q1 && self.high < Q3 {
                self.low -= Q1;
                self.high -= Q1;
                self.value -= Q1;
            } else {
                break;
            }
            self.low = (self.low << 1) & MAX_VALUE;
            self.high = ((self.high << 1) | 1) & MAX_VALUE;
            self.value = ((self.value << 1) | reader.read_bit()) & MAX_VALUE;
        }
    }

    pub fn decode_bit(&mut self, reader: &mut BitReader) -> u32 {
        let target = self.get_target(2);
        let bit = if target >= 1 { 1 } else { 0 };
        self.decode(bit, bit + 1, 2, reader);
        bit
    }
}

// ============================================================================
// TOKEN REPRESENTATION
// ============================================================================
#[derive(Debug, Clone, Copy)]
pub enum Token {
    Nibble(u8),
    EOF,
    Match { dist: usize, len: usize },
}

// ============================================================================
// LZ77 MATCH FINDER
// ============================================================================
pub struct LZ77 {
    head: [i16; LZ_HASH_SIZE],
    prev: [i16; LZ_WINDOW],
}

impl LZ77 {
    pub fn new() -> Self {
        LZ77 {
            head: [-1; LZ_HASH_SIZE],
            prev: [-1; LZ_WINDOW],
        }
    }

    #[inline]
    fn hash(raw: &[u8], p: usize) -> usize {
        let h = ((raw[p] as usize) << 16) ^ ((raw[p + 1] as usize) << 8) ^ (raw[p + 2] as usize);
        h % LZ_HASH_SIZE
    }

    fn find_match(&self, raw: &[u8], i: usize, n: usize) -> (usize, usize) {
        if i + LZ_MIN_MATCH > n {
            return (0, 0);
        }
        let hv = Self::hash(raw, i);
        let mut cand = self.head[hv] as isize;
        let mut best_len = 0;
        let mut best_dist = 0;
        let mut attempts = 0;
        let limit = min(LZ_MAX_MATCH, n - i);

        while cand >= 0 && (i - cand as usize) <= LZ_WINDOW && attempts < LZ_MAX_CHAIN {
            let c_pos = cand as usize;
            if best_len > 0 {
                if i + best_len >= n {
                    break;
                }
                // Quick filter
                if raw[c_pos + best_len] != raw[i + best_len] {
                    cand = self.prev[c_pos & LZ_WIN_MASK] as isize;
                    attempts += 1;
                    continue;
                }
            }

            let mut l = 0;
            while l < limit && raw[c_pos + l] == raw[i + l] {
                l += 1;
            }
            if l > best_len && l >= LZ_MIN_MATCH {
                best_len = l;
                best_dist = i - c_pos;
                if l >= limit {
                    break;
                }
            }
            cand = self.prev[c_pos & LZ_WIN_MASK] as isize;
            attempts += 1;
        }

        (best_len, best_dist)
    }

    fn insert_hash(&mut self, raw: &[u8], p: usize, n: usize) {
        if p + 2 >= n {
            return;
        }
        let hv = Self::hash(raw, p);
        self.prev[p & LZ_WIN_MASK] = self.head[hv];
        self.head[hv] = p as i16;
    }

    pub fn parse(&mut self, raw: &[u8]) -> Vec<Token> {
        let n = raw.len();
        let mut tokens = Vec::new();

        if n < LZ_MIN_MATCH + 2 {
            for &b in raw {
                tokens.push(Token::Nibble((b >> 4) & 0x0F));
                tokens.push(Token::Nibble(b & 0x0F));
            }
            tokens.push(Token::EOF);
            return tokens;
        }

        let mut i = 0;
        while i < n {
            if i + LZ_MIN_MATCH > n {
                for k in i..n {
                    tokens.push(Token::Nibble((raw[k] >> 4) & 0x0F));
                    tokens.push(Token::Nibble(raw[k] & 0x0F));
                }
                break;
            }

            let (cur_len, cur_dist) = self.find_match(raw, i, n);
            self.insert_hash(raw, i, n);

            if cur_len >= LZ_MIN_MATCH {
                // Lazy match checking
                if i + 1 < n && cur_len < LZ_MAX_MATCH {
                    let (next_len, _) = self.find_match(raw, i + 1, n);
                    if next_len > cur_len {
                        let b = raw[i];
                        tokens.push(Token::Nibble((b >> 4) & 0x0F));
                        tokens.push(Token::Nibble(b & 0x0F));
                        i += 1;
                        continue;
                    }
                }

                tokens.push(Token::Match { dist: cur_dist, len: cur_len });
                for j in 1..cur_len {
                    self.insert_hash(raw, i + j, n);
                }
                i += cur_len;
            } else {
                let b = raw[i];
                tokens.push(Token::Nibble((b >> 4) & 0x0F));
                tokens.push(Token::Nibble(b & 0x0F));
                i += 1;
            }
        }

        tokens.push(Token::EOF);
        tokens
    }
}

// ============================================================================
// GHOSTPREDICT v9 COMPRESSION/DECOMPRESSION ENGINE
// ============================================================================
pub struct GhostPredictEngine {
    // Principal PPM
    graph: Box<[[u32; ALPHABET_SIZE]; 256]>,
    graph_cum: Box<[[u32; ALPHABET_SIZE + 1]; 256]>,
    graph_totals: [u32; 256],
    o0_counts: [u32; ALPHABET_SIZE],
    o0_cum: [u32; ALPHABET_SIZE + 1],
    current_node: usize,

    // Dist Modelo
    dist_code_counts: [u32; DIST_CODE_SIZE],
    dist_code_cum: [u32; DIST_CODE_SIZE + 1],
    last_offsets: [usize; 3],

    // Len Modelo
    len_code_counts: [u32; LEN_CODE_SIZE],
    len_code_cum: [u32; LEN_CODE_SIZE + 1],
    last_length: usize,
}

impl GhostPredictEngine {
    pub fn new() -> Self {
        // Inicializa o0 com ASCII_PRIOR
        let mut o0_cum = [0; ALPHABET_SIZE + 1];
        let mut s = 0;
        for i in 0..ALPHABET_SIZE {
            s += ASCII_PRIOR[i];
            o0_cum[i + 1] = s;
        }

        // Inicializa dist_code
        let mut dist_code_cum = [0; DIST_CODE_SIZE + 1];
        for i in 0..=DIST_CODE_SIZE {
            dist_code_cum[i] = i as u32;
        }

        // Inicializa len_code
        let mut len_code_cum = [0; LEN_CODE_SIZE + 1];
        for i in 0..=LEN_CODE_SIZE {
            len_code_cum[i] = i as u32;
        }

        GhostPredictEngine {
            graph: Box::new([[0; ALPHABET_SIZE]; 256]),
            graph_cum: Box::new([[0; ALPHABET_SIZE + 1]; 256]),
            graph_totals: [0; 256],
            o0_counts: ASCII_PRIOR,
            o0_cum,
            current_node: 0,
            dist_code_counts: [1; DIST_CODE_SIZE],
            dist_code_cum,
            last_offsets: [0; 3],
            len_code_counts: [1; LEN_CODE_SIZE],
            len_code_cum,
            last_length: 0,
        }
    }

    pub fn compress(&mut self, token_stream: &[Token]) -> Vec<u8> {
        let mut writer = BitWriter::new();
        let mut coder = ArithmeticCoder::new();

        for &token in token_stream {
            let symbol = match token {
                Token::Nibble(n) => n as usize,
                Token::EOF => EOF_SYMBOL,
                Token::Match { .. } => MATCH_SYMBOL,
            };

            let edges = &self.graph[self.current_node];
            let t = self.graph_totals[self.current_node];
            let edge_x = edges[symbol];

            if t == 0 {
                coder.encode(self.o0_cum[symbol], self.o0_cum[symbol + 1], self.o0_cum[ALPHABET_SIZE], &mut writer);
            } else if edge_x > 0 {
                let adjusted = t + 1; // PPMA: escape weight = 1
                let ecum = &self.graph_cum[self.current_node];
                coder.encode(ecum[symbol], ecum[symbol + 1], adjusted, &mut writer);
            } else {
                let adjusted = t + 1;
                // Encode escape at [T, T+1)
                coder.encode(t, t + 1, adjusted, &mut writer);

                // Exclussão PPM
                let mut masked_total = self.o0_cum[ALPHABET_SIZE];
                let mut masked_low = self.o0_cum[symbol];
                for j in 0..ALPHABET_SIZE {
                    if edges[j] > 0 {
                        let c = self.o0_counts[j];
                        masked_total -= c;
                        if j < symbol {
                            masked_low -= c;
                        }
                    }
                }
                let masked_high = masked_low + self.o0_counts[symbol];
                coder.encode(masked_low, masked_high, masked_total, &mut writer);
            }

            // Aprendizado e Reescalonamento para o nó do grafo
            self.graph[self.current_node][symbol] = edge_x + 1;
            self.graph_totals[self.current_node] = t + 1;
            
            // Reescalonamento PPM se atingir limiar de 2048 para evitar overflow e estagnação
            if self.graph_totals[self.current_node] >= 2048 {
                let mut sum_ctx = 0;
                for s in 0..ALPHABET_SIZE {
                    if self.graph[self.current_node][s] > 0 {
                        self.graph[self.current_node][s] = (self.graph[self.current_node][s] >> 1) | 1;
                        sum_ctx += self.graph[self.current_node][s];
                    }
                }
                self.graph_totals[self.current_node] = sum_ctx;
            }

            // Reconstrói a tabela acumulativa do grafo
            let mut acc = 0;
            self.graph_cum[self.current_node][0] = 0;
            for k in 0..ALPHABET_SIZE {
                acc += self.graph[self.current_node][k];
                self.graph_cum[self.current_node][k + 1] = acc;
            }

            // Aprendizado Ordem-0
            self.o0_counts[symbol] += 1;
            if self.o0_counts.iter().sum::<u32>() >= 2048 {
                for s in 0..ALPHABET_SIZE {
                    self.o0_counts[s] = (self.o0_counts[s] >> 1) | 1;
                }
            }
            // Reconstrói acumulativa do Ordem-0
            let mut acc_o0 = 0;
            self.o0_cum[0] = 0;
            for k in 0..ALPHABET_SIZE {
                acc_o0 += self.o0_counts[k];
                self.o0_cum[k + 1] = acc_o0;
            }

            // Processamento secundário para MATCH
            if let Token::Match { dist, len } = token {
                // Modelo Distância
                let dist_code = if dist == self.last_offsets[0] {
                    0
                } else if dist == self.last_offsets[1] {
                    1
                } else if dist == self.last_offsets[2] {
                    2
                } else {
                    3 + bucket_dist(dist)
                };

                coder.encode(self.dist_code_cum[dist_code], self.dist_code_cum[dist_code + 1], self.dist_code_cum[DIST_CODE_SIZE], &mut writer);
                
                self.dist_code_counts[dist_code] += 1;
                if self.dist_code_counts.iter().sum::<u32>() >= 2048 {
                    for s in 0..DIST_CODE_SIZE {
                        self.dist_code_counts[s] = (self.dist_code_counts[s] >> 1) | 1;
                    }
                }
                let mut acc_dist = 0;
                self.dist_code_cum[0] = 0;
                for k in 0..DIST_CODE_SIZE {
                    acc_dist += self.dist_code_counts[k];
                    self.dist_code_cum[k + 1] = acc_dist;
                }

                if dist_code >= 3 {
                    let db = dist_code - 3;
                    let extra_bits = DIST_EXTRA[db];
                    let extra = dist - DIST_BASE[db];
                    for b in (0..extra_bits).rev() {
                        coder.encode_bit(((extra >> b) & 1) as u32, &mut writer);
                    }
                }
                mtf_offsets(&mut self.last_offsets, dist);

                // Modelo Length
                let len_code = if len == self.last_length {
                    0
                } else {
                    1 + bucket_len(len)
                };

                coder.encode(self.len_code_cum[len_code], self.len_code_cum[len_code + 1], self.len_code_cum[LEN_CODE_SIZE], &mut writer);
                
                self.len_code_counts[len_code] += 1;
                if self.len_code_counts.iter().sum::<u32>() >= 2048 {
                    for s in 0..LEN_CODE_SIZE {
                        self.len_code_counts[s] = (self.len_code_counts[s] >> 1) | 1;
                    }
                }
                let mut acc_len = 0;
                self.len_code_cum[0] = 0;
                for k in 0..LEN_CODE_SIZE {
                    acc_len += self.len_code_counts[k];
                    self.len_code_cum[k + 1] = acc_len;
                }

                if len_code >= 1 {
                    let lb = len_code - 1;
                    let extra_bits = LEN_EXTRA[lb];
                    let extra = len - LEN_BASE[lb];
                    for b in (0..extra_bits).rev() {
                        coder.encode_bit(((extra >> b) & 1) as u32, &mut writer);
                    }
                }
                self.last_length = len;
            } else if symbol != EOF_SYMBOL {
                self.current_node = ((self.current_node & 0x0F) << 4) | symbol;
            }
        }

        coder.finish(&mut writer);
        writer.bytes
    }

    pub fn decompress(&mut self, payload: Vec<u8>) -> Vec<Token> {
        let mut reader = BitReader::new(payload);
        let mut decoder = ArithmeticDecoder::new(&mut reader);
        let mut tokens = Vec::new();

        loop {
            let edges = &self.graph[self.current_node];
            let t = self.graph_totals[self.current_node];
            let symbol: usize;

            if t == 0 {
                let total = self.o0_cum[ALPHABET_SIZE];
                let target = decoder.get_target(total);
                // Busca binária rápida
                symbol = match self.o0_cum.binary_search(&target) {
                    Ok(idx) => idx,
                    Err(idx) => idx - 1,
                };
                decoder.decode(self.o0_cum[symbol], self.o0_cum[symbol + 1], total, &mut reader);
            } else {
                let adjusted = t + 1;
                let target = decoder.get_target(adjusted);

                if target == t {
                    decoder.decode(t, adjusted, adjusted, &mut reader);
                    // Exclusão PPM
                    let mut masked_total = self.o0_cum[ALPHABET_SIZE];
                    for j in 0..ALPHABET_SIZE {
                        if edges[j] > 0 {
                            masked_total -= self.o0_counts[j];
                        }
                    }
                    let target_m = decoder.get_target(masked_total);
                    let mut acc = 0;
                    let mut sym_idx = 0;
                    let mut low_s = 0;
                    let mut high_s = 0;
                    for s in 0..ALPHABET_SIZE {
                        if edges[s] > 0 {
                            continue;
                        }
                        let w = self.o0_counts[s];
                        if acc + w > target_m {
                            sym_idx = s;
                            low_s = acc;
                            high_s = acc + w;
                            break;
                        }
                        acc += w;
                    }
                    decoder.decode(low_s, high_s, masked_total, &mut reader);
                    symbol = sym_idx;
                } else {
                    let ecum = &self.graph_cum[self.current_node];
                    symbol = match ecum.binary_search(&target) {
                        Ok(idx) => idx,
                        Err(idx) => idx - 1,
                    };
                    decoder.decode(ecum[symbol], ecum[symbol + 1], adjusted, &mut reader);
                }
            }

            // Aprendizado e Reescalonamento para o nó do grafo
            let edge_x = edges[symbol];
            self.graph[self.current_node][symbol] = edge_x + 1;
            self.graph_totals[self.current_node] = t + 1;

            if self.graph_totals[self.current_node] >= 2048 {
                let mut sum_ctx = 0;
                for s in 0..ALPHABET_SIZE {
                    if self.graph[self.current_node][s] > 0 {
                        self.graph[self.current_node][s] = (self.graph[self.current_node][s] >> 1) | 1;
                        sum_ctx += self.graph[self.current_node][s];
                    }
                }
                self.graph_totals[self.current_node] = sum_ctx;
            }

            let mut acc = 0;
            self.graph_cum[self.current_node][0] = 0;
            for k in 0..ALPHABET_SIZE {
                acc += self.graph[self.current_node][k];
                self.graph_cum[self.current_node][k + 1] = acc;
            }

            // Aprendizado Ordem-0
            self.o0_counts[symbol] += 1;
            if self.o0_counts.iter().sum::<u32>() >= 2048 {
                for s in 0..ALPHABET_SIZE {
                    self.o0_counts[s] = (self.o0_counts[s] >> 1) | 1;
                }
            }
            let mut acc_o0 = 0;
            self.o0_cum[0] = 0;
            for k in 0..ALPHABET_SIZE {
                acc_o0 += self.o0_counts[k];
                self.o0_cum[k + 1] = acc_o0;
            }

            if symbol == EOF_SYMBOL {
                tokens.push(Token::EOF);
                break;
            }

            if symbol == MATCH_SYMBOL {
                // Decodifica distância
                let d_target = decoder.get_target(self.dist_code_cum[DIST_CODE_SIZE]);
                let dist_code = match self.dist_code_cum.binary_search(&d_target) {
                    Ok(idx) => idx,
                    Err(idx) => idx - 1,
                };
                decoder.decode(self.dist_code_cum[dist_code], self.dist_code_cum[dist_code + 1], self.dist_code_cum[DIST_CODE_SIZE], &mut reader);

                self.dist_code_counts[dist_code] += 1;
                if self.dist_code_counts.iter().sum::<u32>() >= 2048 {
                    for s in 0..DIST_CODE_SIZE {
                        self.dist_code_counts[s] = (self.dist_code_counts[s] >> 1) | 1;
                    }
                }
                let mut acc_dist = 0;
                self.dist_code_cum[0] = 0;
                for k in 0..DIST_CODE_SIZE {
                    acc_dist += self.dist_code_counts[k];
                    self.dist_code_cum[k + 1] = acc_dist;
                }

                let dist = if dist_code < 3 {
                    self.last_offsets[dist_code]
                } else {
                    let db = dist_code - 3;
                    let extra_bits = DIST_EXTRA[db];
                    let mut extra = 0;
                    for _ in 0..extra_bits {
                        extra = (extra << 1) | decoder.decode_bit(&mut reader) as usize;
                    }
                    DIST_BASE[db] + extra
                };
                mtf_offsets(&mut self.last_offsets, dist);

                // Decodifica comprimento
                let l_target = decoder.get_target(self.len_code_cum[LEN_CODE_SIZE]);
                let len_code = match self.len_code_cum.binary_search(&l_target) {
                    Ok(idx) => idx,
                    Err(idx) => idx - 1,
                };
                decoder.decode(self.len_code_cum[len_code], self.len_code_cum[len_code + 1], self.len_code_cum[LEN_CODE_SIZE], &mut reader);

                self.len_code_counts[len_code] += 1;
                if self.len_code_counts.iter().sum::<u32>() >= 2048 {
                    for s in 0..LEN_CODE_SIZE {
                        self.len_code_counts[s] = (self.len_code_counts[s] >> 1) | 1;
                    }
                }
                let mut acc_len = 0;
                self.len_code_cum[0] = 0;
                for k in 0..LEN_CODE_SIZE {
                    acc_len += self.len_code_counts[k];
                    self.len_code_cum[k + 1] = acc_len;
                }

                let len = if len_code == 0 {
                    self.last_length
                } else {
                    let lb = len_code - 1;
                    let extra_bits = LEN_EXTRA[lb];
                    let mut extra = 0;
                    for _ in 0..extra_bits {
                        extra = (extra << 1) | decoder.decode_bit(&mut reader) as usize;
                    }
                    LEN_BASE[lb] + extra
                };
                self.last_length = len;

                tokens.push(Token::Match { dist, len });
            } else {
                tokens.push(Token::Nibble(symbol as u8));
                self.current_node = ((self.current_node & 0x0F) << 4) | symbol;
            }
        }

        tokens
    }
}

// ============================================================================
// RECONSTRUTOR LZ77
// ============================================================================
pub fn lz77_reconstruct(tokens: &[Token]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut nibble_hi: Option<u8> = None;

    for &token in tokens {
        match token {
            Token::EOF => break,
            Token::Match { dist, len } => {
                let start = out.len() - dist;
                for k in 0..len {
                    out.push(out[start + k]);
                }
            }
            Token::Nibble(nib) => {
                if let Some(hi) = nibble_hi {
                    out.push((hi << 4) | nib);
                    nibble_hi = None;
                } else {
                    nibble_hi = Some(nib);
                }
            }
        }
    }
    out
}
