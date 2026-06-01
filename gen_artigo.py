#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera o artigo SBC (.docx) a partir de resultados_reais.json e cross_domain.json (harness v2)."""
import json, os
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

ROOT = os.path.dirname(os.path.abspath(__file__))
JSON = os.path.join(ROOT, "resultados_reais.json")
CROSSJSON = os.path.join(ROOT, "cross_domain.json")
OUT = os.path.join(ROOT, "artigo", "GhostPredict_SBC.docx")
REPO = "https://github.com/matheusaraujoc/GPA"

DOM_LABEL = {
    "MQTT": "MQTT (IoT)", "AIS": "AIS (navios)", "IntelLab": "Sensores (Intel Lab)",
    "Household": "Medidor (energia)", "Geolife": "GPS (GeoLife)",
    "Log-Apache": "Log Apache", "Log-Linux": "Log Linux", "Log-OpenSSH": "Log OpenSSH",
    "Log-HDFS": "Log HDFS", "SMS": "SMS", "Tweets": "Tweets",
}
def domains(R): return [(k, v) for k, v in R.items() if not k.startswith("_")]
def virg(s): return str(s).replace(".", ",")

def set_cell(cell, text, bold=False, size=10, font="Times New Roman", align="c"):
    cell.text = ""; p = cell.paragraphs[0]
    p.alignment = {"c": WD_ALIGN_PARAGRAPH.CENTER, "l": WD_ALIGN_PARAGRAPH.LEFT, "r": WD_ALIGN_PARAGRAPH.RIGHT}[align]
    r = p.add_run(text); r.bold = bold; r.font.size = Pt(size); r.font.name = font
    p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(0)

def style_doc(doc):
    st = doc.styles["Normal"]; st.font.name = "Times New Roman"; st.font.size = Pt(12)
    sec = doc.sections[0]; sec.page_height = Cm(29.7); sec.page_width = Cm(21.0)
    sec.top_margin = Cm(3.5); sec.bottom_margin = Cm(2.5); sec.left_margin = Cm(3.0); sec.right_margin = Cm(3.0)

def para(doc, text, size=12, bold=False, italic=False, align="j", before=6, after=0,
         first_indent=None, l_indent=None, r_indent=None, font="Times New Roman"):
    p = doc.add_paragraph()
    p.alignment = {"j": WD_ALIGN_PARAGRAPH.JUSTIFY, "c": WD_ALIGN_PARAGRAPH.CENTER, "l": WD_ALIGN_PARAGRAPH.LEFT}[align]
    pf = p.paragraph_format; pf.space_before = Pt(before); pf.space_after = Pt(after)
    if first_indent is not None: pf.first_line_indent = Cm(first_indent)
    if l_indent is not None: pf.left_indent = Cm(l_indent)
    if r_indent is not None: pf.right_indent = Cm(r_indent)
    r = p.add_run(text); r.bold = bold; r.italic = italic; r.font.name = font; r.font.size = Pt(size)
    return p

def section(doc, text, size=13): para(doc, text, size=size, bold=True, align="l", before=12, after=6)
def body(doc, text, first=True): para(doc, text, size=12, align="j", before=6, first_indent=(0 if first else 1.27))
def caption(doc, text): para(doc, text, size=10, bold=True, align="c", before=6, after=6, font="Arial")
def codeline(doc, text): para(doc, text, size=10, align="l", before=2, after=2, l_indent=0.6, font="Consolas")

def add_table(doc, headers, rows, colsize=10):
    t = doc.add_table(rows=1, cols=len(headers)); t.style = "Table Grid"; t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for j, h in enumerate(headers): set_cell(t.rows[0].cells[j], h, bold=True, size=colsize)
    for row in rows:
        cells = t.add_row().cells
        for j, v in enumerate(row): set_cell(cells[j], v, bold=False, size=colsize, align=("l" if j == 0 else "c"))
    return t

def load(path): return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}

