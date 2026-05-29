# GhostPredict v10 — Especificação Algorítmica

Compressor lossless de **overhead mínimo (1 bit)** otimizado para payloads pequenos (< 4 KB). Esta especificação descreve o algoritmo de forma independente de linguagem — qualquer implementação que respeite as regras aqui produzirá streams `.gpa` bit-exatos compatíveis entre si.

> **Mudanças do v10 em relação ao v9:** (1) um **bit de flag de modo** prefixa o stream (0 = comprimido, 1 = stored); (2) **modo stored** grava os bytes crus quando a compressão inflaria, garantindo inflação máxima de **+1 byte**; (3) o pipeline de referência é **streaming** (não materializa o stream de tokens), mantendo RAM ~constante. O núcleo estatístico (LZ77 + PPM-D + aritmético) é idêntico ao v9.

---

## 1. Escopo

| Critério | Valor |
|---|---|
| Tipo | Lossless, 1-pass, adaptativo |
| Alvo primário | Payloads de 32 B a 4 KB (IoT, MQTT, CoAP, HTTP, telemetria) |
| Overhead de cabeçalho | **1 bit** (flag de modo; nenhuma tabela, magic ou metadado) |
| Inflação máxima garantida | **+1 byte** (via modo stored) |
| Determinismo | Bit-exato em qualquer arquitetura (aritmética inteira) |
| Memória de trabalho típica | ~37 KB (grafo PPM) + buffers de E/S; ~constante para payloads pequenos |
| Limite mínimo eficiente | ~13 B (abaixo disso o overhead aritmético/flag infla até 1 B) |

---

## 2. Pipeline

```
bytes brutos
    │
    ▼  Pré-pass LZ77 (janela 4 KB, lazy match, hash chain)
token stream  ──  alfabeto unificado de 18 símbolos + tuplas (dist, len) para matches
    │
    ▼  Modelagem estatística adaptativa
três modelos probabilísticos paralelos:
  • PPM Ordem-2 sobre nibbles (símbolo principal)
  • Modelo Dist-Code (3 slots de offset history + 13 buckets logarítmicos)
  • Modelo Len-Code (1 slot de last-length + 7 buckets logarítmicos)
    │
    ▼  Codificador aritmético inteiro de 32 bits (probabilidades guiam intervalos)
fluxo de bits
    │
    ▼  Padding com zeros até múltiplo de 8
stream aritmético (precedido por 1 bit de flag = 0)
    │
    ▼  Decisão de modo: se |comprimido| > |original| + 1, descarta e usa STORED
arquivo .gpa (flag + stream comprimido  OU  0x80 + bytes crus)
```

A descompressão é exatamente o espelho: lê o bit de flag; se for 1, devolve os bytes crus; se for 0, decodifica símbolos com modelos sincronizados e expande tokens com LZ77 reverso. O pipeline de referência processa tokens em **streaming** (emite/consome um token por vez, sem acumular o stream completo em memória).

---

## 3. Constantes Fundamentais

Toda implementação **deve** usar exatamente estes valores.

### 3.1 Codificador aritmético

| Símbolo | Valor (hex) |
|---|---|
| `MAX_VALUE` | `0xFFFFFFFF` |
| `HALF` | `0x80000000` |
| `Q1` | `0x40000000` |
| `Q3` | `0xC0000000` |

### 3.2 Alfabeto principal

| Símbolo | Índice |
|---|---|
| Nibbles | 0 — 15 |
| `EOF` | 16 |
| `MATCH` | 17 |
| `ALPHABET_SIZE` | 18 |

### 3.3 LZ77

| Parâmetro | Valor (v10.1) | Valor (v9/v10) |
|---|---|---|
| `LZ_WINDOW` | **32768** | 4096 |
| `LZ_WIN_MASK` | **32767** | 4095 |
| `LZ_MIN_MATCH` | 4 | 4 |
| `LZ_MAX_MATCH` | 67 | 67 |
| `LZ_HASH_SIZE` | 16381 (primo) | 16381 |
| `LZ_MAX_CHAIN` | **128** | 16 |

