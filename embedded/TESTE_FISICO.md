# Protocolo de teste físico no ESP32

Guia para produzir, na placa real, os números que a análise estática não alcança:
**latência por mensagem, folga de pilha, heap dinâmico e integridade** do decodificador GPA.
São exatamente as medições que o artigo lista como trabalho futuro na Seção 10.

O que já está validado **sem** hardware (não precisa refazer):

| Alegação | Como foi validada | Resultado |
|---|---|---|
| Round-trip bit a bit | decoder C contra o motor Rust, 12 vetores held-out, modos frio e com prior | 24/24 exatos |
| Footprint de RAM do decoder | `idf.py size-components` no alvo xtensa | `.bss` = 19.692 B |
| Ausência de alocação dinâmica | inspeção do código: todo o estado é estático | zero `malloc` |

O que **só** a placa entrega: latência real, folga de pilha, comportamento térmico e de
alimentação, e o custo do modo com prior sob CPU embarcada.

---

## Hardware confirmado

Placa detectada e identificada por `esptool` em 2026-08-03:

| Item | Valor |
|---|---|
| Chip | ESP32-D0WDQ6, revisão v1.1 |
| Núcleos e clock | dual core, 240 MHz |
| SRAM | 520 KB (DRAM utilizável ~320 KB) |
| Flash | 16 MB |
| Cristal | 40 MHz |
| MAC | 5c:01:3b:07:9f:e4 |
| Porta serial | **COM3** (USB-serial CH9102, driver OK) |
| Alvo do IDF | `idf.py set-target esp32` |

A flash de 16 MB acomoda o primer com folga enorme (16 KB, 0,1% da flash). A restrição real é a
DRAM no modo com prior, tratada na Seção 3.

---

## 0. Pré-requisitos

**Único bloqueio hoje:** o ESP-IDF não está instalado (restou apenas o driver USB em
`~/.espressif/tools/idf-driver`; `C:\Espressif` não existe mais, e não há PlatformIO nem a
extensão do VSCode). A placa já é reconhecida em COM3, então falta só a cadeia de compilação.

Instale a versão **v5.5.x** (a mais recente da série 5.5, hoje a v5.5.5), pelo instalador
oficial em https://dl.espressif.com/dl/esp-idf/. Ele traz o toolchain xtensa, o Python do IDF e
o git; são cerca de 2 GB e uns 15 a 30 minutos.

**Por que a 5.5 e não a 6.0.** O `sdkconfig` deste projeto foi gerado pela v5.5.4
(`CONFIG_IDF_INIT_VERSION="5.5.4"`), então a série 5.5 reaproveita a configuração sem
migração. A v6.0 é uma release maior, com remoção de APIs obsoletas e mudanças de build, e não
traz nada de útil aqui: o que ela adiciona é suporte a chips novos (ESP32-C5, C61), e a placa
deste projeto é o ESP32 clássico. Para um artigo, vale ainda fixar a versão exata usada e
reportá-la junto dos resultados.

Depois, abra o terminal **ESP-IDF PowerShell** (ele exporta `IDF_PATH` e o toolchain) e confirme:

```sh
idf.py --version
```

Também é preciso o motor Rust compilado, para gerar os vetores:

```sh
rustc +stable-x86_64-pc-windows-gnu -C opt-level=3 main.rs -o main.exe
main.exe t          # suite de conformidade, deve passar tudo
```

> **Atenção ao Python.** Dentro do terminal ESP-IDF, o `python` é o do IDF e não tem as
> bibliotecas do projeto. Para os scripts do repositório use o caminho explícito:
> `C:/Users/Matheus/AppData/Local/Programs/Python/Python311/python.exe`.

---

## 1. Gerar os vetores de teste

O firmware não testa uma mensagem inventada: ele testa mensagens **held-out**, geradas pelo
mesmo protocolo do `benchmark.py` (embaralhamento com semente fixa, treino e teste disjuntos,
primer construído só com o treino).

```sh
# corpus IoT determinístico, não exige a pasta datasets/
python embedded/tools/gen_vectors.py

# preferível para o artigo: dados reais, um registro por linha
python embedded/tools/gen_vectors.py --from-file datasets/mqtt/loop_1.csv --skip-header
```

Isso escreve `embedded/main/gpa_test_vectors.h` (as mensagens e seus `.gpa`) e
`embedded/main/gpa_primer_test.bin` (o primer do domínio).

Com o corpus padrão, o resultado esperado é:

```
media: orig 58,2 B  frio 49,4 B  primed 16,9 B
fator primed sobre o original: 3,44x
```

### Conferir os vetores no PC antes de gravar

