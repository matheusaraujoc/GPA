# Fase 1 — Validação Fundamental

Objetivo: provar que o algoritmo está correto.

## Testes

### Arquivos aleatórios

* 32 B
* 64 B
* 128 B
* 256 B
* 512 B
* 1 KB
* 4 KB
* 16 KB

Pode ir até 2mb para criterio de curiosidade

Gerados com:

```python
os.urandom()
```

Esperado:

* Compressão ≈ 100%
* Nunca corromper dados

---

### Teste de integridade

Para cada arquivo:

```python
SHA256(original)
SHA256(descomprimido)
```

Esperado:

```text
100% idênticos
```

---

# Fase 2 — Cenários Reais de IoT

Objetivo: medir desempenho no caso de uso principal.

## MQTT

Payloads:

```json
{"temp":25.3}
```

```json
{"temp":25.3,"hum":81}
```

```json
{"temp":25.3,"hum":81,"press":1012}
```

Tamanhos:

* 32 B
* 64 B
* 128 B
* 256 B

---

## Telemetria Industrial

```json
{
  "device":"A01",
  "status":"OK",
  "temp":26.3
}
```

Simular:

* 100 mensagens
* 1.000 mensagens
* 10.000 mensagens

---

## GPS

```json
{
  "lat":-2.9,
  "lon":-41.7,
  "speed":63
}
```

---

## Sensores

```json
{
  "sensor":12,
  "value":456
}
```

---

### Métricas

Registrar:

| Métrica             | Valor |
| ------------------- | ----- |
| Tamanho Original    |       |
| Tamanho GPA         |       |
| Economia (%)        |       |
| Tempo Compressão    |       |
| Tempo Descompressão |       |
| RAM Pico            |       |

---

# Fase 3 — Competição Direta

Objetivo: provar vantagem contra soluções existentes.

Comparar:

* GPA
* Deflate
* Gzip
* Zstd nível 1
* Zstd nível 3
* LZ4

O concorrente natural do GPA não é LZMA.

É LZ4.

LZ4 domina cenários de:

* IoT
* Streaming
* Redes
* Jogos
* Tempo real

Observação: Nos meus testes manuais, o menor arquivo que o GPA conseguiu comprimir foi um arquivo de 28bytes, ele comprimiu 3,57% do tamanho, deixando com 27 bytes. E descomprimiu de forma satisfatoria e sem perda de dados. Em tamanhos especificos a baixo disso, ele não compactou nada mais. E em alguns casos inflou em 1byte.

Logs do processo:


--- INICIANDO COMPRESSÃO FAST-START ---
Tamanho Original: 28 Bytes
Executando compressão nativa em Rust...
Lendo arquivo original: C:/Users/Matheus/Desktop/Testes GPA/28 bytes.txt...
Tamanho Original: 28 bytes
Executando prÃ©-pass LZ77 (janela 4KB + lazy match)...
Codificando via PPM-D Ordem-2 e HistÃ³rico MTF...
------------------------------------------------------------
Tamanho Comprimido: 27 bytes
ReduÃ§Ã£o de Tamanho: 3.57%
Tempo Decorrido: 0.0007 segundos
OperaÃ§Ã£o concluÃ­da com sucesso!
------------------------------------------------------------
------------------------------
Tamanho Final: 27 Bytes
Redução de Tamanho: 3.57%
Tempo Decorrido: 0.04 segundos

--- INICIANDO DESCOMPRESSÃO ---
Arquivo GPA: 27 Bytes
Executando descompressão nativa em Rust...
Lendo arquivo comprimido: C:/Users/Matheus/Desktop/Testes GPA/teste13.gpa...
Decodificando bits com PPM-D Ordem-2...
Reconstruindo fluxo original LZ77...
------------------------------------------------------------
Tamanho Restaurado: 28 bytes
Tempo Decorrido: 0.0007 segundos
OperaÃ§Ã£o concluÃ­da com sucesso!
------------------------------------------------------------
------------------------------
Tamanho Restaurado: 28 Bytes
Tempo Decorrido: 0.04 segundos

---

## Score

Criar um índice:

```text
Score =
Compressão × Peso
+
Velocidade × Peso
+
RAM × Peso
```

Exemplo:

```text
Compressão = 40%
Velocidade = 40%
RAM = 20%
```

---

# Fase 4 — Stress Test

Objetivo: encontrar limites.

## Arquivos

* 1 KB
* 4 KB
* 16 KB
* 64 KB
* 256 KB
* 1 MB
* 10 MB