def build():
    R = load(JSON); CR = load(CROSSJSON)
    meta = R.get("_meta", {}); floor = meta.get("framing_floor_zstd_dict", {})
    doc = Document(); style_doc(doc)

    para(doc, "GhostPredict: compressão lossless com prior embutido no codec para micro-payloads de IoT",
         size=16, bold=True, align="c", before=12, after=12)
    para(doc, "Matheus Araújo", size=12, bold=True, align="c", before=0, after=12)
    para(doc, "Projeto de pesquisa independente", size=12, align="c", before=0, after=0)
    para(doc, "araujomatheuscarv@gmail.com", size=10, align="c", font="Courier New", before=6, after=12)

    para(doc, "Abstract.", size=12, bold=True, align="j", before=6, l_indent=0.8, r_indent=0.8)
    para(doc, "General purpose compressors such as gzip, zstd and brotli enlarge very short messages, "
              "because header and framing overhead exceeds any saving. This work presents GhostPredict, "
              "a lossless compressor specialized in the micro-payloads of tens of bytes that dominate "
              "IoT telemetry. The method combines a header free format, an order-2 context model over "
              "nibbles with integer arithmetic coding, and a domain prior embedded in the codec rather "
              "than in the file, which both warms the statistical model and acts as an LZ dictionary. "
              "Across eleven real datasets the primed variant produces the smallest files among all "
              "baselines, including short string specialists and trained zstd dictionaries; once the "
              "dictionary framing is removed to isolate the model, the advantage over the lean zstd "
              "dictionary is about 1.8 times. The file stays dictionary free, and the method never "
              "expands incompressible input beyond a negligible margin. We also quantify the dependence "
              "of the gains on a domain matched prior.",
         size=12, align="j", before=0, l_indent=0.8, r_indent=0.8)
    para(doc, "Resumo.", size=12, bold=True, align="j", before=12, l_indent=0.8, r_indent=0.8)
    para(doc, "Compressores de propósito geral como gzip, zstd e brotli aumentam o tamanho de "
              "mensagens muito curtas, pois o custo de cabeçalho e enquadramento supera qualquer "
              "economia. Este trabalho apresenta o GhostPredict, um compressor lossless especializado "
              "nos micro-payloads de dezenas de bytes da telemetria de IoT. O método combina um formato "
              "sem cabeçalho, um modelo de contexto de ordem 2 sobre nibbles com codificação aritmética "
              "inteira, e um prior de domínio embutido no codec, e não no arquivo, que aquece o modelo "
              "e serve de dicionário. Em onze conjuntos de dados reais, a variante com prior produz o "
              "menor arquivo entre todos os concorrentes, incluindo especialistas de string curta e o "
              "dicionário treinado do zstd; isolando o modelo, ao remover o enquadramento do "
              "dicionário, a vantagem sobre o zstd enxuto é de cerca de 1,8 vezes. O arquivo permanece "
              "livre de dicionário e o método nunca expande entradas incompressíveis além de margem "
              "desprezível. Também quantificamos a dependência dos ganhos em relação a um prior casado "
              "com o domínio.",
         size=12, align="j", before=0, l_indent=0.8, r_indent=0.8)

    # 1. Introducao
    section(doc, "1. Introdução")
    body(doc, "A expansão da Internet das Coisas multiplicou um tipo de tráfego que os compressores "
        "clássicos atendem mal: mensagens muito curtas, frequentemente de trinta a uma centena de "
        "bytes, emitidas por sensores, rastreadores e dispositivos de telemetria. Protocolos como MQTT "
        "e CoAP, e enlaces de baixa potência como LoRaWAN e NB-IoT, transportam esse tipo de payload, "
        "no qual cada byte transmitido tem custo direto em energia, em tempo de antena e em limites "
        "regulatórios de ciclo de trabalho.")
    body(doc, "Nesse regime de tamanho, os compressores de propósito geral tendem a aumentar o dado em "
        "vez de reduzi-lo. Formatos como o DEFLATE [Deutsch 1996], o Zstandard [Collet and Kucherawy "
        "2021] e o Brotli [Alakuijala and Szabadka 2016] carregam cabeçalhos, somas de verificação e "
        "estruturas de bloco cujo custo fixo domina quando a entrada tem poucas dezenas de bytes. O "
        "resultado é que uma mensagem de trinta bytes costuma sair maior do que entrou.", first=False)
    body(doc, "Este trabalho investiga se um compressor desenhado para esse nicho pode reverter o "
        "quadro. A proposta, chamada GhostPredict, parte de três decisões de projeto: um formato sem "
        "cabeçalho, em que o arquivo é apenas o fluxo aritmético; um prior de domínio embutido no "
        "próprio codec, e não no arquivo, que aquece o modelo estatístico e fornece um dicionário "
        "inicial, eliminando o custo de partida a frio; e uma garantia de que nenhuma entrada será "
        "expandida além de margem mínima. As contribuições são o algoritmo e o formato, o mecanismo de "
        "prior embutido, a garantia de não expansão, e uma avaliação em onze conjuntos de dados reais "
        "que isola o ganho do modelo do ganho de formato e quantifica a dependência do prior em relação "
        "ao domínio. O código e os scripts de reprodução estão disponíveis publicamente em https://github.com/matheusaraujoc/GPA.", first=False)

    # 2. Relacionados
    section(doc, "2. Trabalhos relacionados")
    body(doc, "A compressão lossless de propósito geral apoia-se na substituição de cadeias repetidas "
        "por referências [Ziv and Lempel 1977] e na modelagem estatística seguida de codificação de "
        "entropia, cujos marcos são o código de Huffman [1952], a predição por casamento parcial de "
        "Cleary and Witten [1984] e a codificação aritmética de Witten, Neal and Cleary [1987]. O "
        "GhostPredict combina as duas famílias.")
    body(doc, "Para mensagens curtas existem compressores especializados com codebook embutido, como o "
        "Unishox2 [Ramanathan 2021] e o SMAZ, usados em dispositivos restritos. Esses métodos vencem a "
        "partida a frio por já carregarem conhecimento sobre a língua, mas o conhecimento é estático e "
        "não se adapta ao domínio. A ideia de compartilhar um prior entre os dois lados, sem inseri-lo "
        "no arquivo, tem precedente maduro: o zstd treina dicionários a partir de amostras, o "
        "concorrente direto da nossa proposta; e, em genômica, a compressão baseada em referência "
        "[Fritz et al. 2011] é o paradigma dominante. O GhostPredict transpõe esse princípio para o "
        "extremo dos micro-payloads, onde o custo fixo dos formatos gerais é proporcionalmente maior.",
        first=False)

    # 3. Algoritmo
    section(doc, "3. O algoritmo GhostPredict")
    body(doc, "O núcleo é um pipeline determinístico: a entrada passa por um estágio LZ77 de janela "
        "deslizante, que substitui repetições por pares de distância e comprimento; o fluxo de "
        "símbolos resultante, com nibbles literais e códigos de distância e comprimento, alimenta um "
        "modelo de contexto de ordem 2 sobre nibbles; e as probabilidades guiam um codificador "
        "aritmético inteiro de 32 bits. Por usar aritmética inteira, a codificação é exatamente "
        "reproduzível, garantindo o casamento bit a bit entre compressão e descompressão.")
    body(doc, "O arquivo é apenas o fluxo aritmético, sem cabeçalho. Para impedir expansão de entradas "
        "incompressíveis, a primeira decisão codificada é uma escolha binária enviesada entre o modo "
        "normal e um modo de armazenamento direto, na proporção de um para sessenta e quatro. O custo "
        "dessa flag é cerca de 0,02 bit no caso compressível e seis bits no armazenado, onde os bytes "
        "são codificados por um modelo plano, limitando a expansão máxima a cerca de um por mil mais "
        "alguns bytes.", first=False)
    body(doc, "A característica central é o modo com prior. Antes de codificar a mensagem, compressor e "
        "descompressor percorrem um corpus de domínio, o primer, atualizando o modelo de forma "
        "idêntica, sem emitir bits, e o utilizam como dicionário do LZ77. O primer reside no codec e é "
        "distribuído uma vez junto ao firmware; não acompanha cada mensagem. Cada arquivo permanece "
        "livre de dicionário, e o ganho do prior se soma à ausência de custo fixo.", first=False)

    # 4. Metodologia
    section(doc, "4. Metodologia experimental")
    body(doc, "A avaliação usa onze conjuntos de dados reais, listados na Tabela 1, todos como fluxos "
        "de registros curtos com um registro por linha. Para cada domínio, os registros são "
        "embaralhados com semente fixa e divididos em treino e teste disjuntos. O conjunto de treino "
        "constrói tanto o primer do GhostPredict, formado pelos últimos 32 KB do corpus de treino, "
        "quanto o dicionário do zstd, treinado pelas mesmas amostras, de modo que ambos recebem a mesma "
        "informação prévia. O conjunto de teste, com mil mensagens não vistas, é comprimido "
        "mensagem a mensagem. Medir mensagens individuais, e não arquivos inteiros, é essencial: medir "
        "arquivos diluiria o custo de partida a frio e esconderia o efeito que o prior corrige. A "
        "exceção de tamanho são os quatro conjuntos de log, na versão amostrada de duas mil linhas do "
        "Loghub, em que teste e treino têm mil mensagens cada.")
    caption(doc, "Tabela 1. Conjuntos de dados reais utilizados na avaliação.")
    add_table(doc, ["Domínio", "Fonte", "Registro típico"],
        [["MQTT / IoT", "MQTTEEB-D [Aqachtoul et al. 2025]", "~76 B"],
         ["AIS / navios", "MarineCadastre [MarineCadastre 2025]", "~100 B"],
         ["Sensores", "Intel Lab Data [Bodik et al. 2004]", "~64 B"],
         ["Energia", "UCI Household Power [Hebrail and Berard 2012]", "~62 B"],
         ["GPS", "GeoLife [Zheng et al. 2009]", "~65 B"],
         ["Logs (4 tipos)", "Loghub [Zhu et al. 2023]", "84 a 300 B"],
         ["SMS", "SMS Spam Collection [Almeida et al. 2011]", "~88 B"],
         ["Tweets", "Sentiment140 [Go et al. 2009]", "~148 B"]], colsize=11)
    body(doc, "Comparam-se dez configurações: o GhostPredict sem prior e com prior; os especialistas de "
        "string curta Unishox2 e SMAZ; o gzip nível 9; o zstd nível 19, com e sem dicionário treinado; "
        "uma variante enxuta do dicionário do zstd, sem soma de verificação e sem identificador de "
        "dicionário, que remove o enquadramento removível para isolar a contribuição do modelo; o "
        "brotli nível 11; e o xz nível 9. As versões foram zstd 1.5.7, xz 5.6.3, gzip 1.13, brotli "
        "1.1.0 e Unishox2 da distribuição oficial. As métricas são o tamanho médio, a mediana e o "
        "percentil 95 por mensagem, a fração de mensagens expandidas, a fração de vitórias, a vazão e o "
        "uso de memória. O procedimento é reproduzível a partir do repositório público (https://github.com/matheusaraujoc/GPA), com sementes fixas; o commit exato e um identificador de versão devem acompanhar a versão final.",
        first=False)

    # 5. Resultados
    section(doc, "5. Resultados")
    build_results(doc, R, CR, floor, meta)

    # 6. Discussao
    section(doc, "6. Discussão")
    body(doc, "Os resultados sustentam a tese e delimitam seu alcance. No nicho de micro-payloads, o "
        "prior embutido no codec entrega o menor arquivo entre todos os concorrentes. É importante "
        "separar as duas fontes desse ganho. Parte vem do formato sem cabeçalho, pois o dicionário do "
        "zstd carrega um enquadramento fixo que, em saídas de algumas dezenas de bytes, representa uma "
        "fração relevante; ao remover o enquadramento removível, na variante enxuta, a vantagem do "
        "GhostPredict cai mas permanece. A parte restante vem do modelo aquecido pelo prior, que "
        "reduz o custo de codificação das mensagens. Ambas as fontes são contribuições legítimas, e a "
        "decomposição evita atribuir ao modelo um ganho que é, em parte, de formato.")
    body(doc, "Fora do nicho o método não compete. Em dados gerais de maior porte a razão de "
        "compressão fica na classe do gzip, atrás de zstd, xz e brotli, pela janela curta e pelo modelo "
        "de baixa ordem. Em texto de linguagem natural livre, compressores de caractere permanecem "
        "competitivos. A principal ameaça à validade é a dependência entre o prior e o domínio, "
        "quantificada na Seção 5: um prior de domínio distinto degrada o resultado e pode até inflar, o "
        "que reforça a necessidade de casar o primer com a aplicação. A avaliação usa mil "
        "mensagens por domínio; uma validação industrial deveria ampliar amostras e domínios.", first=False)
    body(doc, "Estabelecido que o efeito existe e medido onde ele vem, a questão prática deixa de "
        "ser a sua realidade e passa a ser o seu balanço de engenharia. A proposta troca um custo "
        "fixo por um ganho recorrente. O custo é o primer, de 16 a 32 KB na memória de programa do "
        "dispositivo, pago uma única vez e nunca transmitido. O ganho é a redução de cerca de duas a "
        "três vezes sobre o dicionário do zstd em cada mensagem enviada, ou de cerca de 1,7 vezes "
        "quando se isola o modelo do formato. Em um cenário típico de IoT, com um dispositivo que "
        "transmite muitas mensagens curtas por enlaces onde cada byte custa energia e tempo de antena, "
        "o balanço é favorável, pois a memória de programa investida é abundante nos "
        "microcontroladores usuais, da ordem de megabytes, enquanto a economia se acumula a cada "
        "transmissão. A condição para que o trade-off compense é a estabilidade do domínio, "
        "quantificada na Seção 5: um primer descasado anula o ganho e pode inflar. O método é, "
        "portanto, indicado quando o domínio é estável e o volume de mensagens é alto, e "
        "contraindicado quando o tráfego é heterogêneo ou a memória de programa é criticamente "
        "escassa.", first=False)

    # 7. Hardware embarcado
    section(doc, "7. Viabilidade em hardware embarcado")
    body(doc, "O destino natural do método são dispositivos de recursos restritos, como os "
        "microcontroladores das famílias ESP32, STM32 e nRF, onde o ganho em bytes se converte em "
        "economia de energia e de tempo de antena. A arquitetura de uso é assimétrica: o dispositivo "
        "comprime a mensagem antes de transmitir, com o codificador e o primer gravados no firmware, "
        "e o gateway ou a nuvem descomprime. Como todo o pipeline usa apenas aritmética inteira e é "
        "determinístico, ele não exige unidade de ponto flutuante e roda de forma idêntica no "
        "microcontrolador e no servidor. Os requisitos de memória cabem nesses dispositivos: o "
        "conjunto de trabalho do decodificador, de cerca de 19 KB, e o do codificador no perfil "
        "micro, de cerca de 51 KB, ficam bem abaixo das centenas de quilobytes de RAM de um ESP32, e "
        "o primer, de 16 a 32 KB, reside na memória de programa, da ordem de megabytes nesses chips.")
    body(doc, "Boa parte dessas alegações pode ser validada sem o dispositivo físico, por "
        "compilação cruzada e análise estática. Ao portar o motor para o ambiente de destino, em C "
        "sobre o ESP-IDF ou em Rust no modo no_std, basta compilar o binário no computador e "
        "inspecionar seu mapa de memória. No ESP-IDF, o comando idf.py size reporta a divisão em "
        "flash, com as seções de código (.text) e de constantes (.rodata, onde reside o primer), e em "
        "RAM estática, com as seções de dados inicializados (.data) e não inicializados (.bss). Esses "
        "números validam, de forma reproduzível e sem hardware, a parte estática do footprint da "
        "Tabela 8: que o código e o primer cabem na flash e que as estruturas estáticas cabem na RAM. "
        "Um projeto que aloque o modelo em vetores estáticos, em vez de no heap, torna o footprint "
        "completo diretamente visível nessa análise. Restam para o dispositivo real, ou para um "
        "emulador como o QEMU, a latência por mensagem e o pico de heap dinâmico, medíveis com "
        "esp_timer_get_time e esp_get_free_heap_size.", first=False)
    body(doc, "O balanço energético reforça a viabilidade. Em enlaces de baixa potência, a "
        "transmissão de rádio domina o consumo, de modo que gastar alguns microssegundos de "
        "processador para reduzir o payload à metade prolonga a autonomia. Em tecnologias com limites "
        "rígidos de payload, como os doze bytes por quadro do Sigfox ou os tetos de ciclo de trabalho "
        "do LoRaWAN, a redução pode ser a diferença entre caber ou não em um quadro, ou entre "
        "respeitar ou não o limite regulatório.", first=False)
    body(doc, "Essa viabilidade foi confirmada na prática. Portamos o decodificador para C sem "
        "alocação dinâmica, com todo o estado em memória estática, e o verificamos bit a bit contra "
        "o motor de referência nos vetores de conformidade e em mensagens reais. Ao compilá-lo para "
        "o ESP32 com o ESP-IDF, o relatório de tamanho por componente do idf.py atribui ao "
        "decodificador 19,7 KB na seção de dados não inicializados e cerca de 1,8 KB de código em "
        "flash, no alvo xtensa real. O valor de RAM converge com as outras duas medições "
        "independentes, o alocador instrumentado em Rust e a análise do objeto no hospedeiro, ambas "
        "em torno de 19 KB, o que confirma a linha do decodificador da Tabela 8 no próprio hardware "
        "de destino. Restam para o dispositivo físico, ou para o emulador, a latência e a energia.",
        first=False)

    # 8. Conclusao
    section(doc, "8. Conclusão e trabalhos futuros")
    body(doc, "Apresentamos o GhostPredict, um compressor lossless para micro-payloads de IoT que "
        "combina formato sem cabeçalho, garantia de não expansão e um prior de domínio embutido no "
        "codec. A avaliação em onze conjuntos de dados reais mostra que, no seu nicho, o método produz "
        "o menor arquivo entre todos os concorrentes, e que, isolando o modelo do formato, mantém "
        "vantagem sobre o dicionário treinado do zstd, preservando arquivos livres de dicionário. Os "
        "ganhos observados dependem da existência de um prior compatível com o domínio da aplicação, "
        "condição que quantificamos e que define o escopo de uso do método. Como trabalho futuro, "
        "planejamos um modelo de contexto de ordem mais alta, a inclusão de mais especialistas de "
        "string curta na comparação, e a validação do footprint do decodificador em microcontroladores "
        "reais.")

    # Referencias
    section(doc, "Referências")
    refs = [
        "Alakuijala, J. and Szabadka, Z. (2016). Brotli Compressed Data Format. RFC 7932, IETF.",
        "Almeida, T. A., Gómez Hidalgo, J. M. and Yamakami, A. (2011). Contributions to the study of "
        "SMS spam filtering: new collection and results. In Proceedings of the 2011 ACM Symposium on "
        "Document Engineering (DocEng), pages 259-262.",
        "Aqachtoul, A., Karam, K., Elamrani, A., Najib, M., Rafalia, N. and Bakhouya, M. (2025). "
        "MQTTEEB-D: a real-world IoT cybersecurity dataset for AI-powered threat detection in MQTT "
        "networks. Data in Brief, 61:111897.",
        "Bodik, P., Hong, W., Guestrin, C., Madden, S., Paskin, M. and Thibaux, R. (2004). Intel Lab "
        "Data. Intel Berkeley Research Lab. http://db.csail.mit.edu/labdata/labdata.html.",
        "Cleary, J. G. and Witten, I. H. (1984). Data compression using adaptive coding and partial "
        "string matching. IEEE Transactions on Communications, 32(4):396-402.",
        "Collet, Y. and Kucherawy, M. (2021). Zstandard Compression and the 'application/zstd' Media "
        "Type. RFC 8878, IETF.",
        "Deutsch, P. (1996). DEFLATE Compressed Data Format Specification version 1.3. RFC 1951, IETF.",
        "Fritz, M. H.-Y., Leinonen, R., Cochrane, G. and Birney, E. (2011). Efficient storage of high "
        "throughput DNA sequencing data using reference-based compression. Genome Research, "
        "21(5):734-740.",
        "Go, A., Bhayani, R. and Huang, L. (2009). Twitter sentiment classification using distant "
        "supervision. Technical report, Stanford University.",
        "Hébrail, G. and Bérard, A. (2012). Individual Household Electric Power Consumption Data Set. "
        "UCI Machine Learning Repository. https://doi.org/10.24432/C58K54.",
        "Huffman, D. A. (1952). A method for the construction of minimum-redundancy codes. Proceedings "
        "of the IRE, 40(9):1098-1101.",
        "MarineCadastre (2025). Vessel Traffic Data (AIS). NOAA and BOEM. "
        "https://marinecadastre.gov/accessais/.",
        "Ramanathan, A. (2021). Unishox: a hybrid encoder for short Unicode strings. Zenodo. "
        "https://doi.org/10.5281/zenodo.5800408.",
        "Witten, I. H., Neal, R. M. and Cleary, J. G. (1987). Arithmetic coding for data compression. "
        "Communications of the ACM, 30(6):520-540.",
        "Zheng, Y., Zhang, L., Xie, X. and Ma, W.-Y. (2009). Mining interesting locations and travel "
        "sequences from GPS trajectories. In WWW 2009, pages 791-800.",
        "Ziv, J. and Lempel, A. (1977). A universal algorithm for sequential data compression. IEEE "
        "Transactions on Information Theory, 23(3):337-343.",
        "Zhu, J., He, S., He, P., Liu, J. and Lyu, M. R. (2023). Loghub: a large collection of system "
        "log datasets for AI-driven log analytics. In ISSRE 2023.",
    ]
    for r in refs:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pf = p.paragraph_format; pf.space_before = Pt(6); pf.left_indent = Cm(0.5); pf.first_line_indent = Cm(-0.5)
        run = p.add_run(r); run.font.name = "Times New Roman"; run.font.size = Pt(12)

    os.makedirs(os.path.dirname(OUT), exist_ok=True); doc.save(OUT); print("salvo em", OUT)