Roda o **mesmo** decoder C que vai para a placa, então pega erro de geração sem gastar ciclo
de flash. O `gcc` do MSYS2 precisa da própria pasta no `PATH`, senão falha sem mensagem:

```sh
export PATH="/c/msys64/ucrt64/bin:$PATH"
cd embedded/test

# modo frio
gcc -O2 -I ../components/gpa_decoder/include -I ../main \
    ../components/gpa_decoder/gpa_decoder.c vectors_test.c -o vectors_test.exe
./vectors_test.exe

# modo com prior
gcc -O2 -DGPA_ENABLE_PRIMED -I ../components/gpa_decoder/include -I ../main \
    ../components/gpa_decoder/gpa_decoder.c vectors_test.c -o vectors_primed.exe
./vectors_primed.exe
```

Esperado: `TODOS OS VETORES BIT-EXATOS`. Se falhar aqui, **não grave na placa**: o problema
está na geração, não no hardware.

---

## 2. Experimento A — modo frio

É o caminho de baixo footprint (~19 KB de `.bss`), o que o artigo defende como viável em
microcontrolador.

```sh
cd embedded
idf.py set-target esp32
idf.py build
idf.py size-components      # confirme .bss do componente gpa_decoder (~19.692 B)
idf.py -p COM3 flash monitor
```

A porta desta placa é a **COM3**, já confirmada. Para sair do monitor: `Ctrl+]`.

Saída esperada (os tempos são o que você vai registrar):

```
=== MODO FRIO (sem prior) ===
msg  orig  .gpa  fator   ok    min    med   media    p95    max   (us)
  0    54    53   1.02x  OK     ...
...
latencia media..: <X> us por mensagem
integridade.....: TODAS bit-exatas
```

**Registre:** latência média, mediana, p95, vazão, delta de heap (deve ser 0), folga de pilha.

---

## 3. Experimento B — modo com prior

Este é o mecanismo central do artigo, e é onde está o achado mais importante do teste.

Habilite o modo editando `components/gpa_decoder/CMakeLists.txt`, descomentando:

```cmake
target_compile_definitions(${COMPONENT_LIB} PUBLIC GPA_ENABLE_PRIMED)
```

Depois:

```sh
idf.py fullclean && idf.py build
idf.py size-components      # o .bss sobe para ~259 KB
idf.py -p COM3 flash monitor
```

### Aviso de memória

O modo com prior usa cerca de **259 KB de `.bss`**, assim distribuídos:

| Estrutura | Tamanho | Para quê |
|---|---:|---|
| `LZ_prev[32768]` (int32) | 128,0 KB | cadeia de hash do LZ, para reparsar o primer |
| `LZ_head[16381]` (int32) | 64,0 KB | cabeça da hash do LZ |
| `WORK[32768+16384]` | 48,0 KB | primer mais mensagem reconstruída |
| modelo PPM e auxiliares | 19,2 KB | o mesmo do modo frio |
| **total** | **~259 KB** | |

Um ESP32 tem cerca de 320 KB de DRAM utilizável, então **cabe, mas com pouca folga**. Se o
link falhar com `region 'dram0_0_seg' overflowed`, na ordem:

1. **Desabilite Wi-Fi e Bluetooth** no `menuconfig`. As duas pilhas reservam dezenas de KB de
   DRAM mesmo sem serem usadas, e o benchmark não precisa de rádio. É de longe o maior ganho.
2. **Reduza o buffer de trabalho** para o tamanho real do seu primer mais a maior mensagem.
   Com o primer de 16 KB e mensagens de ~100 B, `-DGPA_WORK_SIZE=18432` economiza 30 KB. O
   decoder valida os limites, então um valor pequeno demais retorna erro em vez de corromper.

> **Não adianta reduzir o primer** com `--primer-cap` para resolver estouro de DRAM: as tabelas
> `LZ_head` e `LZ_prev` têm tamanho fixo (192 KB somadas), independente do primer, porque
> precisam reproduzir exatamente o parse do compressor. Um primer menor só diminui o
> `GPA_WORK_SIZE` necessário. Encolher as tabelas exigiria mudar compressor e decodificador
> juntos, ou seja, mudança de formato.

### O achado a confirmar na placa

Medido no PC, com o mesmo código que vai para a placa:

| Modo | Latência por mensagem (PC) | Tamanho médio |
|---|---:|---:|
| Frio | ~4 µs | 49,4 B |
| Com prior | ~1048 µs | 16,9 B |

A diferença de ~250× **não é o custo de decodificar**: é o custo de **re-aquecer o modelo com
os 16 KB do primer a cada mensagem**. A decodificação em si continua custando poucos
microssegundos; o aquecimento é que domina.

