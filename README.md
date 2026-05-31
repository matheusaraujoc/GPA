# GhostPredict (GPA)

**Compressor lossless com prior embutido no codec, especializado em micro-payloads de IoT.**

O GhostPredict é um compressor de dados sem perdas desenhado para um regime que os compressores
de uso geral atendem mal: mensagens muito curtas, de dezenas de bytes, típicas de telemetria de
IoT (MQTT, CoAP, LoRaWAN, NB-IoT). Nesse regime, gzip, zstd e brotli costumam **aumentar** o
tamanho do dado, porque o custo fixo de cabeçalho e enquadramento supera qualquer economia.

A tese do projeto, sustentada por experimentos em onze conjuntos de dados reais, é simples e
mensurável: **compartilhar um prior de domínio no firmware, e não no arquivo, é vantajoso para
micro-payloads.** O prior aquece o modelo estatístico e serve de dicionário, sem que o arquivo
comprimido carregue qualquer dicionário ou cabeçalho.

| | |
|---|---|
| Resultado central | menor arquivo entre todos os concorrentes no nicho; ~1,7× sobre o dicionário enxuto do zstd (modelo isolado), até ~3× sobre o dicionário padrão |
| Garantia | nunca expande a entrada além de ~0,1% (modo de armazenamento) |
| Footprint | decodificador ~19 KB de RAM, compressor ~51 KB; primer 16–32 KB de flash |
| Integridade | lossless, determinístico, bit a bit exato (suíte de conformidade) |

A análise completa está em **[artigo/](artigo/)** (artigo no padrão SBC e documentação técnica
detalhada, ambos em `.docx` e `.pdf`).

---

## Sumário