> **v10.1:** as posições da hash-chain (`head`/`prev`) passaram de `i16` para `i32` — em `i16` qualquer posição > 32767 truncava, quebrando o match-finder em arquivos grandes. Com `i32` + janela 32 KB + chain mais funda, o LZ passa a casar repetições de longo alcance (streams). É uma mudança só do **codificador**: o decodificador reconstrói a partir das distâncias codificadas e não tem janela. Custo: tabelas LZ do codificador ~192 KB (não afeta a RAM de decodificação).

### 3.4 Buckets de distância (modelo Dist)

```
v10.1 (cobre dist até 32768):
DIST_BUCKETS = 16
DIST_BASE   = [1, 2, 3, 5, 9, 17, 33, 65, 129, 257, 513, 1025, 2049, 4097, 8193, 16385]
DIST_EXTRA  = [0, 0, 1, 2, 3,  4,  5,  6,   7,   8,   9,   10,   11,   12,   13,   14]

v9/v10 (cobria dist até 4096):
DIST_BUCKETS = 13
DIST_BASE   = [1, 2, 3, 5, 9, 17, 33, 65, 129, 257, 513, 1025, 2049]
DIST_EXTRA  = [0, 0, 1, 2, 3,  4,  5,  6,   7,   8,   9,   10,   11]
```

Bucket `b` cobre `dist ∈ [DIST_BASE[b], DIST_BASE[b] + 2^DIST_EXTRA[b] − 1]`. Os bits extras são emitidos crus após o índice do bucket.

### 3.5 Buckets de length (modelo Len)

```
LEN_BUCKETS = 7
LEN_BASE  = [4, 5, 6, 8, 12, 20, 36]
LEN_EXTRA = [0, 0, 1, 2,  3,  4,  5]
```

### 3.6 Alfabetos dos modelos auxiliares

| Modelo | Tamanho | Layout |
|---|---|---|
| `DIST_CODE_SIZE` | 19 (v10.1; era 16) | índices 0–2 = REP0/REP1/REP2; 3+ = bucket novo (3–18 em v10.1) |
| `LEN_CODE_SIZE` | 8 | índice 0 = REP (igual ao último length); 1–7 = bucket novo |

### 3.7 Prior ASCII (modelo Ordem-0 principal)

```
ASCII_PRIOR = [1, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
                ^---- nibbles ----^  ^------ resto ------^ EOF MATCH
```

Justificativa: nibbles 1–7 são frequentes em bytes ASCII de texto/JSON. Soma = 25.

---

## 4. Codificador Aritmético Inteiro

### 4.1 Estado

```
low          ← 0
high         ← MAX_VALUE
pending_bits ← 0
output       ← stream de bits vazio
```

### 4.2 Operação `encode(low_count, high_count, total_count)`

```
range  ← high − low + 1
high   ← low + (range × high_count) / total_count − 1
low    ← low + (range × low_count)  / total_count

repete:
    se high < HALF:                emit(0)
    senão se low ≥ HALF:           emit(1); low −= HALF; high −= HALF
    senão se low ≥ Q1 e high < Q3: pending_bits += 1; low −= Q1; high −= Q1
    senão: pare
    low  ← (low << 1) ∧ MAX_VALUE
    high ← ((high << 1) | 1) ∧ MAX_VALUE
```

Todas as divisões são **truncadas para o piso** (operação inteira).

### 4.3 Emissão de bit (com bits pendentes)

```
emit(bit):
    output.append(bit)
    para cada um dos pending_bits:
        output.append(bit ⊕ 1)
    pending_bits ← 0
```

### 4.4 Bit cru

`encode_bit(b) ≡ encode(b, b+1, 2)`. Equivale a 1 bit de probabilidade ½.

### 4.5 Finalização

```
pending_bits += 1
se low < Q1: emit(0)
senão:        emit(1)
```

### 4.6 Decodificador

O decodificador mantém `low`, `high`, `value` (32 bits cada). Inicializa `value` lendo 32 bits do stream. Para decodificar:

