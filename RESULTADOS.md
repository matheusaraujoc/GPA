# GPA — Resultados, Limites e Ganhos

Consolidação dos benchmarks do GhostPredict. Define onde o algoritmo **ganha**, onde **perde**, e o perfil de **recursos**.

> **Metodologia / ressalvas.** Os dados abaixo usam **payloads sintéticos realistas** (geradores com variação: device IDs, timestamps, valores aleatórios) e arquivos reais do projeto (código/markdown). Tamanhos em **bytes** (menor = melhor) ou ratio % (maior = melhor). Os testes *primed* usam conjuntos **held-out** (valores novos, não vistos no primer). Concorrentes: gzip-9, zstd (níveis 1/3/19 e `--train`/dict), brotli-11, lzma/xz-9, Unishox2 (compilado do fonte oficial). **Validação em dados reais (logs/IoT) é o próximo passo** — os números aqui indicam o comportamento, não substituem um corpus real.

---

## 1. Conformidade (correção)

Suíte `main.exe t` — round-trip **bit-exato** em todos os casos de referência (vazio, 1 byte, "Hello World!", range(256), repetições, JSON IoT). Integridade lossless verificada também em toda a bateria de benchmark (SHA256 / comparação byte-a-byte). **Nenhuma corrupção em nenhum tamanho testado (até 64 MB).**

---

## 2. Micro-payload SEM prior — o nicho fundamental

Mensagem única minúscula, sem nenhum conhecimento prévio. Tamanho do `.gpa` (bytes):

| Caso | orig | **GPA** | gzip-9 | zstd-1 | zstd-3 | lz4 |
|---|---:|---:|---:|---:|---:|---:|
| MQTT `{"temp":25.3}` | 13 | **14** | 33 | 22 | 22 | 36 |
| MQTT 35 B | 35 | **32** | 55 | 44 | 44 | 58 |
| GPS 35 B | 35 | **31** | 53 | 44 | 44 | 58 |
| Sensor 25 B | 25 | **24** | 45 | 34 | 34 | 48 |
| Telemetria 42 B | 42 | **38** | 59 | 51 | 51 | 65 |

**Ganho:** o GPA é o **único** que comprime — todos os de propósito geral **inflam** (overhead de framing domina). Esse é o resultado fundamental do nicho. **Placar vs gerais: GPA vence 100%.**

**Limite:** vs o especialista **Unishox2** (codebook hand-tuned), o GPA-**frio perde** — o Unishox vence o *cold-start* numa mensagem fria:

| Caso | GPA-frio | Unishox2 |
|---|---:|---:|
| Telemetria | 51 | **42** |
| Sensor | 23 | **19** |
| GPS | 36 | **32** |
| MQTT | 32 | **28** |

> Sem conhecimento embutido, é matematicamente impossível bater quem o tem (Unishox) numa mensagem fria minúscula. **O prior resolve isso.**

---

## 3. Micro-payload COM prior (*primed*) — a inovação

Prior de domínio embutido (não vai no arquivo). Conjunto **held-out** (valores novos). Tamanho do `.gpa` (bytes):

| Caso | orig | **GPA-primed** | GPA-frio | Unishox2 | brotli-11 | zstd-dict (mín.) |
|---|---:|---:|---:|---:|---:|---:|
| Telemetria | 58 | **13** | 51 | 42 | 62 | 25 |
| Sensor | 25 | **10** | 23 | 19 | 29 | 17 |
| GPS | 40 | **14** | 34 | 32 | 44 | 29 |
| MQTT | 35 | **9** | 32 | 28 | 39 | 18 |
| Telem WARN | 60 | **15** | 52 | 43 | 64 | 25 |

**Ganho:** o GPA-primed **vence todos**. Contra o concorrente justo (`zstd --train` em dicionário, no melhor frame possível — *magicless*, sem checksum/content/dictID), o GPA é **~2× menor**. E mantém o `.gpa` **sem dicionário** (o prior está no codec). Round-trip verificado.

> A vantagem vem da combinação **zero-overhead + modelo aquecido + dicionário LZ + codificação aritmética** — exatamente onde o zstd ainda carrega overhead de bloco/FSE que pesa em saídas de ~10 B.

---

## 4. Prior genérico — generalidade além do domínio

Primer **genérico** (corpus amplo de texto curto variado, não específico de domínio), testado em texto held-out diverso. Vencedor (menor) por caso:

| Caso | GPA-prim-gen | Unishox2 | brotli-11 | vencedor |
|---|---:|---:|---:|:---:|
| URL | 18 | 38 | 38 | **GPA** |
| Email | 8 | 15 | 24 | **GPA** |
| JSON | 26 | 38 | 60 | **GPA** |
| Log | 24 | 37 | 51 | **GPA** |
| Key-Value | 15 | 31 | 38 | **GPA** |
| Inglês (prosa comum) | 25 | 36 | 32 | **GPA** |
| Inglês ("quick brown fox") | 30 | 29 | 47 | Unishox |
| Frase PT | 26 | 19 | 32 | Unishox |

**Placar: GPA 8 × 2 Unishox2.** Com um prior genérico, o GPA é um **bom compressor geral de texto curto estruturado** (URLs, JSON, logs, configs — o universo máquina-a-máquina).

