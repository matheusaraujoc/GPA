#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera os vetores de teste do firmware de benchmark do ESP32.

Produz `embedded/main/gpa_test_vectors.h` contendo:
  - o primer de dominio (usado no modo primed);
  - N mensagens held-out, cada uma com o original, o .gpa frio e o .gpa primed.

O protocolo espelha o do benchmark.py: as mensagens sao embaralhadas com semente
fixa e divididas em treino (constroi o primer) e teste (held-out, vai para o
firmware). Assim os numeros medidos na placa sao comparaveis aos do artigo.

Uso:
    # corpus IoT sintetico determinstico (nao exige a pasta datasets/)
    python embedded/tools/gen_vectors.py

    # dados reais: um registro por linha (recomendado para o artigo)
    python embedded/tools/gen_vectors.py --from-file datasets/mqtt/loop_1.csv --skip-header

Depois: idf.py build flash monitor
"""
import argparse
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAIN_EXE = os.path.join(ROOT, "main.exe")
OUT_H = os.path.join(ROOT, "embedded", "main", "gpa_test_vectors.h")

PRIMER_CAP = 16384   # cabe folgado na flash; a janela LZ aproveita os ultimos 32 KB
N_TEST = 12          # mensagens held-out embutidas no firmware
SEED = 42


def synth_corpus(n=4000, seed=SEED):
    """Corpus IoT determinstico: telemetria MQTT, sensores, GPS e log.

    Serve quando a pasta datasets/ nao esta disponivel. Tem a estrutura repetitiva
    tipica de telemetria (mesmos campos, valores variando), que e o regime alvo.
    """
    rnd = random.Random(seed)
    devs = ["A01", "A02", "B07", "B12", "C03", "C09", "D11", "D42"]
    stats = ["OK", "WARN", "OK", "OK", "IDLE"]
    out = []
    for i in range(n):
        kind = i % 4
        ts = 1725866030 + i * 7
        if kind == 0:
            out.append('{"dev":"%s","ts":%d,"temp":%.1f,"hum":%d,"st":"%s"}' % (
                rnd.choice(devs), ts, rnd.uniform(18.0, 34.0), rnd.randint(30, 95),
                rnd.choice(stats)))
        elif kind == 1:
            out.append("%d,%d,%.4f,%.4f,%.2f,%d" % (
                ts, rnd.randint(1, 54), rnd.uniform(18.0, 30.0),
                rnd.uniform(20.0, 45.0), rnd.uniform(2.6, 3.1), rnd.randint(0, 4)))
        elif kind == 2:
            out.append('{"lat":%.6f,"lon":%.6f,"spd":%.1f,"alt":%d,"ts":%d}' % (
                rnd.uniform(-3.2, -2.6), rnd.uniform(-42.0, -41.2),
                rnd.uniform(0.0, 92.0), rnd.randint(2, 180), ts))
        else:
            out.append("[%s] 2026-05-%02dT%02d:%02d sensor=%d value=%d status=%s" % (
                rnd.choice(["INFO", "WARN", "INFO"]), rnd.randint(1, 28),
                rnd.randint(0, 23), rnd.randint(0, 59), rnd.randint(1, 54),
                rnd.randint(0, 9999), rnd.choice(stats)))
    return out


def load_lines(path, skip_header):
    with open(path, "rb") as f:
        raw = f.read()
    lines = [l.strip() for l in raw.replace(b"\r\n", b"\n").split(b"\n")]
    lines = [l for l in lines if l]
    if skip_header and lines:
        lines = lines[1:]
    return [l.decode("utf-8", "replace") for l in lines]


def run_engine(args):
    r = subprocess.run([MAIN_EXE] + args, capture_output=True)
    if r.returncode != 0:
        sys.exit("erro no motor: %s\n%s" % (" ".join(args), r.stderr.decode("utf-8", "replace")))


def compress(msg_bytes, primer_path=None):
    """Comprime um payload com o motor Rust. Sem primer usa 'c'; com primer usa 'cpf'."""
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in.bin")
        dst = os.path.join(td, "out.gpa")
        with open(src, "wb") as f:
            f.write(msg_bytes)
        if primer_path:
            run_engine(["cpf", src, dst, primer_path])
        else:
            run_engine(["c", src, dst])
        with open(dst, "rb") as f:
            return f.read()


def c_array(name, data, per_line=16):
    lines = ["static const unsigned char %s[%d] = {" % (name, len(data))]
    for i in range(0, len(data), per_line):
        chunk = data[i:i + per_line]
        lines.append("    " + "".join("0x%02x," % b for b in chunk))
    lines.append("};")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-file", help="arquivo com um registro por linha (dados reais)")
    ap.add_argument("--skip-header", action="store_true", help="ignora a primeira linha (CSV)")
    ap.add_argument("--n-test", type=int, default=N_TEST, help="mensagens held-out no firmware")
    ap.add_argument("--primer-cap", type=int, default=PRIMER_CAP, help="tamanho maximo do primer")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()

    if not os.path.exists(MAIN_EXE):
        sys.exit("main.exe nao encontrado. Compile antes:\n"
                 "  rustc +stable-x86_64-pc-windows-gnu -C opt-level=3 main.rs -o main.exe")

    if a.from_file:
        records = load_lines(a.from_file, a.skip_header)
        origem = os.path.basename(a.from_file)
        if len(records) < a.n_test * 4:
            sys.exit("poucas linhas em %s (%d)" % (a.from_file, len(records)))
    else:
        records = synth_corpus(seed=a.seed)
        origem = "corpus IoT sintetico determinstico (--from-file para dados reais)"

    rnd = random.Random(a.seed)
    rnd.shuffle(records)

    # held-out: as primeiras n_test viram teste; o restante constroi o primer.
    test_msgs = records[:a.n_test]
    train = records[a.n_test:]

    # primer = ultimos PRIMER_CAP bytes do corpus de treino (mesma regra do gen_primer.py)
    primer_blob = ("\n".join(train) + "\n").encode("utf-8")[-a.primer_cap:]
    primer_path = os.path.join(ROOT, "embedded", "main", "gpa_primer_test.bin")
    with open(primer_path, "wb") as f:
        f.write(primer_blob)

    print("origem........: %s" % origem)
    print("registros.....: %d (treino %d / teste %d)" % (len(records), len(train), len(test_msgs)))
    print("primer........: %d B" % len(primer_blob))
    print()

    entries = []
    tot_o = tot_c = tot_p = 0
    for i, m in enumerate(test_msgs):
        raw = m.encode("utf-8")
        cold = compress(raw)
        primed = compress(raw, primer_path)
        entries.append((i, raw, cold, primed))
        tot_o += len(raw); tot_c += len(cold); tot_p += len(primed)
        print("  msg %2d: orig %3d B  frio %3d B  primed %3d B" % (i, len(raw), len(cold), len(primed)))

    print()
    print("media...: orig %.1f B  frio %.1f B  primed %.1f B"
          % (tot_o / len(entries), tot_c / len(entries), tot_p / len(entries)))
    print("fator primed sobre o original: %.2fx" % (tot_o / tot_p))

    # ---- emite o header ----
    parts = []
    parts.append("/* gpa_test_vectors.h - GERADO POR embedded/tools/gen_vectors.py. NAO EDITE.\n"
                 " *\n"
                 " * Origem: %s\n"
                 " * Protocolo: held-out com semente %d; o primer vem do corpus de treino,\n"
                 " * disjunto das mensagens de teste, como em benchmark.py.\n"
                 " *\n"
                 " * Medias: original %.1f B, frio %.1f B, primed %.1f B.\n"
                 " */\n"
                 "#ifndef GPA_TEST_VECTORS_H\n"
                 "#define GPA_TEST_VECTORS_H\n"
                 % (origem, a.seed, tot_o / len(entries), tot_c / len(entries), tot_p / len(entries)))
    parts.append("#define GPA_N_VECTORS %d\n" % len(entries))
    parts.append("#define GPA_PRIMER_LEN %d\n" % len(primer_blob))
    parts.append("/* O primer so e compilado no modo primed: sao %d B de flash. */\n"
                 "#ifdef GPA_ENABLE_PRIMED\n%s\n#endif\n"
                 % (len(primer_blob), c_array("GPA_PRIMER", primer_blob)))

    for i, raw, cold, primed in entries:
        parts.append(c_array("V%d_ORIG" % i, raw))
        parts.append(c_array("V%d_COLD" % i, cold))
        parts.append("#ifdef GPA_ENABLE_PRIMED\n%s\n#endif" % c_array("V%d_PRIMED" % i, primed))

    parts.append("typedef struct {\n"
                 "    const unsigned char *orig;  unsigned orig_len;\n"
                 "    const unsigned char *cold;  unsigned cold_len;\n"
                 "#ifdef GPA_ENABLE_PRIMED\n"
                 "    const unsigned char *primed; unsigned primed_len;\n"
                 "#endif\n"
                 "} gpa_vector_t;\n")

    rows = []
    for i, raw, cold, primed in entries:
        if True:
            rows.append("    { V%d_ORIG, %d, V%d_COLD, %d,\n"
                        "#ifdef GPA_ENABLE_PRIMED\n"
                        "      V%d_PRIMED, %d,\n"
                        "#endif\n"
                        "    }," % (i, len(raw), i, len(cold), i, len(primed)))
    parts.append("static const gpa_vector_t GPA_VECTORS[GPA_N_VECTORS] = {\n%s\n};\n" % "\n".join(rows))
    parts.append("#endif /* GPA_TEST_VECTORS_H */\n")

    with open(OUT_H, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print("\nheader gerado: %s" % OUT_H)
    print("primer de teste: %s" % primer_path)


if __name__ == "__main__":
    main()