```
get_target(total):
    range ← high − low + 1
    retorne ((value − low + 1) × total − 1) / range

decode(low_count, high_count, total):
    [mesmo cálculo de high/low que o encoder]
    repete:
        se high < HALF:                (sem ação)
        senão se low ≥ HALF:           low −= HALF; high −= HALF; value −= HALF
        senão se low ≥ Q1 e high < Q3: low −= Q1; high −= Q1; value −= Q1
        senão: pare
        low   ← (low << 1) ∧ MAX_VALUE
        high  ← ((high << 1) | 1) ∧ MAX_VALUE
        value ← ((value << 1) | read_bit()) ∧ MAX_VALUE
```

Quando o stream acaba, `read_bit()` retorna 0.

---

## 5. Pré-pass LZ77

### 5.1 Hash table

```
head[LZ_HASH_SIZE]      // último índice com hash h
prev[LZ_WINDOW]         // chain: prev[p ∧ LZ_WIN_MASK] = posição anterior com mesma hash
```

Inicialmente todos `head[i] = prev[i] = -1`.

### 5.2 Função hash (3 bytes)

```
h(p) = ((raw[p] << 16) ⊕ (raw[p+1] << 8) ⊕ raw[p+2]) mod LZ_HASH_SIZE
```

### 5.3 Busca de match em posição `i`

```
find_match(i):
    se i + LZ_MIN_MATCH > n: retorne (0, 0)
    hv ← h(i)
    cand ← head[hv]
    best_len ← 0; best_dist ← 0; attempts ← 0
    limit ← min(LZ_MAX_MATCH, n − i)

    enquanto cand ≥ 0 e (i − cand) ≤ LZ_WINDOW e attempts < LZ_MAX_CHAIN:
        // Quick filter: rejeita se posição limite não bate
        se best_len > 0:
            se i + best_len ≥ n: pare
            se raw[cand + best_len] ≠ raw[i + best_len]:
                cand ← prev[cand ∧ LZ_WIN_MASK]; attempts += 1; continue

        // Extensão exaustiva
        l ← 0
        enquanto l < limit e raw[cand + l] = raw[i + l]: l += 1
        se l > best_len e l ≥ LZ_MIN_MATCH:
            best_len ← l; best_dist ← i − cand
            se l ≥ limit: pare

        cand ← prev[cand ∧ LZ_WIN_MASK]; attempts += 1

    retorne (best_len, best_dist)
```

### 5.4 Inserção na hash table

```
insert_hash(p):
    se p + 2 ≥ n: retorne
    hv ← h(p)
    prev[p ∧ LZ_WIN_MASK] ← head[hv]
    head[hv] ← p
```

### 5.5 Loop principal com lazy matching

```
i ← 0
enquanto i < n:
    se i + LZ_MIN_MATCH > n:
        // emite literais restantes
        para k = i até n − 1:
            emit_literal_byte(raw[k])
        pare

    (cur_len, cur_dist) ← find_match(i)
    insert_hash(i)

    se cur_len ≥ LZ_MIN_MATCH:
        // Lazy: testa match em i+1
        se i + 1 < n e cur_len < LZ_MAX_MATCH:
            (next_len, _) ← find_match(i + 1)
            se next_len > cur_len:
                emit_literal_byte(raw[i])
                i += 1
                continue

        emit_match(cur_dist, cur_len)
        para j = 1 até cur_len − 1: insert_hash(i + j)
        i += cur_len
    senão:
        emit_literal_byte(raw[i])
        i += 1

emit_token(EOF)
```

### 5.6 Emissão de literal (byte → 2 nibbles)

```
emit_literal_byte(b):
    emit_token((b >> 4) ∧ 0x0F)   // nibble alto
    emit_token(b ∧ 0x0F)           // nibble baixo
```

### 5.7 Emissão de match (token MATCH + dist + len)

```
emit_match(dist, len):
    emit_token(MATCH)        // = 17
    emit_token(dist)         // 1 ≤ dist ≤ LZ_WINDOW
    emit_token(len)          // LZ_MIN_MATCH ≤ len ≤ LZ_MAX_MATCH
```

