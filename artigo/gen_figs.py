#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera as sete figuras do artigo, em artigo/figs/ e em artigo/latex/figs/.

As figuras 4, 5 e 6 sao derivadas de resultados_reais.json e cross_domain.json,
produzidos por benchmark.py. A figura 7 usa as medicoes de
embedded/resultado_esp32.txt. As figuras 1 a 3 sao diagramas do algoritmo.

Requer matplotlib. Usar o Python 3.11 do usuario, nao o python do ESP-IDF:
    python artigo/gen_figs.py
"""
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON = os.path.join(ROOT, "resultados_reais.json")
CROSSJSON = os.path.join(ROOT, "cross_domain.json")
DESTINOS = [os.path.join(ROOT, "artigo", "figs"),
            os.path.join(ROOT, "artigo", "latex", "figs")]

DOM_LABEL = {
    "MQTT": "MQTT (IoT)", "AIS": "AIS (navios)", "IntelLab": "Sensores (Intel Lab)",
    "Household": "Medidor (energia)", "Geolife": "GPS (GeoLife)",
    "Log-Apache": "Log Apache", "Log-Linux": "Log Linux", "Log-OpenSSH": "Log OpenSSH",
    "Log-HDFS": "Log HDFS", "SMS": "SMS", "Tweets": "Tweets",
}

# Paleta Okabe-Ito (publicada, segura para daltonismo). Reforcada por rotulos
# diretos e legendas, para que a identidade nunca dependa apenas da cor.
C_ORIG = "#999999"
C_GPA = "#0072B2"
C_ZSTD = "#E69F00"
C_UNI = "#009E73"
INK = "#222222"

# Medicoes do ESP32 (embedded/resultado_esp32.txt e idf.py size-components)
LAT_FRIO, LAT_PRIOR = 698.0, 47665.0
RAM_FRIO_BSS, RAM_PRIOR_BSS = 19.692, 68.852
RAM_PRIOR_HEAP = 196.844

# Parametros do enlace LoRaWAN (ver Secao 7 do artigo)
LORAWAN_MAC_OVERHEAD = 13
I_TX_A, V_SUP = 0.028, 3.3
P_TX_W = I_TX_A * V_SUP


def domains(R):
    return [(k, v) for k, v in R.items() if not k.startswith("_")]


def load(path):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def salvar(fig, nome):
    for d in DESTINOS:
        os.makedirs(d, exist_ok=True)
        fig.savefig(os.path.join(d, nome), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("  " + nome)


# --------------------------------------------------------------------------
# Auxiliares de desenho
# --------------------------------------------------------------------------
def _style_axes(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#BBBBBB")
    ax.tick_params(colors=INK, labelsize=9)


def _box(ax, x, y, w, h, text, fc="#EDF2F9", ec="#44506B", fs=8.5, lw=1.1,
         ls="-", weight="normal"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012",
                                fc=fc, ec=ec, lw=lw, linestyle=ls, mutation_scale=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            color=INK, weight=weight, linespacing=1.35)


def _arrow(ax, x1, y1, x2, y2, ls="-", color="#44506B"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=11, lw=1.2, color=color, linestyle=ls))


# --------------------------------------------------------------------------
# Figura 1: pipeline
# --------------------------------------------------------------------------
def fig_pipeline():
    fig, ax = plt.subplots(figsize=(9.2, 3.4), dpi=200)
    ax.set_xlim(0, 100); ax.set_ylim(0, 40); ax.axis("off")
    _box(ax, 1, 24, 11, 10, "Entrada\n(bytes)")
    _box(ax, 16, 22, 15, 14, "LZ77\njanela 4/32 KB\nlazy matching\noffset history")
    _box(ax, 35, 24, 15, 10, "Fluxo de tokens\nnibbles, MATCH\n(dist, len), EOF")
    _box(ax, 54, 30.5, 17, 8.0, "PPM ordem 2\nsobre nibbles", fc="#E7F2EC")
    _box(ax, 54, 20.5, 17, 8.0, "Modelo de\ndistância", fc="#E7F2EC")
    _box(ax, 54, 10.5, 17, 8.0, "Modelo de\ncomprimento", fc="#E7F2EC")
    _box(ax, 75, 22, 13, 14, "Codificador\naritmético\ninteiro\n32 bits", fc="#FBF1DC")
    _box(ax, 91.5, 24, 8, 10, "Arquivo\n.gpa", fc="#F2F2F2")
    _box(ax, 16, 3, 15, 8, "Primer de domínio\n(opcional, no codec)", fc="#FFFFFF", ls="--")
    _box(ax, 75, 3, 13, 8, "Flag enviesada 1/64\ne modo stored", fc="#FFFFFF", ls="--")
    _arrow(ax, 12, 29, 16, 29)
    _arrow(ax, 31, 29, 35, 29)
    _arrow(ax, 50, 29, 54, 33.5)
    _arrow(ax, 50, 29, 54, 24.5)
    _arrow(ax, 50, 27, 54, 15.0)
    _arrow(ax, 71, 34.5, 75, 31)
    _arrow(ax, 71, 24.5, 75, 27)
    _arrow(ax, 71, 14.5, 75, 24)
    _arrow(ax, 88, 29, 91.5, 29)
    _arrow(ax, 23.5, 11, 23.5, 22, ls="--")
    _arrow(ax, 31, 7, 62, 10.5, ls="--")
    _arrow(ax, 81.5, 11, 81.5, 22, ls="--")
    salvar(fig, "fig1_pipeline.png")


# --------------------------------------------------------------------------
# Figura 2: sequencia do modo com prior
# --------------------------------------------------------------------------
def fig_sequencia():
    fig, ax = plt.subplots(figsize=(8.6, 4.6), dpi=200)
    ax.set_xlim(0, 100); ax.set_ylim(0, 62); ax.axis("off")
    _box(ax, 8, 55, 30, 6, "Dispositivo (codificador)", fc="#EDF2F9", weight="bold", fs=9)
    _box(ax, 62, 55, 30, 6, "Gateway / nuvem (decodificador)", fc="#EDF2F9", weight="bold", fs=9)
    ax.plot([23, 23], [8, 55], ls="--", lw=1.0, color="#888888")
    ax.plot([77, 77], [8, 55], ls="--", lw=1.0, color="#888888")

    def step(x, y, text, w=26):
        _box(ax, x - w / 2, y - 2.6, w, 5.2, text, fc="#FFFFFF", fs=8)

    step(23, 49, "1. prime_model(PRIMER):\naquece PPM, dist, len")
    step(77, 49, "1. prime_model(PRIMER):\nestado idêntico")
    step(23, 40, "2. LZ77 sobre PRIMER ++ msg\n(matches podem citar o primer)")
    step(23, 31, "3. codifica tokens da mensagem\n(aritmético, modelos aquecidos)")
    _arrow(ax, 23, 25, 77, 25)
    ax.text(50, 26.5, "4. transmite o .gpa (somente a mensagem)", ha="center",
            fontsize=8.5, color=INK)
    step(77, 19, "5. decodifica com modelos aquecidos;\nmatches copiam do primer")
    step(77, 11.5, "6. descarta o prefixo do primer\ne entrega a mensagem")
    ax.text(50, 3.5, "O primer reside no firmware dos dois lados e nunca é transmitido.",
            ha="center", fontsize=8.5, style="italic", color="#555555")
    salvar(fig, "fig2_sequencia.png")


# --------------------------------------------------------------------------
# Figura 3: diagrama de classes
# --------------------------------------------------------------------------
def fig_uml():
    fig, ax = plt.subplots(figsize=(9.6, 6.4), dpi=200)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")

    def klass(x, y, w, name, attrs, meths, fs=7.0):
        lh, h_name = 3.4, 5.5
        h_attr = lh * max(len(attrs), 1) + 2
        h_meth = lh * max(len(meths), 1) + 2
        h = h_name + h_attr + h_meth
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="square,pad=0",
                                    fc="#FCFCFC", ec="#44506B", lw=1.1))
        ax.plot([x, x + w], [y + h - h_name] * 2, color="#44506B", lw=0.8)
        ax.plot([x, x + w], [y + h_meth] * 2, color="#44506B", lw=0.8)
        ax.text(x + w / 2, y + h - h_name / 2, name, ha="center", va="center",
                fontsize=fs + 1.2, weight="bold", color=INK)
        for i, a in enumerate(attrs):
            ax.text(x + 1.2, y + h - h_name - 2 - i * lh, a, ha="left", va="top",
                    fontsize=fs, family="monospace", color=INK)
        for i, m in enumerate(meths):
            ax.text(x + 1.2, y + h_meth - 1 - i * lh, m, ha="left", va="top",
                    fontsize=fs, family="monospace", color=INK)

    klass(2, 22, 34, "GhostPredictEngine",
          ["graph[256][18]: u16", "graph_cum, graph_totals", "o0_counts[18], o0_cum",
           "current_node: 0..255", "dist_code_counts[16]", "last_offsets[3] (MTF)",
           "len_code_counts[8]", "last_length"],
          ["compress_stream(raw)", "decompress_stream(gpa)", "compress_primed(raw, primer)",
           "decompress_primed(gpa, primer)", "encode_token(tok)", "learn_token(tok)",
           "decode_symbol()", "decode_match()"])
    klass(44, 66, 26, "LZ77",
          ["head: Vec<i32>", "prev: Vec<i32>", "window, hash_size"],
          ["find_match(i)", "insert_hash(p)", "parse_streaming(raw)", "parse_with_dict(comb)"])
    klass(76, 70, 22, "«enum» Token",
          ["Nibble(u8)", "Match(dist,len)", "EOF"], ["  "])
    klass(44, 36, 26, "ArithmeticCoder",
          ["low, high: u32", "pending_bits"],
          ["encode(lo, hi, tot)", "encode_bit(b)", "finish()"])
    klass(44, 8, 26, "ArithmeticDecoder",
          ["low, high, value: u32"],
          ["get_target(tot)", "decode(lo, hi, tot)", "decode_bit()"])
    klass(76, 38, 22, "BitWriter",
          ["bytes: Vec<u8>", "bit_accum, bit_count"], ["write_bit(b)", "flush()"])
    klass(76, 12, 22, "BitReader", ["bytes: Vec<u8>", "bit_idx"], ["read_bit()"])

    _arrow(ax, 36, 74, 44, 76); ax.text(39.5, 77.5, "usa", fontsize=7, color="#44506B")
    _arrow(ax, 70, 78, 76, 78); ax.text(71.5, 79.5, "emite", fontsize=7, color="#44506B")
    _arrow(ax, 36, 48, 44, 46); ax.text(38.5, 48.5, "usa", fontsize=7, color="#44506B")
    _arrow(ax, 36, 30, 44, 18); ax.text(38.5, 25, "usa", fontsize=7, color="#44506B")
    _arrow(ax, 70, 45, 76, 45); ax.text(70.8, 46.5, "escreve", fontsize=7, color="#44506B")
    _arrow(ax, 70, 16, 76, 17); ax.text(71.5, 18.5, "lê", fontsize=7, color="#44506B")
    salvar(fig, "fig3_uml.png")


# --------------------------------------------------------------------------
# Figura 4: tamanho medio por dominio
# --------------------------------------------------------------------------
def fig_resultados(R):
    doms = [d for d, _ in domains(R)]
    labels = [DOM_LABEL.get(d, d) for d in doms]
    orig = [R[d]["orig_mean"] for d in doms]
    gpa = [R[d]["ratio"]["GPA-primed"]["mean"] for d in doms]
    lean = [R[d]["ratio"]["zstd-dict-lean"]["mean"] for d in doms]
    uni = [R[d]["ratio"]["unishox2"]["mean"] for d in doms]
    y = list(range(len(doms)))[::-1]
    hb = 0.19
    fig, ax = plt.subplots(figsize=(8.8, 6.2), dpi=200)
    ax.barh([i + 1.5 * hb for i in y], orig, hb, color=C_ORIG, label="Original")
    ax.barh([i + 0.5 * hb for i in y], uni, hb, color=C_UNI, label="Unishox2")
    ax.barh([i - 0.5 * hb for i in y], lean, hb, color=C_ZSTD, label="zstd dicionário enxuto")
    ax.barh([i - 1.5 * hb for i in y], gpa, hb, color=C_GPA, label="GhostPredict com prior")
    for i, v in zip(y, gpa):
        ax.text(v + 2, i - 1.5 * hb, ("%.0f" % v), va="center", fontsize=7.5, color=C_GPA)
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("tamanho médio por mensagem (bytes); menor é melhor", fontsize=9)
    ax.legend(loc="lower right", fontsize=8.5, frameon=False)
    ax.grid(axis="x", color="#DDDDDD", lw=0.6); ax.set_axisbelow(True)
    _style_axes(ax)
    salvar(fig, "fig4_resultados.png")


# --------------------------------------------------------------------------
# Figura 5: mapa de calor do experimento cruzado
# --------------------------------------------------------------------------
def fig_cross(CR):
    doms = list(CR.keys())
    short = {d: DOM_LABEL.get(d, d).split(" ")[0] for d in doms}
    mat = [[CR[t].get(p) for p in doms] for t in doms]
    fig, ax = plt.subplots(figsize=(6.4, 4.9), dpi=200)
    vmax = max(max(r) for r in mat)
    im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=vmax)
    ax.set_xticks(range(len(doms))); ax.set_xticklabels([short[d] for d in doms], fontsize=9)
    ax.set_yticks(range(len(doms))); ax.set_yticklabels([short[d] for d in doms], fontsize=9)
    ax.set_xlabel("primer usado", fontsize=9); ax.set_ylabel("domínio de teste", fontsize=9)
    for i, t in enumerate(doms):
        for j, p in enumerate(doms):
            v = mat[i][j]
            ax.text(j, i, ("%.0f" % v), ha="center", va="center", fontsize=8.5,
                    color=("white" if v > 0.6 * vmax else INK),
                    weight=("bold" if i == j else "normal"))
    cb = fig.colorbar(im, ax=ax, shrink=0.85)
    cb.set_label("bytes por mensagem", fontsize=8.5)
    cb.ax.tick_params(labelsize=8)
    ax.tick_params(length=0)
    salvar(fig, "fig5_cross.png")


# --------------------------------------------------------------------------
# Figura 6: tempo de antena LoRaWAN
# --------------------------------------------------------------------------
def toa_ms(pl_bytes, sf, bw=125000, cr=1, crc=1, ih=0, npre=8):
    """Tempo de antena LoRa em ms, pela formulacao do datasheet SX1276."""
    tsym = (2 ** sf) / bw * 1000.0
    de = 1 if sf >= 11 else 0
    num = 8 * pl_bytes - 4 * sf + 28 + 16 * crc - 20 * ih
    npay = 8 + max(math.ceil(num / (4 * (sf - 2 * de))) * (cr + 4), 0)
    return (npre + 4.25) * tsym + npay * tsym


def fig_airtime(R):
    doms = [d for d, _ in domains(R)]
    labels = [DOM_LABEL.get(d, d) for d in doms]
    t_o, t_c = [], []
    for d in doms:
        po = int(math.ceil(R[d]["orig_mean"])) + LORAWAN_MAC_OVERHEAD
        pc = int(math.ceil(R[d]["ratio"]["GPA-primed"]["mean"])) + LORAWAN_MAC_OVERHEAD
        t_o.append(toa_ms(po, 12) / 1000.0)
        t_c.append(toa_ms(pc, 12) / 1000.0)
    y = list(range(len(doms)))[::-1]
    hb = 0.34
    fig, ax = plt.subplots(figsize=(8.8, 5.6), dpi=200)
    ax.barh([i + hb / 2 for i in y], t_o, hb, color=C_ORIG, label="payload original")
    ax.barh([i - hb / 2 for i in y], t_c, hb, color=C_GPA, label="GhostPredict com prior")
    for i, b in zip(y, t_c):
        ax.text(b + 0.06, i - hb / 2, ("%.1f s" % b).replace(".", ","),
                va="center", fontsize=7.5, color=C_GPA)
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("tempo de antena por mensagem em SF12/125 kHz (s); menor é melhor",
                  fontsize=9)
    ax.legend(loc="lower right", fontsize=8.5, frameon=False)
    ax.grid(axis="x", color="#DDDDDD", lw=0.6); ax.set_axisbelow(True)
    _style_axes(ax)
    salvar(fig, "fig6_airtime.png")


# --------------------------------------------------------------------------
# Figura 7: medicoes no ESP32
# --------------------------------------------------------------------------
def fig_esp32():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.0, 4.2), dpi=200)
    x = [0, 1]

    ax1.bar(x, [LAT_FRIO, LAT_PRIOR], 0.5, color=[C_GPA, C_ZSTD])
    ax1.set_yscale("log")
    ax1.set_xticks(x); ax1.set_xticklabels(["sem prior", "com prior"], fontsize=10)
    ax1.set_ylabel("latência por mensagem (µs, escala log)", fontsize=9.5)
    ax1.set_title("Latência de decodificação no ESP32", fontsize=10.5, color=INK)
    for xi, v in zip(x, [LAT_FRIO, LAT_PRIOR]):
        rot = ("%.0f µs" % v) if v < 1000 else (("%.1f ms" % (v / 1000.0)).replace(".", ","))
        ax1.text(xi, v * 1.18, rot, ha="center", fontsize=9.5, color=INK)
    ax1.set_ylim(top=LAT_PRIOR * 4)
    ax1.annotate("68 vezes mais lento;\ncerca de 47 ms são\nreaquecimento do modelo",
                 xy=(1, LAT_PRIOR), xytext=(0.30, LAT_PRIOR * 1.7), fontsize=8.5,
                 color=INK, arrowprops=dict(arrowstyle="->", color="#888888", lw=1.0))
    _style_axes(ax1)
    ax1.grid(axis="y", color="#E4E4E4", lw=0.7); ax1.set_axisbelow(True)

    ax2.bar(x, [RAM_FRIO_BSS, RAM_PRIOR_BSS], 0.5, color=[C_GPA, C_ZSTD],
            label="RAM estática (.bss)")
    ax2.bar([1], [RAM_PRIOR_HEAP], 0.5, bottom=[RAM_PRIOR_BSS], color=C_ZSTD,
            alpha=0.45, label="RAM dinâmica (heap)")
    ax2.set_xticks(x); ax2.set_xticklabels(["sem prior", "com prior"], fontsize=10)
    ax2.set_ylabel("memória de trabalho (KB)", fontsize=9.5)
    ax2.set_title("Memória do decodificador no ESP32", fontsize=10.5, color=INK)
    ax2.text(0, RAM_FRIO_BSS + 8, "19,7 KB\nsem alocação", ha="center", fontsize=9.5, color=INK)
    ax2.text(1, RAM_PRIOR_BSS + RAM_PRIOR_HEAP + 8, "265,7 KB", ha="center",
             fontsize=9.5, color=INK)
    ax2.axhline(176, color="#888888", ls=":", lw=1.3)
    ax2.text(-0.42, 183, "limite de dados estáticos do ESP32 (cerca de 176 KB)",
             fontsize=8, color="#777777")
    ax2.set_ylim(top=310)
    ax2.legend(fontsize=8.5, frameon=False, loc="upper left")
    _style_axes(ax2)
    ax2.grid(axis="y", color="#E4E4E4", lw=0.7); ax2.set_axisbelow(True)

    fig.tight_layout()
    salvar(fig, "fig7_esp32.png")


def main():
    print("gerando figuras do artigo:")
    fig_pipeline()
    fig_sequencia()
    fig_uml()
    R, CR = load(JSON), load(CROSSJSON)
    if R and domains(R):
        fig_resultados(R)
        fig_airtime(R)
    else:
        print("  (figuras 4 e 6 puladas: resultados_reais.json ausente)")
    if CR:
        fig_cross(CR)
    else:
        print("  (figura 5 pulada: cross_domain.json ausente)")
    fig_esp32()
    print("destinos: " + ", ".join(os.path.relpath(d, ROOT) for d in DESTINOS))


if __name__ == "__main__":
    main()
