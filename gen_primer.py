#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador do primer.bin do GhostPredict.

O primer e um corpus bruto de mensagens representativas do dominio. Ele NAO tem
formato especial: e apenas a concatenacao de amostras, uma por linha. O motor o
embute em tempo de compilacao via include_bytes!("primer.bin") e o usa para
(a) aquecer o modelo PPM e (b) servir de dicionario LZ. So os ultimos CAP bytes
entram na janela do LZ (CAP = 32768 por padrao, igual a janela de fluxo);
o PPM, porem, e aquecido pelo corpus inteiro.

Tres modos:
  --from-dataset ARQ : constroi um primer de DOMINIO a partir de um arquivo com
                       um registro por linha. Embaralha com semente fixa, separa
                       as primeiras N_TEST linhas como TESTE (held-out, NUNCA
                       entram no primer) e usa as seguintes como treino. E o
                       procedimento usado na validacao experimental.
  --synthetic        : gera um primer GENERICO de texto curto estruturado
                       (palavras, chave=valor, URLs, e-mails, JSON), de forma
                       deterministica. Reproduz o estilo do primer generico.
  --from-files A B .. : concatena varios arquivos de amostras.

Exemplos:
  python gen_primer.py --from-dataset datasets/.../loop_1.csv --skip-header
  python gen_primer.py --synthetic --cap 16384
  python gen_primer.py --from-files urls.txt jsons.txt --out primer.bin
"""
import argparse, os, random, sys

DEFAULT_CAP = 32768   # casa com LZ_WINDOW (32 KB): so os ultimos CAP bytes viram dicionario
N_TEST = 200          # held-out reservado como teste (mesmo valor do harness)

def cap_tail(corpus: bytes, cap: int) -> bytes:
    # Mantem os ULTIMOS cap bytes: sao os que a janela LZ enxerga como dicionario.
    return corpus[-cap:] if cap and len(corpus) > cap else corpus

def from_dataset(path, seed, skip_header, cap, heldout):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = [ln.rstrip("\n").rstrip("\r") for ln in f]
    if skip_header and lines:
        lines = lines[1:]
    lines = [x for x in lines if x.strip()]
    random.Random(seed).shuffle(lines)
    # As primeiras N_TEST sao TESTE (held-out): nunca entram no primer.
    train = lines[N_TEST:N_TEST + heldout] if heldout else lines[N_TEST:]
    corpus = ("\n".join(train) + "\n").encode("utf-8", "replace")
    return cap_tail(corpus, cap), len(train)

def from_files(paths, cap):
    buf = bytearray()
    for p in paths:
        with open(p, "rb") as f:
            buf += f.read()
            if buf[-1:] != b"\n":
                buf += b"\n"
    return cap_tail(bytes(buf), cap), len(paths)

def synthetic(seed, cap):
    rnd = random.Random(seed)
    words = ("time year people way day man thing woman life child world school "
             "state family student group country problem hand part place case week "
             "company system program question work government number night point home "
             "water room mother area money story fact month lot right study book eye job "
             "word business issue side kind head house service friend father power hour "
             "game line end member law car city community name president team minute idea "
             "body information back parent face others level office door health person art "
             "war history party result change morning reason research girl guy moment air "
             "teacher force education").split()
    domains = ["example.com", "data.cloud", "sensor.io", "api.service.net", "mail.org"]
    keys = ["count", "active", "value", "status", "code", "id", "temp", "hum",
            "email", "title", "name", "date", "level", "type", "size", "flag"]
    out = []
    def w(n): return " ".join(rnd.choice(words) for _ in range(n))
    while sum(len(x) + 1 for x in out) < (cap * 4):  # gera com folga; corte final pega o fim
        r = rnd.random()
        if r < 0.30:
            out.append(w(rnd.randint(3, 9)))
        elif r < 0.50:
            out.append(";".join(f"{rnd.choice(keys)}={rnd.randint(0, 999)}" for _ in range(rnd.randint(2, 4))))
        elif r < 0.65:
            out.append(f"https://www.{rnd.choice(domains)}/account/v{rnd.randint(1,3)}/{rnd.randint(1000,99999)}")
        elif r < 0.78:
            out.append(f"{rnd.choice(words)}.{rnd.choice(words)}{rnd.randint(1,99)}@{rnd.choice(domains)}")
        else:
            fields = ", ".join(f'"{rnd.choice(keys)}":{rnd.randint(0,999)}.{rnd.randint(10,99)}'
                               for _ in range(rnd.randint(2, 4)))
            out.append("{" + fields + "}")
    corpus = ("\n".join(out) + "\n").encode("utf-8", "replace")
    return cap_tail(corpus, cap), len(out)

def main():
    ap = argparse.ArgumentParser(description="Gera o primer.bin do GhostPredict.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from-dataset", metavar="ARQ", help="arquivo com um registro por linha")
    g.add_argument("--synthetic", action="store_true", help="corpus generico deterministico")
    g.add_argument("--from-files", nargs="+", metavar="ARQ", help="concatena varios arquivos")
    ap.add_argument("--out", default="primer.bin")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP, help="bytes finais mantidos (0 = sem corte)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--skip-header", action="store_true", help="ignora a 1a linha (cabecalho CSV)")
    ap.add_argument("--heldout", type=int, default=5000, help="linhas de treino apos as N_TEST de teste")
    args = ap.parse_args()

    if args.from_dataset:
        primer, n = from_dataset(args.from_dataset, args.seed, args.skip_header, args.cap, args.heldout)
        origem = f"dataset {os.path.basename(args.from_dataset)} ({n} linhas de treino, held-out apos as {N_TEST} de teste)"
    elif args.from_files:
        primer, n = from_files(args.from_files, args.cap)
        origem = f"{n} arquivo(s)"
    else:
        primer, n = synthetic(args.seed, args.cap)
        origem = f"sintetico ({n} linhas geradas, semente {args.seed})"

    with open(args.out, "wb") as f:
        f.write(primer)
    print(f"primer escrito: {args.out}  ({len(primer)} bytes)  origem: {origem}")
    print("Recompile o motor para embutir o novo primer:")
    print("  rustc +stable-x86_64-pc-windows-gnu -C opt-level=3 main.rs -o main.exe")

if __name__ == "__main__":
    main()