Estes três tokens são lidos juntos pelo codificador: o `MATCH` vai pelo modelo principal, `dist` e `len` pelos modelos auxiliares (§7).

---

## 6. Stream de Tokens

O stream produzido pelo LZ77 é uma sequência de inteiros com a convenção:

| Token | Significado |
|---|---|
| 0 – 15 | nibble literal |
| 16 (`EOF`) | fim do stream — última posição |
| 17 (`MATCH`) | indica que os **dois inteiros seguintes** são `dist` e `len` |

O LZ77 sempre emite literais em pares (nibble alto, nibble baixo) e matches em fronteiras de byte — isto é, **um MATCH nunca aparece com um nibble pendente**. Implementações podem assumir esse invariante.

---

## 7. Modelos Probabilísticos

Três modelos rodam em paralelo no mesmo stream aritmético.

### 7.1 Modelo Principal (PPM Ordem-2 nibble)

**Estado:**

```
graph[256][18]    // contadores graph[contexto][símbolo]
graph_totals[256] // soma dos contadores por contexto
o0_counts[18]     // contadores Ordem-0
                  // inicialização: o0_counts ← ASCII_PRIOR (§3.7)
current_node ∈ [0, 255]   // contexto de 2 nibbles (8 bits)
                          // inicialização: current_node ← 0
```

Todos os tabelas cumulativas (`o0_cum`, `graph_cum`) são mantidas incrementalmente para evitar reconstrução.

**Codificação do símbolo `X` no contexto `S`:**

Seja `T = graph_totals[S]`, `edges = graph[S]`.

```
caso A — Nó virgem (T = 0):
    codifica X usando Ordem-0:
        encode(o0_cum[X], o0_cum[X+1], o0_cum[18])

caso B — Hit no grafo (T > 0 e edges[X] > 0):
    adjusted ← T + 1   // PPMA: 1 ponto reservado para escape
    encode(graph_cum[S][X], graph_cum[S][X+1], adjusted)

caso C — Escape (T > 0 e edges[X] = 0):
    // emite escape (intervalo [T, T+1))
    encode(T, T+1, T+1)
    // PPM com Máscara de Exclusão: codifica X via Ordem-0 mascarada
    masked_total ← o0_cum[18]
    masked_low   ← o0_cum[X]
    para j = 0 até 17:
        se edges[j] > 0:
            masked_total −= o0_counts[j]
            se j < X: masked_low −= o0_counts[j]
    masked_high ← masked_low + o0_counts[X]
    encode(masked_low, masked_high, masked_total)
```

**Aprendizado (sempre executado após codificar/decodificar X):**

```
graph[S][X]      += 1
graph_totals[S]  += 1
para k = X+1 até 18: graph_cum[S][k] += 1

o0_counts[X] += 1
para k = X+1 até 18: o0_cum[k] += 1
```

**Atualização de `current_node`:**

```
se X = MATCH:
    current_node não muda  (ver §7.4 sobre matches)
senão se X = EOF:
    current_node não muda
senão:
    current_node ← ((current_node ∧ 0x0F) << 4) | X
```

### 7.2 Modelo Dist-Code (Offset History + Buckets)

**Estado:**

```
dist_code_counts[16] ← [1] × 16     // Laplace plano
dist_code_cum[17]                    // cumulativo
last_offsets[3] ← [0, 0, 0]          // 3 últimos dists vistos (MTF)
```

**Codificação de um `dist` (1 ≤ dist ≤ LZ_WINDOW):**