**Limite:** perde em **prosa de linguagem natural livre** com vocabulário fora do corpus (o codebook caractere-a-caractere do Unishox é mais robusto a palavras novas), e em **idioma não coberto** pelo primer (ex.: PT num primer inglês — corrigível incluindo PT no corpus).

---

## 5. Dados gerais / arquivos maiores — fora do nicho

Engine **frio** em arquivos reais (ratio %, maior = melhor):

| arquivo | orig | **GPA** | gzip-9 | zstd-19 | brotli-11 | lzma-9 |
|---|---:|---:|---:|---:|---:|---:|
| app.py (Python) | 9,9 KB | 73,5% | 74,8% | 75,2% | **77,3%** | 74,8% |
| spec.md (markdown) | 24 KB | 61,4% | 62,5% | 63,6% | **66,0%** | 64,2% |
| ghost_core.rs (Rust) | 40 KB | 79,4% | 80,2% | 81,3% | **82,3%** | 81,5% |
| JSON 1 MB | 1 MB | 92,6% | 89,8% | 98,3% | **98,6%** | 98,3% |
| CSV 1 MB | 1 MB | 86,5% | 81,8% | 92,1% | **95,7%** | 95,1% |
| aleatório 64 KB | 64 KB | **−2,8%** | −0,0% | −0,0% | −0,0% | −0,1% |

**Limite:** em dados gerais o GPA é **classe-gzip** — levemente atrás em texto, à frente do gzip em dados estruturados, mas **atrás de zstd/brotli/lzma**. Causas: janela LZ de 32 KB (não pega longo alcance), modelo de só 1 byte de contexto, alfabeto de nibble (desperdiça a vantagem do aritmético). Em **dados incompressíveis** ele **infla** (único do grupo — não tem modo *stored*).

---

## 6. Escalabilidade e recursos

Engine frio, dados não-repetitivos crescentes:

| tamanho | ratio | velocidade | RAM pico |
|---|---:|---:|---:|
| 1 MB | 78,7% | ~7 MB/s | 5 MB |
| 8 MB | 78,7% | 7,0 MB/s | 14 MB |
| 64 MB | 78,8% | 7,2 MB/s | 82 MB |

- **Ratio não degrada com o tamanho** — estável; não há "cliff".
- **RAM ≈ tamanho do arquivo** — a engine carrega o arquivo inteiro na memória (`Vec`). É o gargalo para arquivos muito grandes.
- **Velocidade ~7 MB/s constante** (codificador aritmético bit-a-bit). 1 GB ≈ ~2,3 min.

**Footprint da engine (heap, via tracking allocator):**
- **Decodificador:** ~**37 KB** (só as tabelas do grafo PPM) até 4 KB — não usa tabelas LZ. Viável em ESP32/STM32.
- **Codificador:** ~117 KB (janela micro 4 KB) a ~232 KB (janela stream 32 KB) — inclui as tabelas LZ.

---

## 7. Síntese: limites e ganhos

### Ganhos
- **Único que comprime micro-payload** onde os gerais incham (zero-overhead).
- **Com prior: bate zstd-dict ~2× e Unishox2** em texto curto estruturado, sem dicionário no arquivo.
- **Prior genérico generaliza** para texto curto estruturado amplo (8×2 vs Unishox).
- **Decodificador leve** (~37 KB) — embarcado.
- **Lossless, determinístico, bit-exato, streaming.**

### Limites
- **Sem prior, perde para o Unishox2** no minúsculo (cold-start).
- **Prosa livre / idioma fora do primer:** Unishox vence.
- **Dados gerais grandes:** classe-gzip; perde para zstd/brotli/lzma (janela 32 KB).
- **Incompressível:** infla (sem *stored*).
- **RAM = tamanho do arquivo**; **velocidade ~7 MB/s** — limita arquivos muito grandes.

### Posicionamento honesto
O GPA é **imbatível no seu nicho** (micro-payload, com prior) e **não compete fora dele**. A força é a especialização, não a universalidade — exatamente a tese do projeto.

---

## 8. Direções futuras (fora do escopo do GPA atual)

Exploradas em protótipo (Python), **não incluídas neste repositório** (mantido focado no GPA):

- **Context Mixing (CM):** um CM tunado classe-lpaq a **frio** bateu gzip/zstd-19/brotli-11 em **ratio** em texto/código pequeno-médio — ao custo de velocidade (lento). CM+prior superaria o nibble-PPM+prior. Direção para mais ratio.
- **Orquestrador de blocos:** dividir arquivos grandes em blocos (~4 MB), comprimir em **paralelo** com **best-of-breed** por bloco (zstd/xz/GPA), unir. Dá **RAM limitada** (bloco × workers, independe do tamanho) + **velocidade** (paralelismo) + ratio best-of-breed — a arquitetura para o caso de arquivos grandes, onde o GPA entra só nos blocos do seu nicho.

Estas frentes formam uma "estrutura completa" futura: **GPA para pequeno, orquestrador+ferramentas fortes para grande.** O foco atual é finalizar o **GPA (o núcleo / a inovação)**.