---

## Tipos

### JSON

### CSV

### TXT

### HTML

### Código Python

### Código C

### Logs

### Aleatório

---

Boa ideia. Como o GPA tem foco em **IoT, telemetria e mensagens pequenas**, o uso de RAM não deve ser apenas uma métrica secundária. Ele deve virar uma seção principal do relatório.

Eu substituiria a antiga Fase 5 por uma **Análise Profunda de Memória**.

# Fase 5 — Análise de Memória (RAM)

## Objetivo

Determinar:

* Quanto RAM o GPA realmente necessita.
* Como a RAM cresce conforme o tamanho dos dados.
* Quanto da RAM é algoritmo e quanto é overhead.
* Comparação com algoritmos concorrentes.

---

## Métricas Coletadas

### RAM Pico

Maior valor observado durante a execução.

Exemplo:

| Arquivo | GPA    |
| ------- | ------ |
| 64 B    | 3.5 MB |
| 1 KB    | 3.5 MB |
| 16 KB   | 5.7 MB |
| 256 KB  | 29 MB  |
| 1 MB    | 102 MB |

---

### RAM por KB Processado

Fórmula:

```text
RAM Pico / Tamanho Original
```

Exemplo:

```text
102 MB / 1 MB = 102
```

Resultado:

```text
102 bytes de RAM para cada byte processado
```

Essa métrica mostra a eficiência estrutural do algoritmo.

---

### Crescimento da RAM

Gerar gráfico:

```text
Tamanho Arquivo
↓
RAM Utilizada
```

Objetivo:

Identificar se o crescimento é:

* Linear
* Logarítmico
* Exponencial
* Constante

---

### RAM Compressão

Medir separadamente:

| Arquivo       | RAM |
| ------------- | --- |
| Compressão    |     |
| Descompressão |     |

Muitos algoritmos usam muito mais RAM para comprimir do que para descomprimir.

---

# Seção Especial: Eficiência de Memória

Criar um ranking:

## Compressão por MB de RAM

Fórmula:

```text
Bytes economizados / RAM utilizada
```

Exemplo:

```text
Arquivo: 1 MB

Original: 1.000 KB
Comprimido: 350 KB

Economia:
650 KB

RAM:
50 MB

Eficiência:
13 KB economizados por MB de RAM
```

---

## Índice GPA-RAM

Uma métrica própria.

Fórmula:

```text
GPA-RAM =
(% Compressão × Velocidade)
÷ RAM
```

Permite comparar algoritmos diferentes em uma única escala.

---

# Análise de Escalabilidade

Executar:

| Tamanho |
| ------- |
| 32 B    |
| 64 B    |
| 128 B   |
| 256 B   |
| 512 B   |
| 1 KB    |
| 4 KB    |
| 16 KB   |
| 64 KB   |
| 256 KB  |
| 1 MB    |
| 5 MB    |
| 10 MB   |

E registrar:

| Tamanho | RAM |
| ------- | --- |
| 32 B    |     |
| 64 B    |     |
| 128 B   |     |
| ...     |     |
| 10 MB   |     |

---

# Perguntas-Chave

O relatório deve responder:

### 1.

A RAM cresce linearmente?

```text
RAM ∝ tamanho
```

ou

```text
RAM ∝ tamanho²
```

---

### 2.

Qual é o tamanho mínimo viável?

Exemplo:

```text
Até 16 KB:
RAM < 10 MB

Até 64 KB:
RAM < 20 MB
```

Mas o objetivo é usar a menor quantidade de ram possível para comprimir e descomprir. Por exemplo, queria usar 32kb de ram para comprimir 4kb, e descomprimir depois. Esse é um plano secundário.

---

### 3.

Existe um ponto de saturação?

Exemplo:

```text
Até 256 KB funciona bem.

Acima disso o consumo explode.
```

---

# Destaque Executivo

No início do relatório eu colocaria um quadro específico:

## Destaques de Memória

| Métrica        | GPA                 |
| -------------- | ------------------- |
| RAM mínima     |                     |
| RAM média      |                     |
| RAM máxima     |                     |
| Crescimento    | Linear / Não Linear |
| RAM por KB     |                     |
| Melhor cenário |                     |
| Pior cenário   |                     |

---

A principal hipótese que eu tento provar é:

> "O GPA não é um compressor universal. Ele é um compressor especializado para mensagens pequenas (32 B a 4 KB), onde consegue melhor relação entre compressão, latência e simplicidade operacional do que os compressores tradicionais."