- [Início rápido](#início-rápido)
- [Compilação](#compilação)
- [Manual de uso](#manual-de-uso)
  - [CLI do motor (main.exe)](#1-cli-do-motor-mainexe)
  - [Gerador de primer (gen_primer.py)](#2-gerador-de-primer-gen_primerpy)
  - [Interface gráfica (app.py)](#3-interface-gráfica-apppy)
  - [Benchmark de validação (benchmark.py)](#4-benchmark-de-validação-benchmarkpy)
- [Como o algoritmo funciona](#como-o-algoritmo-funciona)
- [Reprodução da validação](#reprodução-da-validação)
- [Resultados](#resultados)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Limites](#limites)

---

## Início rápido

```sh
# 1. compilar o motor (Windows, toolchain GNU)
rustc +stable-x86_64-pc-windows-gnu -C opt-level=3 main.rs -o main.exe

# 2. verificar a corretude (suíte de conformidade, round-trip bit a bit)
main.exe t

# 3. comprimir e descomprimir uma mensagem
main.exe c   mensagem.json   mensagem.gpa     # comprime (nunca infla)
main.exe d   mensagem.gpa    saida.json       # descomprime

# 4. comprimir COM prior de domínio (a inovação)
main.exe cp  mensagem.json   mensagem.gpa     # usa o primer embutido (primer.bin)
main.exe dp  mensagem.gpa    saida.json
```

---

## Compilação

### Motor (obrigatório)

O motor é Rust puro, sem dependências externas, compilado por um único comando. No Windows usa-se
a cadeia **GNU**, pois o ligador MSVC falha neste projeto.

```sh
rustc +stable-x86_64-pc-windows-gnu -C opt-level=3 main.rs -o main.exe
```

O `primer.bin` é embutido no binário em tempo de compilação (`include_bytes!`). Trocar o prior
significa substituir `primer.bin` e recompilar.

### Ferramentas de comparação (apenas para o benchmark)

O `benchmark.py` compara o GPA com especialistas de string curta. Compile-os uma vez:

```sh
cd tools/short
gcc -O2 -o uni_cli.exe  uni_cli.c  unishox2.c
gcc -O2 -o smaz_cli.exe smaz_cli.c smaz.c
```

O benchmark também usa `zstd`, `xz`, `gzip` e `brotli` no PATH, e o pacote Python `psutil`
(opcional, para medir memória).

---

## Manual de uso

### 1. CLI do motor (main.exe)

O arquivo comprimido (`.gpa`) é puramente o fluxo aritmético, sem cabeçalho. Comandos:

| Comando | Função |
|---|---|
| `c   entrada saida.gpa` | Comprimir. Seleciona o perfil de janela pelo tamanho e garante nunca inflar. |
| `d   entrada.gpa saida` | Descomprimir. |
| `cp  entrada saida.gpa` | Comprimir **com prior** embutido no binário (`primer.bin`). |
| `dp  entrada.gpa saida` | Descomprimir com o prior embutido. |
| `cpf entrada saida.gpa primer` | Comprimir com prior lido de um **arquivo** (sem recompilar). |
| `dpf entrada.gpa saida primer` | Descomprimir com prior de arquivo. |
| `cs  entrada saida.gpas` | Comprimir em **fluxo de blocos** (RAM limitada, arquivos grandes). |
| `ds  entrada.gpas saida` | Descomprimir fluxo de blocos. |
| `t` | Suíte de **conformidade** (round-trip bit a bit + nunca inflar + tamanhos de referência). |
| `bench entrada [iters]` | Benchmark **em memória**: tempo e pico de heap do motor. |

**Importante sobre o modo com prior:** o `.gpa` gerado por `cp`/`cpf` contém apenas a mensagem;
o primer não vai no arquivo. A descompressão (`dp`/`dpf`) **exige o mesmo primer** usado na
compressão, byte a byte. Encoder e decoder compartilham o primer, distribuído uma vez com o
firmware.

Exemplo do efeito do prior (mensagem MQTT real de 69 bytes):

```
1725866030.472465,0x0018,...,2,dos          (69 B)
  GPA sem prior (c)  .... 42 B
  zstd --train (dict) ... 43 B
  Unishox2 .............. 35 B
  GPA com prior (cp) .... 16 B   ◄── prior de domínio casado
```

### 2. Gerador de primer (gen_primer.py)

O primer é um corpus bruto de amostras representativas do domínio, uma por linha. O
`gen_primer.py` o constrói em três modos:

```sh
# de um dataset (held-out: reserva as primeiras N de teste, usa as seguintes como treino)
python gen_primer.py --from-dataset datasets/.../loop_1.csv --skip-header --cap 32768

# corpus genérico sintético e determinístico (texto curto estruturado)
python gen_primer.py --synthetic --cap 16384

# concatenando arquivos de amostras seus
python gen_primer.py --from-files urls.txt jsons.txt --out primer.bin
```

Após gerar um novo `primer.bin`, **recompile o motor** para embuti-lo. Detalhes de
dimensionamento: todo o corpus aquece o modelo PPM, mas só os **últimos 32 KB** (a janela do LZ)
servem de dicionário, por isso o corte padrão em 32 KB.

### 3. Interface gráfica (app.py)

```sh
python app.py
```

A GUI (Tkinter) compila o motor automaticamente e expõe os três modos: normal (`.gpa`), com prior
(`.gpa`) e streaming (`.gpas`), cada um com botões de comprimir e extrair. Útil para uso manual
sem a linha de comando.

### 4. Benchmark de validação (benchmark.py)

Ponto de entrada para um revisor reproduzir a avaliação. Verifica os pré-requisitos
automaticamente e imprime uma tabela-resumo.

```sh
python benchmark.py --quick     # ~minutos: 3 domínios, 50 mensagens (sanidade)
python benchmark.py             # completo: 11 domínios, 1000 mensagens (~1 h)
python benchmark.py --no-cross  # pula o experimento cross-domínio
```

Saídas: `resultados_reais.json` e `cross_domain.json` (o modo `--quick` escreve em
`resultados_quick.json` para nunca sobrescrever os resultados canônicos). A partir desses JSON,
`gen_artigo.py` e `gen_doc.py` regeneram o artigo e a documentação.

---

## Como o algoritmo funciona

Pipeline determinístico, processado símbolo a símbolo:

```
bytes  →  LZ77 (janela 4 KB micro / 32 KB fluxo)  →  nibbles + matches (dist, len)
       →  PPM ordem-2 sobre nibbles + modelos de distância e comprimento
       →  codificador aritmético inteiro de 32 bits
       →  .gpa (sem cabeçalho, sem rodapé, sem checksum)
```

- **Sem cabeçalho:** o arquivo é só o fluxo aritmético, o que elimina o custo fixo que faz os
  formatos gerais incharem mensagens curtas.
- **Nunca inflar:** a primeira decisão codificada é uma flag binária enviesada (1/64) que, no pior
  caso, ativa um modo de armazenamento direto, limitando a expansão a ~0,1% mais alguns bytes.
- **Prior embutido:** antes de codificar, encoder e decoder percorrem o primer e aquecem o modelo
  de forma idêntica; o primer também alimenta o dicionário LZ.
- **Determinístico:** aritmética inteira, reconstrução bit a bit exata em qualquer arquitetura.

A especificação independente de linguagem está em [spec.md](spec.md). A descrição completa, com
trechos de código comentados, base matemática e guia de reimplementação, está em
[artigo/GhostPredict_Documentacao.docx](artigo/).

---

## Reprodução da validação

### Dados

A pasta `datasets/` não está versionada (é grande; veja `.gitignore`). Para reconstruí-la, baixe
os conjuntos abaixo e mantenha a estrutura de pastas que o `benchmark.py` espera (ver as funções
`ex_*` no início do script).

| Domínio | Fonte | Origem |
|---|---|---|
| MQTT | MQTTEEB-D | Mendeley Data, DOI 10.17632/jfttfjn6tr |
| AIS | MarineCadastre AIS | marinecadastre.gov/accessais (NOAA e BOEM) |
| Sensores | Intel Lab Data | db.csail.mit.edu/labdata/labdata.html |
| Energia | UCI Household Power | UCI ML Repository, DOI 10.24432/C58K54 |
| GPS | GeoLife | Microsoft Research (Zheng et al. 2009) |
| Logs | Loghub | github.com/logpai/loghub (Zhu et al. 2023) |
| SMS | SMS Spam Collection | UCI ML Repository, DOI 10.24432/C5CC84 |
| Tweets | Sentiment140 | Go, Bhayani e Huang 2009 (Stanford) |

### Protocolo

Para cada domínio, os registros são embaralhados com semente fixa e divididos em teste e treino
disjuntos. O treino constrói **tanto** o primer do GPA (últimos 32 KB) **quanto** o dicionário do
zstd, com as mesmas amostras. Cada mensagem de teste é comprimida individualmente. Medir mensagens
isoladas, e não arquivos inteiros, é essencial: arquivos diluiriam o custo de partida a frio que o
prior corrige.

### Passo a passo

```sh
rustc +stable-x86_64-pc-windows-gnu -C opt-level=3 main.rs -o main.exe   # 1. motor
main.exe t                                                              # 2. conformidade
python benchmark.py                                                     # 3. validação (gera JSON)
python gen_artigo.py && python gen_doc.py                               # 4. artigo e documentação
```

Sementes fixas tornam o procedimento reproduzível dentro da variação esperada de medição de tempo.

---

## Resultados

Tamanho médio do comprimido por mensagem, com prior casado (1000 mensagens/domínio, held-out):

| Domínio | original | GPA com prior | zstd-dict | fator (lean) |
|---|---:|---:|---:|---:|
| Log-Apache | ~84 B | **10 B** | 32 B | 2,3× |
| MQTT | ~75 B | **18 B** | 42 B | 1,9× |
| GPS (GeoLife) | ~65 B | **24 B** | 49 B | 1,7× |
| Sensores | ~64 B | **26 B** | 52 B | 1,7× |

- O GPA com prior produz o **menor arquivo** em todos os domínios, incluindo contra Unishox2 e
  SMAZ. Sobre o dicionário **enxuto** do zstd (modelo isolado, sem enquadramento), o fator é
  ~1,3–2,3× (média ~1,7×). Parte do ganho é do modelo, parte da ausência de cabeçalho; o artigo
  decompõe os dois.
- **Dependência de domínio:** um primer descasado degrada o resultado em até ~10× (pode inflar).
  É o limite do método, quantificado no experimento cross-domínio.
- **Fora do nicho** (arquivos grandes, prosa livre, DNA), o GPA é classe-gzip e não compete; ver
  [RESULTADOS.md](RESULTADOS.md) e o artigo.

---

## Estrutura do repositório

| Arquivo / pasta | Papel |
|---|---|
| `ghost_core.rs` | **O algoritmo**: LZ77 + PPM + aritmético + prior + nunca-inflar + streaming |
| `main.rs` | CLI, suíte de conformidade, benchmark em memória, container `.gpas` |
| `primer.bin` | Prior genérico embutido no motor (trocável; ver `gen_primer.py`) |
| `gen_primer.py` | Gerador de primer (de dataset, sintético, ou de arquivos) |
| `app.py` | Interface gráfica (Tkinter) |
| `benchmark.py` | Validação reproduzível para revisores (gera os JSON) |
| `gen_artigo.py`, `gen_doc.py` | Geram o artigo e a documentação a partir dos JSON |
| `tools/short/` | Unishox2 e SMAZ (fontes + drivers) usados como baselines |
| `embedded/` | Decoder de referência em C (`no_std`, sem alocação) + projeto ESP-IDF; valida o footprint da Tabela 8 com `idf.py size` |
| `spec.md` | Especificação algorítmica independente de linguagem |
| `artigo/` | Artigo (SBC) e documentação técnica completa, em `.docx` e `.pdf` |
| `RESULTADOS.md` | Síntese de ganhos e limites |
| `datasets/` | Dados reais da validação (não versionado; ver acima) |

---

## Limites

- **Sem prior**, em mensagem minúscula fria, perde para o Unishox2 (codebook hand-tuned).
- O ganho **depende de um prior casado com o domínio**; um prior genérico ou de outro domínio
  rende pouco e pode inflar.
- **Fora do nicho** (dados grandes gerais, prosa livre, DNA), fica na classe do gzip, atrás de
  zstd, xz e brotli.
- **Velocidade** ~7 MB/s (codificador aritmético bit a bit), adequada a mensagens curtas, não a
  grandes volumes.

Análise honesta e completa, com a decomposição do ganho e o trade-off flash/RAM/compressão, no
artigo e na documentação em [artigo/](artigo/).
