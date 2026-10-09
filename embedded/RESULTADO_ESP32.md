# Medição no ESP32 físico

Primeira execução do decodificador GPA em hardware real. Substitui as estimativas por
medidas, e responde ao item que o artigo listava como trabalho futuro.

## Ambiente

| Item | Valor |
|---|---|
| Placa | ESP32-D0WDQ6 rev v1.1, dual core, 240 MHz, 520 KB SRAM, 16 MB flash |
| Porta | COM3 (USB-serial CH9102) |
| ESP-IDF | v5.5.5 |
| Otimização | `-Os` (`CONFIG_COMPILER_OPTIMIZATION_SIZE`) |
| Vetores | 12 mensagens held-out de log e telemetria, geradas por `tools/gen_vectors.py` |
| Repetições | 200 por mensagem no modo frio, 10 no modo com prior |
| Data | 3 de agosto de 2026 |

Reproduzir: ver [TESTE_FISICO.md](TESTE_FISICO.md). Saída bruta em
[resultado_esp32.txt](resultado_esp32.txt).

## Resultados

| Métrica | Modo frio | Modo com prior |
|---|---:|---:|
| Compressão média | 58,2 B → 49,4 B (1,18×) | 58,2 B → 16,9 B (**3,44×**) |
| Round-trip | **12/12 bit-exatas** | **12/12 bit-exatas** |
| Latência média | **698 µs** | **47.665 µs (47,7 ms)** |
| Latência mediana | 725 µs | 47.562 µs |
| Vazão equivalente | 81,4 KB/s | 1,2 KB/s |
| RAM estática (`.bss`) | **19.692 B** | 68.852 B |
| RAM dinâmica (heap) | **0 B** | 196.844 B |
| RAM total | **~19,7 KB** | **~265 KB** |
| Flash (`.text` + `.rodata`) | 2.031 B | 3.413 B + primer |
| Folga de pilha | 2.128 B nunca usados | 2.128 B nunca usados |

O `.bss` de 19.692 B reproduz exatamente o valor da análise estática anterior e converge com
as outras duas medições independentes: alocador instrumentado em Rust 19.083 B, `size` no
objeto x86 19.776 B. A linha "decodificador ~19 KB" do artigo está confirmada em hardware.

## O achado principal

**O modo com prior custa 47,7 ms por mensagem, 68 vezes o modo frio.** Praticamente todo esse
tempo, cerca de 47 ms, é reaquecimento do modelo: o decodificador reparsa os 16 KB do primer
com LZ77 e reaprende todos os tokens a cada mensagem. A decodificação em si continua na casa
de centenas de microssegundos.

Isso confirma na placa a previsão feita no PC, e é pior do que a extrapolação inicial de 20 a
40 ms. É o obstáculo prático mais sério do mecanismo central do trabalho.

### Contexto: o balanço energético ainda fecha

Para um enlace LoRaWAN em SF12, a Seção 7 do artigo estima 1,8 s de tempo de antena para a
mensagem comprimida. Os 47,7 ms de CPU representam cerca de 2,7% disso. Estimando o consumo
de CPU em 40 mA a 3,3 V, a compressão gasta cerca de 6,3 mJ para economizar cerca de 167 mJ de
rádio. O balanço permanece amplamente favorável, mas a folga deixou de ser desprezível, e em
enlaces rápidos, como Wi-Fi ou NB-IoT, ela desaparece.

### Ressalva importante sobre a direção da medição

Mediu-se o **decodificador**. Na arquitetura do artigo, o dispositivo **comprime** e o gateway
descomprime. O compressor executa o mesmo aquecimento **mais** a busca de casamentos LZ da
mensagem, então 47,7 ms é um **piso**, não o custo real do lado do dispositivo. Portar o
compressor para C e medi-lo é o próximo passo para fechar essa lacuna.

## O que precisou mudar para caber

Duas descobertas de engenharia que não apareciam na análise estática:

**1. As tabelas LZ não cabem no segmento estático.** O modo com prior precisa de 192 KB de
tabelas de hash (`LZ_head` 64 KB e `LZ_prev` 128 KB). O ESP32 clássico limita os dados
estáticos a cerca de 176 KB, e o link falhou com `region 'dram0_0_seg' overflowed by 100376
bytes`. **Não é problema de Wi-Fi**: é o tamanho do segmento. A solução foi alocar as duas
tabelas do heap, que alcança regiões de memória indisponíveis para dados estáticos. O caminho
frio permanece 100% estático, sem `malloc`, nos 19,7 KB.

**2. A ordem de alocação importa.** O heap do ESP32 é fragmentado em regiões, a maior com
157 KB. Pedir primeiro a tabela menor (64 KB) consumia parte da região grande e fazia o pedido
seguinte, de 128 KB, falhar por falta de bloco contíguo. Alocando a **maior primeiro**, as
duas cabem. O sintoma original era enganoso: o decodificador retornava erro e a saída acusava
falha de round-trip, quando o problema era memória.

Também reduzimos `GPA_WORK_SIZE` de 48 KB para 18.432 B, ajustado ao primer real de 16 KB mais
a maior mensagem, liberando 30 KB de dados estáticos.

## Conclusão prática

O decodificador **frio** é plenamente viável em microcontrolador: 19,7 KB de RAM, zero
alocação, 698 µs por mensagem, integridade perfeita. É o que o artigo afirmava, agora
verificado no silício.

O modo **com prior**, que é a contribuição do trabalho, roda e é bit-exato, mas ao custo de
265 KB de RAM e 47,7 ms por mensagem. Cabe no ESP32 e em nada menor: um nRF52832, com 64 KB de
RAM, está fora de questão. Como está, o mecanismo é demonstrável, não implantável.

## O conserto, e por que ele vale muito

Aquecer o modelo uma vez e reutilizar o estado, em vez de reprocessar o primer a cada mensagem.
O estado aquecido tem cerca de 19,7 KB, é determinístico e pode ser **calculado fora do
dispositivo e gravado como constante em flash**. Nesse desenho o decodificador não precisa de
tabela LZ alguma, porque nunca reparsa o primer: ele carrega o estado pronto e mantém apenas os
bytes do primer para os casamentos copiarem.

Projeção: RAM cai de 265 KB para cerca de 36 KB (modelo mais primer), latência cai de 47,7 ms
para a ordem de 700 µs, e o mecanismo passa a caber em microcontroladores de 64 KB. É a mesma
correção que o [estudo de contêiner por blocos](../estudo_blocos/RESULTADO.md) exige para
viabilizar acesso aleatório, o que a torna o item de maior valor do projeto.

## Pendente

- Latência e footprint do **compressor** no alvo (exige portar o compressor para C).
- Medição de **energia** com instrumento de corrente, e de tempo de antena com módulo LoRa.
- Repetir com primer de domínio real, dos datasets do artigo, em vez do corpus sintético.
