# GPA — Decoder de referência embarcado (ESP32 / ESP-IDF)

Decodificador do GhostPredict em **C, `no_std`, sem alocação dinâmica**: todo o estado vive
em memória estática (`.bss`), nenhuma chamada a `malloc`. É um porte **bit-exato** do motor Rust
(`ghost_core.rs`), restrito à descompressão, pensado para microcontroladores como o ESP32.

O objetivo deste diretório é permitir **validar o footprint da Tabela 8 sem hardware**, por
compilação cruzada e análise estática (`idf.py size`), e servir de ponto de partida para rodar
no dispositivo.

## Conteúdo

```
components/gpa_decoder/
  include/gpa_decoder.h     API pública (gpa_decompress, gpa_decompress_primed)
  gpa_decoder.c             implementação no_std, sem alocação
  CMakeLists.txt            componente ESP-IDF
main/
  gpa_example_main.c        exemplo: descomprime uma mensagem embutida, mede heap e latência
  CMakeLists.txt
CMakeLists.txt              projeto ESP-IDF
test/host_test.c            driver de PC para verificar bit-exatidão contra o main.exe (Rust)
```

## Corretude (verificada no PC)

O decoder foi confrontado com o motor Rust em vetores de conformidade e mensagens reais, em modo
normal e com prior. Compilar e testar no PC:

```sh
cd test
gcc -O2 -DGPA_ENABLE_PRIMED -I ../components/gpa_decoder/include \
    ../components/gpa_decoder/gpa_decoder.c host_test.c -o gpa_host.exe

# no PC, comprima com o motor Rust e decodifique com o C:
main.exe c   entrada      m.gpa      &&  gpa_host m.gpa   saida          # modo normal
main.exe cpf entrada      m.gpa  primer.bin &&  gpa_host m.gpa saida primer.bin   # com prior
```

Resultado: **12 de 12 casos bit-exatos** (vazio, literal, "Hello World!", faixa 0–255, repetição,
JSON, mensagem MQTT, ruído aleatório; normal e com prior).

## Footprint (medido com `size`, o mesmo que `idf.py size` usa)

Compilando o objeto e inspecionando as seções:

```sh
gcc -O2 -c -I components/gpa_decoder/include components/gpa_decoder/gpa_decoder.c -o n.o
size n.o
```

| Configuração | `.text` (flash) | `.bss` (RAM estática) |
|---|---:|---:|
| **Decoder normal** (só o modelo PPM) | ~4,1 KB | **~19,3 KB** |
| Decoder com prior (`-DGPA_ENABLE_PRIMED`) | ~7,0 KB | ~259 KB |

Medido **no alvo ESP32 real** (após `idf.py build`), o `idf.py size-components` reporta para o
componente `gpa_decoder`: **`.bss` = 19.692 B**, `.text` (flash) = 1.811 B e `.rodata` = 220 B. As
três medições independentes do `.bss` convergem: alocador Rust 19.083 B, `size` no objeto x86
19.776 B, ESP32 xtensa 19.692 B.

O `.bss` do decoder normal, de cerca de **19 KB**, confirma a linha "decodificador ~19 KB" da
Tabela 8 do artigo, agora por análise estática e não apenas pelo alocador instrumentado. Como o
design é sem alocação, esse é o footprint completo de RAM em tempo de execução. O modo com prior
adiciona as tabelas LZ usadas para aquecer o modelo (hash e janela) mais um buffer de trabalho,
o que explica os ~259 KB; ainda cabe nos ~320–520 KB de SRAM de um ESP32, mas é um footprint bem
maior, por isso fica atrás da diretiva `GPA_ENABLE_PRIMED`.

## Compilar e medir para ESP32 (sem placa, no PC)

Com o ESP-IDF instalado:

```sh
idf.py set-target esp32
idf.py build
idf.py size              # mapa estatico: Flash (.text + .rodata, com o primer) e RAM (.data + .bss)
idf.py size-components   # detalhamento por componente (mostra o gpa_decoder)
```

O `idf.py size` reporta o footprint estático cruzado para o xtensa, validando que o código e os
dados cabem na flash e na RAM do alvo, **sem precisar da placa física**.

## Rodar na placa (opcional)

```sh
idf.py flash monitor
```

O exemplo (`main/gpa_example_main.c`) descomprime uma mensagem embutida (comprimida no PC com
`main.exe c`), confere o round-trip bit a bit, e imprime a latência (`esp_timer_get_time`) e o
heap livre antes e depois (`heap_caps_get_free_size`). Como não há alocação dinâmica, o delta de
heap é nulo; o consumo aparece todo no `.bss`, visível pelo `idf.py size`.

## Habilitar o modo com prior

Defina `GPA_ENABLE_PRIMED` (no componente, descomente a linha `target_compile_definitions`),
embuta o `primer.bin` como vetor `const` na flash, e use `gpa_decompress_primed`. Lembre que o
primer deve ser **byte a byte idêntico** ao usado na compressão.

## Relação com o motor

O `gpa_decoder.c` é um porte direto do caminho de descompressão de `ghost_core.rs`: codificador
aritmético inteiro de 32 bits, modelo PPM de ordem 2 sobre nibbles com escape e exclusão, modelos
de distância e comprimento, e, no modo com prior, o aquecimento via LZ77. O Apêndice C da
documentação técnica mapeia cada etapa às listagens de código.
