# GhostPredict — GPA (Ghost Predict Algorithm)

Compressor **lossless** especializado em **micro-payloads** (32 B – 4 KB): IoT, MQTT, telemetria, sensores, mensagens curtas.

> **A tese:** o GPA não é um compressor universal. É um **especialista em mensagens pequenas**, onde consegue a melhor relação entre compressão, latência e simplicidade — o nicho em que os compressores de propósito geral (gzip, zstd, lz4) **incham** em vez de comprimir.

---

## Por que ele existe

Para payloads minúsculos, os compressores tradicionais **aumentam** o tamanho: o overhead de cabeçalho/framing supera qualquer economia. O GPA foi desenhado para o oposto — **zero header** (o `.gpa` é puramente o stream aritmético) — e é o único que **comprime** uma mensagem de 30 B em vez de inflá-la.

```
{"device":"A23","ts":1700044556,"status":"OK","temp":27.1}   (58 B)
  gzip-9 ........ 62 B   (inflou)
  Unishox2 ...... 42 B
  GPA (frio) .... 51 B
  GPA (primed) .. 13 B   ◄── com prior de domínio
```

---

## A inovação: modo *primed* (prior embutido)

O diferencial do GPA é o **modo primed**: um **corpus de domínio embutido no próprio codec** (`primer.bin`, via `include_bytes!`) que:

1. **aquece** o modelo estatístico (PPM) — ele já começa "conhecendo" a forma das suas mensagens, eliminando o *cold-start* que limita qualquer compressor numa mensagem fria;
2. serve de **dicionário LZ** — substrings comuns (`{"device":"`, `,"status":"OK"`) viram *matches* baratos.

O ponto crucial: **o prior vive no codec, não no arquivo.** O `.gpa` continua **sem dicionário embutido** — encoder e decoder usam o mesmo primer (enviado uma vez com o firmware). Cada arquivo permanece zero-overhead.

**Resultado (held-out, dados sintéticos de domínio):** o GPA-primed **bate o `zstd --train` (dicionário) em ~2×** e **vence o Unishox2** em texto curto estruturado, mantendo o arquivo livre de dicionário. Ver [RESULTADOS.md](RESULTADOS.md).

---

## Como funciona (resumo)

```
bytes  →  LZ77 (janela auto 4 KB micro / 32 KB stream, posições i32)
       →  stream de tokens (nibbles + matches dist/len)
       →  PPM Ordem-2 sobre nibbles + modelos Dist/Len (offset history + buckets)
       →  codificador aritmético inteiro de 32 bits
       →  .gpa  (sem header, sem trailer, sem checksum)
```

- **Streaming:** processa token a token, sem materializar o stream — RAM ~constante.
- **Determinístico:** aritmética inteira, bit-exato em qualquer arquitetura.
- **Modo primed:** o primer aquece o modelo + dicionário LZ antes de codificar a mensagem.

Especificação completa e independente de linguagem: [spec.md](spec.md).

---

## Uso

### CLI (Rust)

Compilar (Windows, toolchain **GNU** — o MSVC falha no link neste ambiente):

```sh
rustc +stable-x86_64-pc-windows-gnu -C opt-level=3 main.rs -o main.exe
```

```sh
main.exe c  entrada      saida.gpa     # comprimir (zero-overhead, sem prior)
main.exe d  entrada.gpa  saida         # descomprimir
main.exe cp entrada      saida.gpa     # comprimir COM prior embutido (primed)
main.exe dp entrada.gpa  saida         # descomprimir primed
main.exe t                             # suíte de conformidade (round-trip bit-exato)
main.exe bench arquivo [iters]         # benchmark in-memory (tempo + heap da engine)
```

### GUI (Python)

```sh
python app.py
```

A GUI compila a engine Rust automaticamente e expõe compressão/extração (normal e *primed*).

### Trocar o prior

O `primer.bin` é um corpus representativo do seu domínio. Para especializar: gere um `primer.bin` com amostras das suas mensagens (uma per linha basta) e recompile — o prior é embutido em tempo de build.

---

## Ganhos e limites

### ✅ Onde o GPA ganha

| Cenário | Resultado |
|---|---|
| Mensagem única **< ~60 B** (sem prior) | **Único** que comprime; bate gzip/zstd/lz4 (que incham) |
| Micro-payload **com prior** (primed) | **Bate zstd-dict ~2×** e o Unishox2 em texto curto estruturado |
| Texto curto estruturado (JSON, URL, log, KV) | Forte, especialmente com prior genérico |
| Footprint do **decodificador** | ~37 KB (tabelas do grafo PPM) — viável em ESP32/STM32 |
| Integridade | Lossless, bit-exato, determinístico |

### ❌ Onde o GPA perde (limites honestos)

| Limite | Detalhe |
|---|---|
| Mensagem minúscula **sem prior** | Perde para o **Unishox2** (codebook hand-tuned vence o cold-start) |
| **Prosa de linguagem natural** livre | O Unishox2 (modelo de caractere) ainda ganha |
| **Arquivos grandes** gerais (> ~100 KB) | Classe-gzip; perde para zstd/xz (janela de 32 KB não pega longo alcance) |
| **Dados incompressíveis** (ruído/cripto) | Inflam (sem modo *stored* — teto de Shannon) |
| **RAM em arquivos grandes** | A engine carrega o arquivo inteiro (RAM ≈ tamanho do arquivo) |
| **Velocidade** | ~7–8 MB/s (codificador aritmético bit-a-bit) — lento para dados grandes |
| Prior é **específico de domínio** | Um prior genérico cobre texto estruturado amplo; o de domínio maximiza |

**Resumo:** o GPA é imbatível no seu nicho (micro-payload, com prior), e não compete fora dele. Análise completa com números em [RESULTADOS.md](RESULTADOS.md).

---

## Estrutura do repositório

| Arquivo | Papel |
|---|---|
| `ghost_core.rs` | Engine (LZ77 + PPM + aritmético + modo primed) |
| `main.rs` | CLI + suíte de conformidade + benchmark |
| `app.py` | GUI (Tkinter) |
| `primer.bin` | Prior embutido (corpus de domínio; trocável) |
| `spec.md` | Especificação algorítmica independente de linguagem |
| `RESULTADOS.md` | Benchmarks consolidados, limites e ganhos em profundidade |
| `planejamento_de_testes.md` | Plano de testes original |
| `cm_real.py`, `cm_lpaq.py` | Protótipos de pesquisa (engine de *context mixing* — direção futura, fora do escopo do GPA atual) |

---

## Status

Engine e modo *primed* **funcionais e validados** (round-trip bit-exato; conformidade 100%). Validação em **dados reais** (logs/IoT) é o próximo passo de pesquisa. Direções futuras documentadas em [RESULTADOS.md](RESULTADOS.md): engine de *context mixing* (mais ratio) e orquestrador de blocos (arquivos grandes com RAM limitada).
