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

// v12 — flag de modo ENVIESADA (nunca inflar). Primeira decisao do stream aritmetico:
// is_stored ocupa o intervalo [FLAG_STORED_LOW, FLAG_TOTAL) = 1/64. Comprimido custa
// ~log2(64/63) ≈ 0.02 bit (quase free); stored custa ~6 bits + coding flat.
pub const FLAG_TOTAL: u16      = 64;
pub const FLAG_STORED_LOW: u16 = 63;

pub const LZ_WINDOW: usize       = 32768;  // janela "stream" (gateways/arquivos grandes) e teto maximo
pub const LZ_WINDOW_MICRO: usize = 4096;   // v10.2: janela "micro" p/ payloads <= 4 KB (RAM minima, zero perda de ratio)
pub const LZ_MIN_MATCH: usize   = 4;
pub const LZ_MAX_MATCH: usize   = 67;
pub const LZ_HASH_SIZE: usize   = 16381;
pub const LZ_HASH_MICRO: usize  = 4099;   // v12.1: hash menor p/ inputs <= 4 KB (head 64 KB -> 16 KB, sem perda de ratio)
pub const LZ_MAX_CHAIN: usize   = 128;    // v10.1: chain mais funda (era 16); sem isso a janela maior nao e varrida

pub const DIST_BUCKETS: usize = 16;
pub const DIST_BASE: [usize; 16] = [1, 2, 3, 5, 9, 17, 33, 65, 129, 257, 513, 1025, 2049, 4097, 8193, 16385];
pub const DIST_EXTRA: [u32; 16]  = [0, 0, 1, 2, 3,  4,  5,  6,   7,   8,   9,   10,   11,   12,   13,   14];

pub const LEN_BUCKETS: usize = 7;
pub const LEN_BASE: [usize; 7] = [4, 5, 6, 8, 12, 20, 36];
pub const LEN_EXTRA: [u32; 7]  = [0, 0, 1, 2,  3,  4,  5];

pub const DIST_CODE_SIZE: usize = 3 + DIST_BUCKETS; // 16
pub const LEN_CODE_SIZE: usize  = 1 + LEN_BUCKETS;  // 8

pub const ASCII_PRIOR: [u16; 18] = [
    1, 2, 2, 2, 2, 2, 2, 2,
    1, 1, 1, 1, 1, 1, 1, 1,
    1, 1,
];