Extrapolando para o ESP32 a 240 MHz, espere algo entre **20 ms e 40 ms por mensagem** no modo
com prior, contra dezenas de microssegundos no modo frio. Confirmar essa ordem de grandeza na
placa é um dos objetivos do teste.

**Consequência de engenharia (candidata a trabalho futuro):** aquecer o modelo **uma vez no
boot** e guardar uma cópia do estado (~19 KB), restaurando-a por `memcpy` antes de cada
mensagem, em vez de reprocessar o primer. Isso troca ~20 ms de CPU por ~19 KB de RAM extra e
deve derrubar a latência do modo com prior para a mesma ordem do modo frio. Vale medir os dois
caminhos para quantificar o ganho.

---

## 4. Experimento C — energia (exige hardware adicional)

> **A placa sozinha não fecha esta parte.** Os Experimentos A e B são validados integralmente
> pelo seu ESP32. Este aqui precisa de um instrumento de corrente e, para a parte de rádio, de
> um módulo LoRa, que a placa não tem. Sem eles, a Seção 7 do artigo permanece analítica, o que
> é legítimo desde que declarado como estimativa, que é como está escrito.


A Seção 7 do artigo estima tempo de antena e energia **analiticamente**, pela fórmula do
SX1276. Medir de verdade exige instrumentação:

**Montagem mínima:** um multímetro com faixa de µA/mA em série com a alimentação de 3,3 V da
placa, ou um medidor dedicado (Nordic PPK II, Otii Arc, INA219 via I²C).

**Procedimento:**

1. Meça a corrente com a CPU ociosa (linha de base).
2. Meça durante um laço contínuo de descompressão (`REPS` alto), nos dois modos.
3. Energia por mensagem = (corrente média − linha de base) × 3,3 V × latência por mensagem.
4. Com um módulo LoRa acoplado, meça a corrente durante a transmissão de um quadro com o
   payload original e com o comprimido, e compare com a Tabela 10 do artigo.

O ponto a demonstrar é o balanço: a energia gasta a mais na CPU para comprimir precisa ser
muito menor que a economizada no rádio. Como o rádio consome ~28 mA por centenas de
milissegundos e a CPU consome ~40 mA por dezenas de milissegundos, a conta deve fechar
folgadamente a favor da compressão, mas **medir é o que transforma a estimativa em resultado**.

**Ressalva de método:** uma placa de desenvolvimento tem regulador de tensão, conversor
USB-serial e LEDs que consomem junto com o SoC e poluem a medição. Números tirados de um
devkit servem como indicativo, não como medição de consumo do chip. Para valor publicável,
meça um módulo isolado alimentado direto em 3,3 V, ou desça a corrente de base do devkit e
reporte apenas o **delta** entre ocioso e comprimindo, que é o que interessa ao argumento.

---

## 5. Planilha de registro

Preencha e guarde junto com os resultados; é o que alimenta a tabela do artigo.

| Item | Modo frio | Modo com prior |
|---|---|---|
| Placa e revisão | | |
| Versão do ESP-IDF | | |
| Frequência de CPU | 240 MHz | 240 MHz |
| `.bss` do `gpa_decoder` | | |
| Flash `.text` + `.rodata` | | |
| Latência média (µs) | | |
| Latência mediana (µs) | | |
| Latência p95 (µs) | | |
| Vazão (KB/s) | | |
| Delta de heap (B) | | |
| Folga de pilha (B) | | |
| Round-trip | | |
| Tamanho médio comprimido | | |

---

## 6. Solução de problemas

| Sintoma | Causa provável | Saída |
|---|---|---|
| `gcc` falha sem imprimir erro | pasta do MSYS2 fora do `PATH` | `export PATH="/c/msys64/ucrt64/bin:$PATH"` |
| `region 'dram0_0_seg' overflowed` | modo com prior + Wi-Fi | desligue Wi-Fi/BT; depois `-DGPA_WORK_SIZE=18432` |
| `Guru Meditation` / stack overflow | pilha da tarefa insuficiente | aumente `CONFIG_ESP_MAIN_TASK_STACK_SIZE` |
| Round-trip falha só na placa | vetor desatualizado após trocar o primer | regenere os vetores e recompile |
| Latência com variação alta | interrupções de Wi-Fi ou log serial | desligue o rádio, aumente `REPS` |
| Porta serial não aparece | driver USB-serial ausente | instale CP210x ou CH340 conforme a placa |

---

## 7. Depois de medir

1. Atualize a Tabela 9 do artigo (custos) com os valores reais.
2. Substitua, na Seção 10, a frase de trabalho futuro sobre validação em placa pelos números
   medidos, movendo-a para a Seção 9.
3. Se implementar a otimização do estado pré-aquecido, ela vira uma contribuição nova: o modo
   com prior deixa de ter custo de CPU proibitivo em microcontrolador.