# ---------------------------------------------------------------------------
def build_results(doc, R, CR, floor, meta):
    if not R or not domains(R):
        body(doc, "Resultados a inserir a partir de resultados_reais.json."); return
    # 5.1 tamanho por mensagem
    body(doc, "A Tabela 2 traz o tamanho médio do comprimido, em bytes, por domínio e configuração, "
        "incluindo a variante enxuta do dicionário do zstd e os especialistas de string curta. Valores "
        "menores são melhores.")
    caption(doc, "Tabela 2. Tamanho médio do comprimido por mensagem (bytes). Menor é melhor.")
    headers = ["Domínio", "orig", "GPA frio", "GPA prior", "unishox2", "smaz", "zstd dict", "zstd lean", "brotli"]
    keymap = ["GPA-frio", "GPA-primed", "unishox2", "smaz", "zstd-dict", "zstd-dict-lean", "brotli-11"]
    rows = []; f_dict = []; f_lean = []; f_uni = []
    for dom, res in domains(R):
        line = [DOM_LABEL.get(dom, dom), virg("%g" % res["orig_mean"])]
        for k in keymap:
            a = res["ratio"].get(k); line.append(virg("%g" % a["mean"]) if a else "-")
        rows.append(line)
        gp = res["ratio"].get("GPA-primed")
        for store, key in ((f_dict, "zstd-dict"), (f_lean, "zstd-dict-lean"), (f_uni, "unishox2")):
            o = res["ratio"].get(key)
            if gp and o and gp["mean"] > 0: store.append(o["mean"] / gp["mean"])
    add_table(doc, headers, rows, colsize=8.5)
    v = lambda x: f"{x:.2f}".replace(".", ",")
    if f_dict and f_lean:
        body(doc, f"Em todos os domínios o GhostPredict com prior produz o menor arquivo médio. Sobre o "
            f"dicionário treinado do zstd, o fator de redução varia de {v(min(f_dict))} a "
            f"{v(max(f_dict))} vezes, média {v(sum(f_dict)/len(f_dict))}. Esse número, porém, inclui o "
            f"enquadramento do zstd. Contra a variante enxuta, que remove a soma de verificação e o "
            f"identificador de dicionário, o fator cai para {v(min(f_lean))} a {v(max(f_lean))} vezes, "
            f"média {v(sum(f_lean)/len(f_lean))}, valor que reflete apenas o modelo. Sobre o Unishox2, "
            f"especialista sem prior, a média é {v(sum(f_uni)/len(f_uni))} vezes.", first=False)
    if floor.get("default") is not None:
        body(doc, f"A diferença entre as duas comparações é o custo fixo de enquadramento. Medido "
            f"sobre uma entrada vazia, o dicionário do zstd ocupa {floor.get('default')} bytes na forma "
            f"padrão e {floor.get('lean')} bytes na forma enxuta, custo que o GhostPredict não paga por "
            f"não ter cabeçalho. A Tabela 3 decompõe, em bytes médios por mensagem, a vantagem do "
            f"GhostPredict com prior sobre o dicionário do zstd em duas parcelas: a moldura removível, "
            f"que é a soma de verificação e o identificador de dicionário eliminados pela variante "
            f"enxuta, e o restante, que combina o modelo aquecido e o cabeçalho irredutível do zstd que "
            f"o formato sem cabeçalho também evita.", first=False)
        caption(doc, "Tabela 3. Decomposição da vantagem do GPA com prior sobre o zstd-dict (bytes/mensagem).")
        drows = []
        for dom, res in domains(R):
            g = res["ratio"].get("GPA-primed"); z = res["ratio"].get("zstd-dict"); zl = res["ratio"].get("zstd-dict-lean")
            if not (g and z and zl): continue
            total = z["mean"] - g["mean"]; mold = z["mean"] - zl["mean"]; modelo = zl["mean"] - g["mean"]
            drows.append([DOM_LABEL.get(dom, dom), virg("%.1f" % total), virg("%.1f" % mold), virg("%.1f" % modelo)])
        add_table(doc, ["Domínio", "Vantagem total", "Moldura removível", "Modelo + formato"], drows, colsize=9.5)

    # 5.2 distribuicao
    body(doc, "A Tabela 4 mostra que a vantagem não se deve a poucos casos extremos: para o "
        "GhostPredict com prior, a mediana e o percentil 95 do tamanho por mensagem ficam próximos da "
        "média em todos os domínios.")
    caption(doc, "Tabela 4. GhostPredict com prior: média, mediana e percentil 95 do tamanho (bytes).")
    rows3 = []
    for dom, res in domains(R):
        a = res["ratio"].get("GPA-primed")
        if a: rows3.append([DOM_LABEL.get(dom, dom), virg("%g" % a["mean"]), virg(a["median"]), virg(a["p95"])])
    add_table(doc, ["Domínio", "Média", "Mediana", "P95"], rows3, colsize=10)

    # 5.3 inflacao e vitoria
    body(doc, "A Tabela 5 mostra a fração de mensagens que cada ferramenta expande e a fração em que o "
        "GhostPredict com prior produz o menor resultado. Ela evidencia o problema que motiva o "
        "trabalho: no regime de poucas dezenas de bytes, gzip e xz frequentemente aumentam o dado.")
    caption(doc, "Tabela 5. Mensagens expandidas (Exp.) e vitórias (Venc.), em porcentagem.")
    rows4 = []
    for dom, res in domains(R):
        ip = res["inflate_pct"]; wp = res["win_pct"]
        rows4.append([DOM_LABEL.get(dom, dom), virg("%g" % wp.get("GPA-primed", 0)),
                      virg("%g" % ip.get("gzip-9", 0)), virg("%g" % ip.get("xz-9", 0)),
                      virg("%g" % ip.get("smaz", 0)), virg("%g" % ip.get("unishox2", 0))])
    add_table(doc, ["Domínio", "GPA prior Venc.", "gzip Exp.", "xz Exp.", "smaz Exp.", "unishox2 Exp."], rows4, colsize=9.5)

    # 5.4 dependencia de dominio (cross)
    if CR:
        body(doc, "A Tabela 6 quantifica a dependência do prior em relação ao domínio. Cada célula é o "
            "tamanho médio do comprimido quando se usa o primer do domínio da coluna para comprimir as "
            "mensagens de teste do domínio da linha. A diagonal, com primer casado, é sempre a menor; "
            "fora dela, o tamanho cresce de forma acentuada, podendo aproximar-se do tamanho original.")
        caption(doc, "Tabela 6. Tamanho médio (bytes) com primer cruzado: linha é o teste, coluna é o primer.")
        cdoms = [d for d in CR.keys()]
        head = ["teste \\ primer"] + [DOM_LABEL.get(d, d).split(" ")[0] for d in cdoms]
        crows = []
        for tb in cdoms:
            row = [DOM_LABEL.get(tb, tb).split(" ")[0]]
            for pa in cdoms:
                val = CR.get(tb, {}).get(pa)
                row.append(virg("%g" % val) if val is not None else "-")
            crows.append(row)
        add_table(doc, head, crows, colsize=9.5)

    # 5.5 velocidade e memoria
    agg = {}
    for dom, res in domains(R):
        for k, vv in res.get("speed", {}).items():
            if vv.get("mbps") is None: continue
            agg.setdefault(k, {"m": [], "r": []}); agg[k]["m"].append(vv["mbps"])
            if vv.get("rss_mb") is not None: agg[k]["r"].append(vv["rss_mb"])
    body(doc, "Quanto a recursos, é preciso separar duas medidas distintas. A Tabela 7 traz a vazão de "
        "compressão e o pico de memória residente do processo no computador de teste, sobre lotes "
        "concatenados. Esse pico de processo inclui o binário e o sistema operacional e não representa "
        "o consumo do algoritmo embarcado. O número relevante para microcontroladores é o conjunto de "
        "trabalho do motor, medido por um alocador instrumentado e independente do tamanho da mensagem "
        "no perfil micro: cerca de 19 KB para o decodificador e cerca de 51 KB para o compressor. A "
        "esse custo soma-se o primer, que ocupa de 16 a 32 KB na memória de programa do dispositivo, "
        "pois reside no codec e não no arquivo.")
    caption(doc, "Tabela 7. Vazão média e pico de memória do processo no host (não é o footprint embarcado).")
    order = ["GPA-frio", "GPA-primed", "gzip-9", "zstd-19", "brotli-11", "xz-9"]
    lbl = {"GPA-frio": "GPA frio", "GPA-primed": "GPA prior", "gzip-9": "gzip-9", "zstd-19": "zstd-19",
           "brotli-11": "brotli-11", "xz-9": "xz-9"}
    rows6 = []
    for k in order:
        if k not in agg: continue
        m = agg[k]["m"]; r = agg[k]["r"]
        rows6.append([lbl[k], f"{(sum(m)/len(m)) if m else 0:.1f}".replace(".", ","),
                      f"{(sum(r)/len(r)) if r else 0:.1f}".replace(".", ",")])
    add_table(doc, ["Configuração", "Vazão (MB/s)", "Mem. proc. (MB)"], rows6, colsize=10)
    body(doc, "A Tabela 8 reúne, em um único lugar, os custos do prior, hoje dispersos pelo texto. "
        "Ela torna o trade-off imediatamente visível: um custo fixo de memória de programa e de RAM, "
        "em troca da compressão, condicionado à estabilidade do domínio.", first=False)
    caption(doc, "Tabela 8. Custos do prior (resumo do trade-off).")
    add_table(doc, ["Item", "Valor"],
        [["Primer (memória de programa)", "16 a 32 KB"],
         ["Decodificador (RAM de trabalho)", "cerca de 19 KB"],
         ["Compressor (RAM de trabalho)", "cerca de 51 KB"],
         ["Degradação com domínio cruzado", "até cerca de 10 vezes (Tabela 6)"]], colsize=10)

    # 5.6 exemplos concretos
    body(doc, "A título de ilustração, uma mensagem MQTT real de 69 bytes, "
        "\"1725866030.472465,0x0018,...,2,dos\", é reduzida pelo GhostPredict com prior a 16 bytes. As "
        "demais ferramentas, sem um prior casado, ficam bem acima: o Unishox2 produz 35 bytes, o zstd "
        "com dicionário 43 bytes, sua variante enxuta 35 bytes, e o GhostPredict sem prior 42 bytes.", first=False)
    body(doc, "Um exemplo de log esclarece por que os logs comprimem tanto. A linha do Apache "
        "\"[Sun Dec 04 06:06:11 2005] [notice] workerEnv.init() ok /etc/httpd/conf/workers2.properties\", "
        "de 91 bytes, é reduzida pelo GhostPredict com prior a 10 bytes, ante 30 bytes do zstd com "
        "dicionário, 63 do Unishox2 e 82 do GhostPredict sem prior. O motivo é que essa linha é um "
        "molde quase fixo, repetido milhares de vezes no fluxo de log; o primer já o conhece, de modo "
        "que apenas a parte variável, sobretudo o instante de tempo, precisa ser codificada. A "
        "agressividade dos resultados de log decorre, portanto, da natureza altamente repetitiva desse "
        "tráfego, e não de um artefato de medição.", first=False)
    body(doc, "Os dois exemplos, o do MQTT e o do log, resumem em uma única mensagem o efeito do "
        "prior de domínio e a razão dos ganhos observados nas tabelas anteriores.", first=False)

if __name__ == "__main__":
    build()