// v11-primed: corpus de dominio embutido no BINARIO (nao vai no .gpa). Aquece o
// modelo PPM + serve de dicionario LZ para micro-payloads. Encoder e decoder
// usam o mesmo PRIMER, entao o arquivo continua sem dicionario embarcado.
pub const PRIMER: &[u8] = include_bytes!("primer.bin");

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

    pub fn encode(&mut self, low_count: u16, high_count: u16, total_count: u16, writer: &mut BitWriter) {
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

    pub fn encode_bit(&mut self, bit: u16, writer: &mut BitWriter) {
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

    pub fn get_target(&self, total_count: u16) -> u16 {
        let range = (self.high as u64) - (self.low as u64) + 1;
        ((((self.value as u64) - (self.low as u64) + 1) * (total_count as u64)  - 1) / range) as u16
    }

    pub fn decode(&mut self, low_count: u16, high_count: u16, total_count: u16, reader: &mut BitReader) {
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

    pub fn decode_bit(&mut self, reader: &mut BitReader) -> u16 {
        let target = self.get_target(2);
        let bit: u16 = if target >= 1 { 1 } else { 0 };
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
    // dist <= LZ_WINDOW (4096) cabe em u16; len <= LZ_MAX_MATCH (67) cabe em u8.
    // Mantém o Token compacto (~4 B vs 24 B com usize) para nao explodir RAM em
    // arquivos grandes onde o stream de tokens e materializado por completo.
    Match { dist: u16, len: u8 },
}

// ============================================================================
// LZ77 MATCH FINDER
// ============================================================================
pub struct LZ77 {
    // v10.1: posicoes em i32 (eram i16, que truncava posicoes > 32767 e quebrava
    // o match-finder em arquivos grandes).
    // v10.2: `prev` e a janela sao dimensionados em runtime (perfil micro/stream),
    // para nao alocar 128 KB de `prev` quando o payload e pequeno.
    head: Vec<i32>,
    prev: Vec<i32>,
    window: usize,
    win_mask: usize,
    hash_size: usize,
}

impl LZ77 {
    // v12.1: `head` e a janela dimensionados em runtime. Perfil micro (input <= 4 KB):
    // janela 4 KB + hash 4099 -> tabelas LZ ~32 KB. Perfil stream: 32 KB + hash 16381.
    pub fn new(window: usize, hash_size: usize) -> Self {
        debug_assert!(window.is_power_of_two(), "janela LZ deve ser potencia de 2");
        LZ77 {
            head: vec![-1i32; hash_size],
            prev: vec![-1i32; window],
            window,
            win_mask: window - 1,
            hash_size,
        }
    }

    #[inline]
    fn hash(&self, raw: &[u8], p: usize) -> usize {
        let h = ((raw[p] as usize) << 16) ^ ((raw[p + 1] as usize) << 8) ^ (raw[p + 2] as usize);
        h % self.hash_size
    }

    fn find_match(&self, raw: &[u8], i: usize, n: usize) -> (usize, usize) {
        if i + LZ_MIN_MATCH > n {
            return (0, 0);
        }
        let hv = self.hash(raw, i);
        let mut cand = self.head[hv] as isize;
        let mut best_len = 0;
        let mut best_dist = 0;
        let mut attempts = 0;
        let limit = min(LZ_MAX_MATCH, n - i);

        while cand >= 0 && (i - cand as usize) <= self.window && attempts < LZ_MAX_CHAIN {
            let c_pos = cand as usize;
            if best_len > 0 {
                if i + best_len >= n {
                    break;
                }
                // Quick filter
                if raw[c_pos + best_len] != raw[i + best_len] {
                    cand = self.prev[c_pos & self.win_mask] as isize;
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
            cand = self.prev[c_pos & self.win_mask] as isize;
            attempts += 1;
        }

        (best_len, best_dist)
    }

    fn insert_hash(&mut self, raw: &[u8], p: usize, n: usize) {
        if p + 2 >= n {
            return;
        }
        let hv = self.hash(raw, p);
        self.prev[p & self.win_mask] = self.head[hv];
        self.head[hv] = p as i32;
    }

    /// Versao STREAMING do parser: em vez de materializar um Vec<Token>, emite cada
    /// token via callback. Permite que o compressor codifique token-a-token sem nunca
    /// guardar o stream inteiro em memoria (RAM ~constante em qualquer tamanho).
    pub fn parse_streaming<F: FnMut(Token)>(&mut self, raw: &[u8], mut emit: F) {
        let n = raw.len();

        if n < LZ_MIN_MATCH + 2 {
            for &b in raw {
                emit(Token::Nibble((b >> 4) & 0x0F));
                emit(Token::Nibble(b & 0x0F));
            }
            emit(Token::EOF);
            return;
        }

        let mut i = 0;
        while i < n {
            if i + LZ_MIN_MATCH > n {
                for k in i..n {
                    emit(Token::Nibble((raw[k] >> 4) & 0x0F));
                    emit(Token::Nibble(raw[k] & 0x0F));
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
                        emit(Token::Nibble((b >> 4) & 0x0F));
                        emit(Token::Nibble(b & 0x0F));
                        i += 1;
                        continue;
                    }
                }

                emit(Token::Match { dist: cur_dist as u16, len: cur_len as u8 });
                for j in 1..cur_len {
                    self.insert_hash(raw, i + j, n);
                }
                i += cur_len;
            } else {
                let b = raw[i];
                emit(Token::Nibble((b >> 4) & 0x0F));
                emit(Token::Nibble(b & 0x0F));
                i += 1;
            }
        }

        emit(Token::EOF);
    }

    /// Como parse_streaming, mas `combined = dict ++ msg`: pre-carrega a hash com
    /// as posicoes do dicionario (0..dict_len) e SO emite tokens da mensagem
    /// (posicoes dict_len..n). Matches da msg podem referenciar o dicionario
    /// (distancias para tras, nunca cruzam a fronteira). Usado no modo primed.
    pub fn parse_with_dict<F: FnMut(Token)>(&mut self, combined: &[u8], dict_len: usize, mut emit: F) {
        let n = combined.len();
        for p in 0..dict_len {
            self.insert_hash(combined, p, n);
        }
        let mut i = dict_len;
        while i < n {
            if i + LZ_MIN_MATCH > n {
                for k in i..n {
                    emit(Token::Nibble((combined[k] >> 4) & 0x0F));
                    emit(Token::Nibble(combined[k] & 0x0F));
                }
                break;
            }
            let (cur_len, cur_dist) = self.find_match(combined, i, n);
            self.insert_hash(combined, i, n);
            if cur_len >= LZ_MIN_MATCH {
                if i + 1 < n && cur_len < LZ_MAX_MATCH {
                    let (next_len, _) = self.find_match(combined, i + 1, n);
                    if next_len > cur_len {
                        let b = combined[i];
                        emit(Token::Nibble((b >> 4) & 0x0F));
                        emit(Token::Nibble(b & 0x0F));
                        i += 1;
                        continue;
                    }
                }
                emit(Token::Match { dist: cur_dist as u16, len: cur_len as u8 });
                for j in 1..cur_len {
                    self.insert_hash(combined, i + j, n);
                }
                i += cur_len;
            } else {
                let b = combined[i];
                emit(Token::Nibble((b >> 4) & 0x0F));
                emit(Token::Nibble(b & 0x0F));
                i += 1;
            }
        }
        emit(Token::EOF);
    }
}

// ============================================================================
// GHOSTPREDICT v9 COMPRESSION/DECOMPRESSION ENGINE
// ============================================================================
pub struct GhostPredictEngine {
    // Principal PPM
    graph: Box<[[u16; ALPHABET_SIZE]; 256]>,
    graph_cum: Box<[[u16; ALPHABET_SIZE + 1]; 256]>,
    graph_totals: [u16; 256],
    o0_counts: [u16; ALPHABET_SIZE],
    o0_cum: [u16; ALPHABET_SIZE + 1],
    current_node: usize,

    // Dist Modelo
    dist_code_counts: [u16; DIST_CODE_SIZE],
    dist_code_cum: [u16; DIST_CODE_SIZE + 1],
    last_offsets: [usize; 3],

    // Len Modelo
    len_code_counts: [u16; LEN_CODE_SIZE],
    len_code_cum: [u16; LEN_CODE_SIZE + 1],
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
            dist_code_cum[i] = i as u16;
        }

        // Inicializa len_code
        let mut len_code_cum = [0; LEN_CODE_SIZE + 1];
        for i in 0..=LEN_CODE_SIZE {
            len_code_cum[i] = i as u16;
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

    /// Codifica UM token no stream aritmetico (usado pelos caminhos streaming e batch).
    pub fn encode_token(&mut self, token: Token, coder: &mut ArithmeticCoder, writer: &mut BitWriter) {
        {
            let symbol = match token {
                Token::Nibble(n) => n as usize,
                Token::EOF => EOF_SYMBOL,
                Token::Match { .. } => MATCH_SYMBOL,
            };

            let edges = &self.graph[self.current_node];
            let t = self.graph_totals[self.current_node];
            let edge_x = edges[symbol];

            if t == 0 {
                coder.encode(self.o0_cum[symbol], self.o0_cum[symbol + 1], self.o0_cum[ALPHABET_SIZE], writer);
            } else if edge_x > 0 {
                let adjusted = t + 1; // PPMA: escape weight = 1
                let ecum = &self.graph_cum[self.current_node];
                coder.encode(ecum[symbol], ecum[symbol + 1], adjusted, writer);
            } else {
                let adjusted = t + 1;
                // Encode escape at [T, T+1)
                coder.encode(t, t + 1, adjusted, writer);

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
                coder.encode(masked_low, masked_high, masked_total, writer);
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
            if self.o0_counts.iter().map(|&x| x as u32).sum::<u32>() >= 2048 {
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
                let dist = dist as usize;
                let len = len as usize;
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

                coder.encode(self.dist_code_cum[dist_code], self.dist_code_cum[dist_code + 1], self.dist_code_cum[DIST_CODE_SIZE], writer);
                
                self.dist_code_counts[dist_code] += 1;
                if self.dist_code_counts.iter().map(|&x| x as u32).sum::<u32>() >= 2048 {
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
                        coder.encode_bit(((extra >> b) & 1) as u16, writer);
                    }
                }
                mtf_offsets(&mut self.last_offsets, dist);

                // Modelo Length
                let len_code = if len == self.last_length {
                    0
                } else {
                    1 + bucket_len(len)
                };

                coder.encode(self.len_code_cum[len_code], self.len_code_cum[len_code + 1], self.len_code_cum[LEN_CODE_SIZE], writer);
                
                self.len_code_counts[len_code] += 1;
                if self.len_code_counts.iter().map(|&x| x as u32).sum::<u32>() >= 2048 {
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
                        coder.encode_bit(((extra >> b) & 1) as u16, writer);
                    }
                }
                self.last_length = len;
            } else if symbol != EOF_SYMBOL {
                self.current_node = ((self.current_node & 0x0F) << 4) | symbol;
            }
        }
    }

    /// Atualiza TODOS os modelos como encode_token, mas SEM codificar nada (sem coder).
    /// Usado para "aquecer" o modelo com o PRIMER, identico nos dois lados. Deve
    /// espelhar exatamente a parte de aprendizado de encode_token.
    pub fn learn_token(&mut self, token: Token) {
        let symbol = match token {
            Token::Nibble(n) => n as usize,
            Token::EOF => EOF_SYMBOL,
            Token::Match { .. } => MATCH_SYMBOL,
        };
        let node = self.current_node;
        let t = self.graph_totals[node];
        let edge_x = self.graph[node][symbol];

        self.graph[node][symbol] = edge_x + 1;
        self.graph_totals[node] = t + 1;
        if self.graph_totals[node] >= 2048 {
            let mut sum_ctx = 0;
            for s in 0..ALPHABET_SIZE {
                if self.graph[node][s] > 0 {
                    self.graph[node][s] = (self.graph[node][s] >> 1) | 1;
                    sum_ctx += self.graph[node][s];
                }
            }
            self.graph_totals[node] = sum_ctx;
        }
        let mut acc = 0;
        self.graph_cum[node][0] = 0;
        for k in 0..ALPHABET_SIZE {
            acc += self.graph[node][k];
            self.graph_cum[node][k + 1] = acc;
        }

        self.o0_counts[symbol] += 1;
        if self.o0_counts.iter().map(|&x| x as u32).sum::<u32>() >= 2048 {
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

        if let Token::Match { dist, len } = token {
            let dist = dist as usize;
            let len = len as usize;
            let dist_code = if dist == self.last_offsets[0] {
                0
            } else if dist == self.last_offsets[1] {
                1
            } else if dist == self.last_offsets[2] {
                2
            } else {
                3 + bucket_dist(dist)
            };
            self.dist_code_counts[dist_code] += 1;
            if self.dist_code_counts.iter().map(|&x| x as u32).sum::<u32>() >= 2048 {
                for s in 0..DIST_CODE_SIZE {
                    self.dist_code_counts[s] = (self.dist_code_counts[s] >> 1) | 1;
                }
            }
            let mut ad = 0;
            self.dist_code_cum[0] = 0;
            for k in 0..DIST_CODE_SIZE {
                ad += self.dist_code_counts[k];
                self.dist_code_cum[k + 1] = ad;
            }
            mtf_offsets(&mut self.last_offsets, dist);

            let len_code = if len == self.last_length {
                0
            } else {
                1 + bucket_len(len)
            };
            self.len_code_counts[len_code] += 1;
            if self.len_code_counts.iter().map(|&x| x as u32).sum::<u32>() >= 2048 {
                for s in 0..LEN_CODE_SIZE {
                    self.len_code_counts[s] = (self.len_code_counts[s] >> 1) | 1;
                }
            }
            let mut al = 0;
            self.len_code_cum[0] = 0;
            for k in 0..LEN_CODE_SIZE {
                al += self.len_code_counts[k];
                self.len_code_cum[k + 1] = al;
            }
            self.last_length = len;
        } else if symbol != EOF_SYMBOL {
            self.current_node = ((self.current_node & 0x0F) << 4) | symbol;
        }
    }

    /// Aquece o modelo (PPM + dist/len) com o PRIMER, sem codificar. Identico
    /// nos dois lados. Pula o EOF (o primer nao e um stream completo).
    fn prime_model(&mut self, primer: &[u8]) {
        let mut lz = LZ77::new(LZ_WINDOW, LZ_HASH_SIZE);
        let mut toks: Vec<Token> = Vec::new();
        lz.parse_streaming(primer, |t| toks.push(t));
        for t in toks {
            if !matches!(t, Token::EOF) {
                self.learn_token(t);
            }
        }
    }

    /// COMPRESSAO PRIMED: aquece o modelo com o primer e usa o primer como
    /// dicionario LZ; o .gpa contem apenas a mensagem codificada (primer fica
    /// no codec, nao no arquivo).
    pub fn compress_primed(&mut self, raw: &[u8], primer: &[u8]) -> Vec<u8> {
        self.prime_model(primer);
        let mut combined = Vec::with_capacity(primer.len() + raw.len());
        combined.extend_from_slice(primer);
        combined.extend_from_slice(raw);
        let mut writer = BitWriter::new();
        let mut coder = ArithmeticCoder::new();
        let mut lz = LZ77::new(LZ_WINDOW, LZ_HASH_SIZE);
        lz.parse_with_dict(&combined, primer.len(), |tok| self.encode_token(tok, &mut coder, &mut writer));
        coder.finish(&mut writer);
        writer.bytes
    }

    /// DESCOMPRESSAO PRIMED: aquece o modelo identicamente e reconstroi a mensagem
    /// num buffer prefixado pelo primer (para os matches no dicionario funcionarem).
    pub fn decompress_primed(&mut self, payload: Vec<u8>, primer: &[u8]) -> Vec<u8> {
        self.prime_model(primer);
        if payload.is_empty() {
            return Vec::new();
        }
        let plen = primer.len();
        let mut reader = BitReader::new(payload);
        let mut decoder = ArithmeticDecoder::new(&mut reader);
        let mut out: Vec<u8> = primer.to_vec();
        let mut nibble_hi: Option<u8> = None;
        loop {
            let symbol = self.decode_symbol(&mut decoder, &mut reader);
            if symbol == EOF_SYMBOL {
                break;
            }
            if symbol == MATCH_SYMBOL {
                let (dist, len) = self.decode_match(&mut decoder, &mut reader);
                let start = out.len() - dist;
                for k in 0..len {
                    out.push(out[start + k]);
                }
            } else {
                if let Some(hi) = nibble_hi {
                    out.push((hi << 4) | symbol as u8);
                    nibble_hi = None;
                } else {
                    nibble_hi = Some(symbol as u8);
                }
                self.current_node = ((self.current_node & 0x0F) << 4) | symbol;
            }
        }
        out[plen..].to_vec()
    }

    /// Caminho STREAMING: parsing LZ + codificacao token-a-token, sem materializar
    /// o Vec<Token>. Formato ZERO-OVERHEAD (sem header/flag) — o .gpa e puramente o
    /// stream aritmetico, como no v9. Otimizado para o nicho de micro-payloads
    /// compressiveis; dados incompressiveis (ruido) podem inflar (teto de Shannon).
    pub fn compress_stream(&mut self, raw: &[u8]) -> Vec<u8> {
        // Caminho COMPRIMIDO: flag enviesada (is_stored=0, ~0.02 bit) + stream LZ/PPM.
        let mut writer = BitWriter::new();
        let mut coder = ArithmeticCoder::new();
        coder.encode(0, FLAG_STORED_LOW, FLAG_TOTAL, &mut writer); // is_stored = 0
        // Auto-seleciona o PERFIL pelo tamanho do input:
        //  - micro (<= 4 KB): janela 4 KB + hash 4099 -> tabelas LZ ~32 KB (compressor-MCU);
        //  - stream (> 4 KB):  janela 32 KB + hash 16381 -> longo alcance.
        // Sem perda de ratio no micro (poucas posicoes p/ a hash) e seguro em qualquer tamanho.
        let (window, hash_size) = if raw.len() <= LZ_WINDOW_MICRO {
            (LZ_WINDOW_MICRO, LZ_HASH_MICRO)
        } else {
            (LZ_WINDOW, LZ_HASH_SIZE)
        };
        let mut lz = LZ77::new(window, hash_size);
        lz.parse_streaming(raw, |tok| self.encode_token(tok, &mut coder, &mut writer));
        coder.finish(&mut writer);
        let comp = writer.bytes;
        if comp.len() <= raw.len() + 1 {
            return comp;
        }
        // INFLOU -> STORED: flag is_stored=1 + bytes em modelo flat (257) + EOF. Saida ~raw+3,
        // garantindo que dados incompressiveis nunca inflam de forma relevante.
        let mut w2 = BitWriter::new();
        let mut c2 = ArithmeticCoder::new();
        c2.encode(FLAG_STORED_LOW, FLAG_TOTAL, FLAG_TOTAL, &mut w2); // is_stored = 1
        for &b in raw {
            c2.encode(b as u16, b as u16 + 1, 257, &mut w2);
        }
        c2.encode(256, 257, 257, &mut w2); // EOF do fluxo flat
        c2.finish(&mut w2);
        let stored = w2.bytes;
        if stored.len() < comp.len() { stored } else { comp }
    }

    /// Decodifica UM simbolo principal (PPM) + atualiza modelos. Compartilhado pelos
    /// caminhos batch e streaming. NAO atualiza current_node (cabe ao chamador).
    fn decode_symbol(&mut self, decoder: &mut ArithmeticDecoder, reader: &mut BitReader) -> usize {
        let edges = &self.graph[self.current_node];
        let t = self.graph_totals[self.current_node];
        let symbol: usize;

        if t == 0 {
            let total = self.o0_cum[ALPHABET_SIZE];
            let target = decoder.get_target(total);
            symbol = match self.o0_cum.binary_search(&target) {
                Ok(idx) => idx,
                Err(idx) => idx - 1,
            };
            decoder.decode(self.o0_cum[symbol], self.o0_cum[symbol + 1], total, reader);
        } else {
            let adjusted = t + 1;
            let target = decoder.get_target(adjusted);

            if target == t {
                decoder.decode(t, adjusted, adjusted, reader);
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
                decoder.decode(low_s, high_s, masked_total, reader);
                symbol = sym_idx;
            } else {
                let ecum = &self.graph_cum[self.current_node];
                symbol = match ecum.binary_search(&target) {
                    Ok(idx) => idx,
                    Err(idx) => idx - 1,
                };
                decoder.decode(ecum[symbol], ecum[symbol + 1], adjusted, reader);
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
        if self.o0_counts.iter().map(|&x| x as u32).sum::<u32>() >= 2048 {
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

        symbol
    }

    /// Decodifica dist + len de um MATCH (modelos auxiliares Dist/Len).
    fn decode_match(&mut self, decoder: &mut ArithmeticDecoder, reader: &mut BitReader) -> (usize, usize) {
        let d_target = decoder.get_target(self.dist_code_cum[DIST_CODE_SIZE]);
        let dist_code = match self.dist_code_cum.binary_search(&d_target) {
            Ok(idx) => idx,
            Err(idx) => idx - 1,
        };
        decoder.decode(self.dist_code_cum[dist_code], self.dist_code_cum[dist_code + 1], self.dist_code_cum[DIST_CODE_SIZE], reader);

        self.dist_code_counts[dist_code] += 1;
        if self.dist_code_counts.iter().map(|&x| x as u32).sum::<u32>() >= 2048 {
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
                extra = (extra << 1) | decoder.decode_bit(reader) as usize;
            }
            DIST_BASE[db] + extra
        };
        mtf_offsets(&mut self.last_offsets, dist);

        let l_target = decoder.get_target(self.len_code_cum[LEN_CODE_SIZE]);
        let len_code = match self.len_code_cum.binary_search(&l_target) {
            Ok(idx) => idx,
            Err(idx) => idx - 1,
        };
        decoder.decode(self.len_code_cum[len_code], self.len_code_cum[len_code + 1], self.len_code_cum[LEN_CODE_SIZE], reader);

        self.len_code_counts[len_code] += 1;
        if self.len_code_counts.iter().map(|&x| x as u32).sum::<u32>() >= 2048 {
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
                extra = (extra << 1) | decoder.decode_bit(reader) as usize;
            }
            LEN_BASE[lb] + extra
        };
        self.last_length = len;
        (dist, len)
    }

    /// Caminho STREAMING: decodifica o stream aritmetico e reconstroi o fluxo LZ77
    /// INLINE (sem materializar Vec<Token>). RAM ~constante no descompressor.
    pub fn decompress_stream(&mut self, payload: Vec<u8>) -> Vec<u8> {
        if payload.is_empty() {
            return Vec::new();
        }
        let mut reader = BitReader::new(payload);
        let mut decoder = ArithmeticDecoder::new(&mut reader);

        // Le a flag de modo enviesada.
        if decoder.get_target(FLAG_TOTAL) >= FLAG_STORED_LOW {
            decoder.decode(FLAG_STORED_LOW, FLAG_TOTAL, FLAG_TOTAL, &mut reader); // STORED
            let mut out: Vec<u8> = Vec::new();
            loop {
                let t = decoder.get_target(257);
                if t == 256 {
                    decoder.decode(256, 257, 257, &mut reader);
                    break;
                }
                decoder.decode(t, t + 1, 257, &mut reader);
                out.push(t as u8);
            }
            return out;
        }
        decoder.decode(0, FLAG_STORED_LOW, FLAG_TOTAL, &mut reader); // COMPRIMIDO

        let mut out: Vec<u8> = Vec::new();
        let mut nibble_hi: Option<u8> = None;

        loop {
            let symbol = self.decode_symbol(&mut decoder, &mut reader);
            if symbol == EOF_SYMBOL {
                break;
            }
            if symbol == MATCH_SYMBOL {
                let (dist, len) = self.decode_match(&mut decoder, &mut reader);
                let start = out.len() - dist;
                for k in 0..len {
                    out.push(out[start + k]);
                }
            } else {
                if let Some(hi) = nibble_hi {
                    out.push((hi << 4) | symbol as u8);
                    nibble_hi = None;
                } else {
                    nibble_hi = Some(symbol as u8);
                }
                self.current_node = ((self.current_node & 0x0F) << 4) | symbol;
            }
        }

        out
    }
}