```
se dist = last_offsets[0]: code ← 0      // REP0
senão se dist = last_offsets[1]: code ← 1  // REP1
senão se dist = last_offsets[2]: code ← 2  // REP2
senão:
    bucket ← _bucket_dist(dist)
    code   ← 3 + bucket                  // NEW

// Codifica code no PPM ordem-0 dist
encode(dist_code_cum[code], dist_code_cum[code+1], dist_code_cum[16])

// Aprende
dist_code_counts[code] += 1
para k = code+1 até 16: dist_code_cum[k] += 1

// Se NEW, emite bits extras crus para refinar dentro do bucket
se code ≥ 3:
    bucket    ← code − 3
    extra_bits ← DIST_EXTRA[bucket]
    extra      ← dist − DIST_BASE[bucket]
    para b = extra_bits − 1 até 0 (decrescente):
        encode_bit((extra >> b) ∧ 1)

// Atualiza offset history (MTF)
mtf_offsets(last_offsets, dist)
```

**MTF (Move-To-Front):**

```
mtf_offsets(arr, value):
    se value está em arr:
        idx ← arr.index(value)
        se idx > 0:
            arr.remove em idx
            arr.insert(0, value)
    senão:
        arr.pop_last()
        arr.insert(0, value)
```

**Função `_bucket_dist`:**

```
_bucket_dist(d):
    para i = 12 até 0 (decrescente):
        se d ≥ DIST_BASE[i]: retorne i
    retorne 0
```

### 7.3 Modelo Len-Code (Last-Length + Buckets)

**Estado:**

```
len_code_counts[8] ← [1] × 8
len_code_cum[9]
last_length ← 0
```

**Codificação de um `length` (LZ_MIN_MATCH ≤ length ≤ LZ_MAX_MATCH):**

```
se length = last_length:
    code ← 0                          // REP
senão:
    bucket ← _bucket_len(length)
    code   ← 1 + bucket               // NEW

encode(len_code_cum[code], len_code_cum[code+1], len_code_cum[8])

// Aprende
len_code_counts[code] += 1
para k = code+1 até 8: len_code_cum[k] += 1

// Se NEW, bits extras crus
se code ≥ 1:
    bucket    ← code − 1
    extra_bits ← LEN_EXTRA[bucket]
    extra      ← length − LEN_BASE[bucket]
    para b = extra_bits − 1 até 0 (decrescente):
        encode_bit((extra >> b) ∧ 1)

last_length ← length
```

### 7.4 Comportamento em torno de MATCH e EOF

Quando o token corrente é `MATCH`:

1. Codifica símbolo `MATCH` no modelo principal (§7.1).
2. Atualiza modelo principal (aprende `MATCH` em contexto `S`).
3. Codifica `dist` no modelo Dist-Code (§7.2).
4. Codifica `length` no modelo Len-Code (§7.3).
5. **`current_node` NÃO é atualizado** (contexto permanece o anterior ao MATCH).
6. Próximo token é processado com `current_node` inalterado.

Quando o token corrente é `EOF`:

1. Codifica símbolo `EOF` no modelo principal.
2. Atualiza modelo principal.
3. Encoder chama `finish()`. Compressão termina.

---

## 8. Pipeline Completo (Compressor)

```
1. Lê bytes brutos
2. Inicializa modelos e codificador aritmético
3. Emite o bit de flag de modo = 0 (comprimido)
4. Em streaming, para cada token produzido pelo lz77_parse (§5.5):
   a. Codifica símbolo principal (§7.1)
   b. Se for MATCH: codifica dist (§7.2), depois length (§7.3)
   c. Atualiza estado (§7.1 aprendizado + shift de current_node)
5. encoder.finish() → bitstream; padding até múltiplo de 8 bits → `comp`
6. Decisão de modo (nunca inflar):
   se len(comp) ≤ len(original) + 1:  saída ← comp
   senão:                              saída ← [0x80] ++ bytes_originais  (STORED)
7. Escreve a saída → arquivo .gpa
```

O parser LZ77 **não** precisa materializar o stream de tokens: ele pode emitir cada token via callback consumido imediatamente pelo codificador (mesmo resultado bit-exato, RAM menor).

## 9. Pipeline Completo (Descompressor)

```
1. Lê bytes do .gpa
2. Lê o bit de flag (MSB do 1º byte):
   se flag = 1:  raw ← bytes[1..]  (STORED — devolve cru); FIM.
3. (flag = 0) Inicializa modelos (idênticos ao compressor) e decodificador,
   começando a leitura de bits APÓS o bit de flag
4. Loop:
   a. Decodifica símbolo principal:
      - Se T = 0: usa o0_cum
      - Senão: lê target, se target = T é escape, senão é hit
   b. Se símbolo = EOF: pare
   c. Se símbolo = MATCH: decodifica dist e length, copia do histórico (LZ77 reverso)
   d. Senão: monta byte a partir dos nibbles (par alto/baixo)
   e. Atualiza estado idêntico ao compressor
5. Escreve raw
```

A reconstrução LZ77 é feita **inline** no loop (sem materializar o stream de tokens).

### Reconstrução LZ77

```
lz77_reconstruct(tokens):
    out ← bytearray vazio
    nibble_hi ← None
    para sym em tokens:
        se sym = EOF: pare
        se sym = MATCH:
            dist ← próximo token
            len  ← próximo token
            start ← len(out) − dist
            // Pode sobrepor (RLE-like) — copia byte a byte
            para k = 0 até len − 1:
                out.append(out[start + k])
        senão:
            se nibble_hi é None:
                nibble_hi ← sym
            senão:
                out.append((nibble_hi << 4) | sym)
                nibble_hi ← None
    retorne bytes(out)
```

---

## 10. Formato do Arquivo `.gpa`

O primeiro **bit** (MSB do primeiro byte, pois o bitstream é MSB-first) é a flag de modo:

```
Modo COMPRIMIDO (flag = 0):
┌───┬─────────────────────────────┐
│ 0 │ stream aritmético           │   ← flag + bits do coder,
│   │ (padded até múltiplo de 8)  │     padded com zeros ao final
└───┴─────────────────────────────┘

Modo STORED (flag = 1):
┌──────┬──────────────────────────┐
│ 0x80 │ bytes originais crus     │   ← 1º byte = 1000_0000, resto = raw
└──────┴──────────────────────────┘
```

- **Header de 1 bit** (a flag de modo). Nenhum magic, tabela ou metadado.
- **Sem trailer. Sem checksum. Sem tabela de frequências.**
- No modo comprimido, o fim lógico é determinado pelo símbolo `EOF` decodificado, não pelo tamanho do arquivo.
- No modo stored, o tamanho do arquivo determina o fim (`raw = bytes[1..]`).
- **Garantia:** a saída nunca excede `tamanho_original + 1` byte.

---

## 11. Garantias Matemáticas

1. **Determinismo:** todas as operações são aritmética inteira sobre `uint32_t`. Não há ponto flutuante. Não há dependência de ordem de avaliação não determinística.
2. **Sincronização compressor/descompressor:** os modelos são inicializados identicamente e atualizados na mesma ordem após cada símbolo. A `Máscara de Exclusão` é recomputada determinística em ambos os lados.
3. **Lossless:** o LZ77 com `dist ≤ posição_atual` e o PPM com aprendizado pós-codificação garantem reconstrução perfeita.
4. **Tamanho mínimo:** para input vazio, o bitstream contém apenas o EOF codificado em Ordem-0, resultando em ~1 byte.

---

## 12. Considerações de Implementação

### 12.1 Estruturas eficientes

| Estrutura | Tamanho |
|---|---|
| `o0_counts`, `o0_cum` | 18 + 19 = 37 × 4 B = 148 B |
| `graph` | 256 × 18 × 4 B = 18 KB |
| `graph_cum` | 256 × 19 × 4 B = 19 KB |
| `graph_totals` | 256 × 4 B = 1 KB |
| `dist_code_*`, `len_code_*` | < 200 B |
| `last_offsets`, `last_length` | 16 B |
| LZ77 `head` | 16381 × 4 B = 64 KB |
| LZ77 `prev` | 4096 × 4 B = 16 KB |
| **Total compressor** | ~120 KB |

O descompressor não precisa do `head`/`prev` da LZ77 (só recebe matches já decididos), então usa ~40 KB.

### 12.2 Otimizações sugeridas para Rust/C

- **Bitstream packing direto:** em vez de construir uma string de bits e empacotar no final, manter um `u64` accumulator e flush a cada 8 bits cheios.
- **Cumulativos em `[u32; 19]`** stack-allocated, atualizáveis via SIMD (AVX2 paralel-add no sufixo).
- **Hash table sem ponteiros:** índices `u16` para `prev` (já cabem em 4 KB).
- **`bisect_right` sobre `cum`** em alfabetos pequenos: substituir por busca linear branchless ou tabela inversa.
- **Match-finder branchless** com prefetch da próxima posição da chain.

### 12.3 Casos especiais

| Input | Saída esperada |
|---|---|
| 0 bytes | 1 byte (flag + EOF codificado em Ordem-0) |
| 1 byte | 2 bytes |
| Input < ~13 bytes | Pode inflar até 1 byte (flag + EOF + finalização) |
| Input com matches saturados (mesmo padrão repetido) | Ratio ≈ 1 bit por byte original |
| Ruído puro (alta entropia) | **Modo stored** ativa: saída = original + 1 byte (sem mais o teto de Shannon que inflava ~5-22%) |

### 12.4 Compatibilidade entre implementações

Duas implementações são compatíveis se e somente se:

1. Usam as mesmas constantes (§3).
2. Produzem o mesmo `cur_dist`/`cur_len` para o mesmo input no `find_match` (mesmo `LZ_MAX_CHAIN`, mesmo critério de tie-breaking).
3. Executam aprendizado **na mesma ordem** em relação à codificação.
4. Usam a mesma divisão truncada inteira em todas as operações.

Diferenças no **match-finder** (depth da chain, lazy matching) **não afetam** a corretude — só o ratio. Um `.gpa` produzido com chain depth 64 é decodificável por uma implementação com chain depth 16, porque o decoder apenas lê o que o encoder decidiu.

---

## 13. Benchmark de Referência (Python protótipo)

Para validar conformidade, implementações **devem** reproduzir os tamanhos abaixo (bit-exatos):

| Input | `.gpa` esperado (bytes) | Modo |
|---|---|---|
| `b""` | 1 | comprimido |
| `b"A"` | 2 | comprimido |
| `b"Hello World!"` | 13 | comprimido |
| `bytes(range(256))` | 257 | **stored** (256 + 1) |
| `b"A" × 100` | 6 | comprimido |
| `b'{"sensor_id":42,"temp":23.5,"hum":60}' × 30` (1110 B) | 46 | comprimido |

Os valores acima são referência do formato **v10** (incluem o bit de flag; `range(256)` cai em stored). Pequenas variações (±1-2 bytes) em outras entradas são aceitáveis se o match-finder diferir, desde que o round-trip seja preservado e a inflação não exceda +1 byte.

---

## 14. Histórico de Versões

| Versão | Mudança principal |
|---|---|
| v7 | PPM Ordem-2 nibble + Máscara de Exclusão (PPMA) |
| v8 | + LZ77 com janela 4 KB, hash chain, buckets PPM para dist/len |
| v9 | + Offset History (3 slots) + Last Length + Lazy Matching + Prior ASCII |
| v10 | + flag de modo (1 bit) + modo STORED (nunca inflar > +1 B) + pipeline streaming (RAM ~constante) |
| **v10.1** | posições LZ em `i32` (corrige truncamento i16) + janela 4 KB→32 KB + chain 16→128 + buckets de distância 13→16. Destrava o LZ em arquivos grandes/streams (codificador-only). |

A evolução preserva a tese fundamental do v7 (nibble alphabet, sem dicionário no arquivo) e amplia o range competitivo para 32 B–4 KB. **Validação empírica (v10, dados realistas):** o GPA vence deflate/gzip/zstd/lz4 em **mensagens únicas pequenas (< ~60 B)**, onde é o único que comprime em vez de inflar; em **streams multi-mensagem** o zstd-1 leva vantagem (janela maior). É um especialista em micro-payloads, não um compressor universal.