#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark.py - Validacao reproduzivel do GhostPredict (GPA).

Para um revisor: este script roda a avaliacao por-mensagem do GPA contra os
concorrentes, em dados reais, e imprime uma tabela-resumo. Tudo com sementes
fixas. Gera resultados_reais.json e cross_domain.json.

Uso:
    python benchmark.py --quick     # ~minutos: 3 dominios, 50 msgs (sanidade)
    python benchmark.py             # completo: 11 dominios, 1000 msgs (~1 h)
    python benchmark.py --no-cross  # pula o experimento cross-dominio

Pre-requisitos (verificados automaticamente):
    - main.exe                  (compilar: ver README)
    - tools/short/uni_cli.exe, smaz_cli.exe   (compilar: ver README)
    - zstd, xz, gzip, brotli no PATH
    - Python: psutil (opcional, p/ memoria), nada mais
    - datasets/ com os conjuntos reais (ver README, secao Dados)
"""
import os, sys, glob, json, random, statistics, subprocess, tempfile, time, shutil, argparse, shutil as _sh

ROOT = os.path.dirname(os.path.abspath(__file__))
DR   = os.path.join(ROOT, "datasets")
MAIN = os.path.join(ROOT, "main.exe")
UNI  = os.path.join(ROOT, "tools", "short", "uni_cli.exe")
SMAZ = os.path.join(ROOT, "tools", "short", "smaz_cli.exe")

SEED, PRIMER_CAP, HELDOUT = 42, 32768, 5000
try:
    import psutil; HAVE_PSUTIL = True
except ImportError:
    HAVE_PSUTIL = False

# --------------------------------------------------------------- extratores
def _lines(path, skip=0, cap=60000):
    out = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for i, ln in enumerate(f):
            if i < skip: continue
            s = ln.rstrip("\n").rstrip("\r")
            if s: out.append(s)
            if len(out) >= cap: break
    return out

def ex_mqtt():      return _lines(os.path.join(DR, "MQTTEEB-D_Final_Dataset/Raw_RealTime_Data/MQTTEEB-D_dataset_loop_1.csv"), skip=1)
def ex_ais():       return _lines(os.path.join(DR, "AIS/ais-2025-01-01"), skip=1)
def ex_intel():     return _lines(os.path.join(DR, "Intelabdata/data.txt"))
def ex_household(): return _lines(os.path.join(DR, "Individual Household Electric Power Consumptio/household_power_consumption.txt"), skip=1)
def ex_geolife():
    out = []; plts = sorted(glob.glob(os.path.join(DR, "Geolife/Data/*/Trajectory/*.plt")))
    random.Random(1).shuffle(plts)
    for p in plts:
        out += _lines(p, skip=6, cap=1000)
        if len(out) >= 60000: break
    return out[:60000]
def ex_log(name):
    return lambda: _lines(os.path.join(DR, "Logs de sistema", name + "_2k.log"))
def ex_sms():
    import csv; out = []
    with open(os.path.join(DR, "SMS Spam Collection/spam.csv"), "r", encoding="utf-8", errors="replace") as f:
        r = csv.reader(f); next(r, None)
        for row in r:
            if len(row) >= 2 and row[1].strip(): out.append(row[1].strip())
    return out
def ex_tweets():
    import csv; out = []
    with open(os.path.join(DR, "Sentiment140 dataset with 1.6 million tweets/training.1600000.processed.noemoticon.csv"),
              "r", encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            if len(row) >= 6 and row[5].strip(): out.append(row[5].strip())
            if len(out) >= 60000: break
    return out

DOMAINS = [
    ("MQTT", ex_mqtt), ("AIS", ex_ais), ("IntelLab", ex_intel), ("Household", ex_household),
    ("Geolife", ex_geolife), ("Log-Apache", ex_log("Apache")), ("Log-Linux", ex_log("Linux")),
    ("Log-OpenSSH", ex_log("OpenSSH")), ("Log-HDFS", ex_log("HDFS")), ("SMS", ex_sms), ("Tweets", ex_tweets),
]
CROSS_FULL = ["MQTT", "AIS", "IntelLab", "Geolife", "Log-Apache"]

# --------------------------------------------------------------- ferramentas
def run_ok(cmd): subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
def sz(p): return os.path.getsize(p)

def _file_tool(b, name, cmd_builder):
    i = os.path.join(TMP, name + "_i"); o = os.path.join(TMP, name + "_o")
    open(i, "wb").write(b); run_ok(cmd_builder(i, o)); return sz(o)

def c_gpa(b, ctx):        return _file_tool(b, "gpa", lambda i, o: [MAIN, "c", i, o])
def c_gpa_primed(b, ctx): return _file_tool(b, "gpap", lambda i, o: [MAIN, "cpf", i, o, ctx["primer"]])
def c_zstd(b, ctx):       return _file_tool(b, "z", lambda i, o: ["zstd", "-19", "-q", "-f", i, "-o", o])
def c_zstd_dict(b, ctx):  return _file_tool(b, "zd", lambda i, o: ["zstd", "-19", "-q", "-f", "-D", ctx["dict"], i, "-o", o])
def c_zstd_lean(b, ctx):  return _file_tool(b, "zl", lambda i, o: ["zstd", "-19", "-q", "-f", "--no-check", "--no-dictID", "-D", ctx["dict"], i, "-o", o])
def c_brotli(b, ctx):     return _file_tool(b, "br", lambda i, o: ["brotli", "-q", "11", "-f", i, "-o", o])
def c_gzip(b, ctx):
    i = os.path.join(TMP, "g")
    open(i, "wb").write(b)
    if os.path.exists(i + ".gz"): os.remove(i + ".gz")
    run_ok(["gzip", "-9", "-k", i]); return sz(i + ".gz")
def c_xz(b, ctx):
    i = os.path.join(TMP, "x")
    open(i, "wb").write(b)
    if os.path.exists(i + ".xz"): os.remove(i + ".xz")
    run_ok(["xz", "-9", "-k", i]); return sz(i + ".xz")
def c_unishox(b, ctx):
    i = os.path.join(TMP, "u"); open(i, "wb").write(b)
    r = subprocess.run([UNI, i], capture_output=True, text=True)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
def c_smaz(b, ctx):
    i = os.path.join(TMP, "sm"); open(i, "wb").write(b)
    r = subprocess.run([SMAZ, i], capture_output=True, text=True)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None

TOOLS = [
    ("GPA-frio", c_gpa), ("GPA-primed", c_gpa_primed), ("gzip-9", c_gzip),
    ("zstd-19", c_zstd), ("zstd-dict", c_zstd_dict), ("zstd-dict-lean", c_zstd_lean),
    ("brotli-11", c_brotli), ("xz-9", c_xz), ("unishox2", c_unishox), ("smaz", c_smaz),
]

def build_primer(heldout, tag):
    corpus = ("\n".join(heldout) + "\n").encode("utf-8", "replace")[-PRIMER_CAP:]
    p = os.path.join(TMP, f"primer_{tag}.bin"); open(p, "wb").write(corpus); return p
def build_dict(heldout, tag):
    train = os.path.join(TMP, f"_train_{tag}.bin")
    open(train, "wb").write(("\n".join(heldout) + "\n").encode("utf-8", "replace"))
    d = os.path.join(TMP, f"dict_{tag}.bin")
    avg = max(16, int(statistics.mean([len(x) for x in heldout])))
    subprocess.run(["zstd", "--train", train, f"-B{avg}", "-o", d, "--maxdict=16384"], capture_output=True, text=True)
    return d if os.path.exists(d) else None
def framing_floor(dct):
    out = {}
    for tag, extra in [("default", []), ("lean", ["--no-check", "--no-dictID"])]:
        i = os.path.join(TMP, "empty"); o = os.path.join(TMP, "empty.zst"); open(i, "wb").write(b"")
        try: run_ok(["zstd", "-19", "-q", "-f"] + extra + ["-D", dct, i, "-o", o]); out[tag] = sz(o)
        except Exception: out[tag] = None
    return out
def agg(lst):
    if not lst: return None
    s = sorted(lst)
    return {"mean": round(statistics.mean(s), 2), "median": s[len(s)//2], "p95": s[int(len(s)*0.95)], "min": s[0], "max": s[-1]}
def throughput_rss(cmd, batch):
    size = sz(batch); rss = 0; t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if HAVE_PSUTIL:
        try:
            ps = psutil.Process(proc.pid)
            while proc.poll() is None:
                try: rss = max(rss, ps.memory_info().rss)
                except Exception: break
        except Exception: pass
    proc.wait(); dt = time.perf_counter() - t0
    return ((size / 1e6) / dt if dt > 0 else 0), rss / 1e6

def prepare(name, extract, n_test):
    recs = extract(); random.Random(SEED).shuffle(recs)
    test = recs[:n_test]; heldout = recs[n_test:n_test + HELDOUT]
    if len(heldout) < 100: heldout = recs[n_test:]
    return {"test": test, "heldout": heldout, "primer": build_primer(heldout, name), "dict": build_dict(heldout, name),
            "orig_mean": round(statistics.mean([len(x.encode("utf-8", "replace")) for x in test]), 2), "n": len(recs)}

def measure_domain(name, D):
    test = D["test"]; ctx = {"primer": D["primer"], "dict": D["dict"]}
    sizes = {t: [] for t, _ in TOOLS}; win = {t: 0 for t, _ in TOOLS}; infl = {t: 0 for t, _ in TOOLS}; origs = []
    for msg in test:
        b = msg.encode("utf-8", "replace"); origs.append(len(b)); per = {}
        for tname, fn in TOOLS:
            if tname.startswith("zstd-dict") and D["dict"] is None: per[tname] = None; continue
            try: s = fn(b, ctx)
            except Exception: s = None
            per[tname] = s
            if s is not None:
                sizes[tname].append(s)
                if s >= len(b): infl[tname] += 1
        valid = {t: s for t, s in per.items() if s is not None}
        if valid:
            best = min(valid.values())
            for t, s in valid.items():
                if s == best: win[t] += 1
    mo = statistics.mean(origs)
    speed = {}; speedset = (test + D["heldout"])
    while len("\n".join(speedset)) < 2_000_000 and len(speedset) < 200000: speedset += D["heldout"]
    batch = os.path.join(TMP, "batch.bin"); open(batch, "wb").write(("\n".join(speedset) + "\n").encode("utf-8", "replace"))
    for tname, cmd in {
        "GPA-frio": [MAIN, "c", batch, os.path.join(TMP, "b.gpa")],
        "GPA-primed": [MAIN, "cpf", batch, os.path.join(TMP, "bp.gpa"), D["primer"]],
        "gzip-9": ["gzip", "-9", "-k", "-f", batch],
        "zstd-19": ["zstd", "-19", "-q", "-f", batch, "-o", os.path.join(TMP, "b.zst")],
        "brotli-11": ["brotli", "-q", "11", "-f", batch, "-o", os.path.join(TMP, "b.br")],
        "xz-9": ["xz", "-9", "-k", "-f", batch],
    }.items():
        try: mb, rss = throughput_rss(cmd, batch); speed[tname] = {"mbps": round(mb, 2), "rss_mb": round(rss, 1)}
        except Exception: speed[tname] = {"mbps": None, "rss_mb": None}
    return {
        "n_records": D["n"], "n_test": len(test), "n_heldout": len(D["heldout"]), "orig_mean": round(mo, 2),
        "ratio": {t: agg(sizes[t]) for t, _ in TOOLS},
        "win_pct": {t: round(100 * win[t] / len(test), 1) for t, _ in TOOLS},
        "inflate_pct": {t: round(100 * infl[t] / len(test), 1) for t, _ in TOOLS},
        "speed": speed,
    }

def cross_domain(DATA, names, n):
    matrix = {}
    for tb in names:
        if tb not in DATA: continue
        testB = DATA[tb]["test"][:n]; matrix[tb] = {}
        for pa in names:
            if pa not in DATA: continue
            vals = []
            for msg in testB:
                b = msg.encode("utf-8", "replace"); i = os.path.join(TMP, "cx"); o = os.path.join(TMP, "cx.gpa")
                open(i, "wb").write(b)
                try: run_ok([MAIN, "cpf", i, o, DATA[pa]["primer"]]); vals.append(sz(o))
                except Exception: pass
            matrix[tb][pa] = round(statistics.mean(vals), 2) if vals else None
        print(f"  teste {tb:<12}: " + "  ".join(f"{pa.split('-')[-1]}={matrix[tb][pa]}" for pa in names if pa in matrix[tb]), flush=True)
    return matrix

# --------------------------------------------------------------- pre-requisitos
def check_prereqs():
    miss = []
    for exe, hint in [(MAIN, "compile main.rs"), (UNI, "compile tools/short"), (SMAZ, "compile tools/short")]:
        if not os.path.exists(exe): miss.append(f"  faltando: {os.path.relpath(exe, ROOT)}  ({hint})")
    for cli in ["zstd", "xz", "gzip", "brotli"]:
        if _sh.which(cli) is None: miss.append(f"  faltando no PATH: {cli}")
    if not os.path.isdir(DR): miss.append(f"  faltando: datasets/  (ver README)")
    if miss:
        print("Pre-requisitos ausentes:"); print("\n".join(miss)); return False
    if not HAVE_PSUTIL: print("Aviso: psutil ausente; a memoria de processo nao sera medida.")
    return True

def print_summary(results, floor):
    print("\n" + "=" * 78)
    print("RESUMO  (tamanho medio do comprimido por mensagem, em bytes)")
    print("=" * 78)
    print(f"{'dominio':<13}{'orig':>6}{'GPA-pr':>8}{'zstd-d':>8}{'zstd-l':>8}{'unish':>7}{'fdict':>7}{'flean':>7}")
    fl = []
    for dom, res in results.items():
        if dom.startswith("_"): continue
        r = res["ratio"]; g = r["GPA-primed"]; z = r["zstd-dict"]; zl = r["zstd-dict-lean"]; u = r.get("unishox2")
        if not (g and z and zl): continue
        fd = z["mean"] / g["mean"]; flf = zl["mean"] / g["mean"]; fl.append(flf)
        print(f"{dom:<13}{res['orig_mean']:>6.0f}{g['mean']:>8.1f}{z['mean']:>8.1f}{zl['mean']:>8.1f}"
              f"{(u['mean'] if u else 0):>7.1f}{fd:>7.2f}{flf:>7.2f}")
    if fl:
        print("-" * 78)
        print(f"fator medio vs zstd-lean (modelo isolado): {sum(fl)/len(fl):.2f}x  |  "
              f"piso de enquadramento zstd-dict: {floor.get('default')} B (lean {floor.get('lean')} B)")

def main():
    global TMP
    ap = argparse.ArgumentParser(description="Validacao reproduzivel do GhostPredict.")
    ap.add_argument("--quick", action="store_true", help="3 dominios, 50 mensagens (sanidade, minutos)")
    ap.add_argument("--no-cross", action="store_true", help="pula o experimento cross-dominio")
    args = ap.parse_args()
    if not check_prereqs(): sys.exit(1)

    n_test = 50 if args.quick else 1000
    doms = [(n, e) for n, e in DOMAINS if n in ("MQTT", "Geolife", "Log-Apache")] if args.quick else DOMAINS
    cross_names = ["MQTT", "Geolife", "Log-Apache"] if args.quick else CROSS_FULL
    cross_n = 30 if args.quick else 100

    # quick escreve em arquivos separados para NUNCA sobrescrever os resultados canonicos
    out_json   = os.path.join(ROOT, "resultados_quick.json" if args.quick else "resultados_reais.json")
    cross_json = os.path.join(ROOT, "cross_quick.json" if args.quick else "cross_domain.json")
    TMP = tempfile.mkdtemp(prefix="gpabench_")
    print(f"Modo: {'QUICK' if args.quick else 'COMPLETO'} | {len(doms)} dominios | {n_test} mensagens/dominio")
    DATA = {}
    for name, ex in doms:
        try: DATA[name] = prepare(name, ex, n_test); print(f"  preparado {name} (n={DATA[name]['n']})", flush=True)
        except Exception as e: print(f"  ERRO {name}: {e}", flush=True)
    floor = framing_floor(DATA["MQTT"]["dict"]) if "MQTT" in DATA and DATA["MQTT"]["dict"] else {}
    results = {"_meta": {"framing_floor_zstd_dict": floor, "n_test": n_test, "heldout": HELDOUT,
                         "primer_cap": PRIMER_CAP, "seed": SEED, "tools": [t for t, _ in TOOLS], "quick": args.quick}}
    for name, _ in doms:
        if name in DATA:
            print(f"[{name}] medindo...", flush=True)
            results[name] = measure_domain(name, DATA[name])
            json.dump(results, open(out_json, "w"), indent=2)
    if not args.no_cross:
        print("\n=== CROSS-DOMINIO (primer da coluna no teste da linha) ===", flush=True)
        matrix = cross_domain(DATA, cross_names, cross_n)
        json.dump(matrix, open(cross_json, "w"), indent=2)
    print_summary(results, floor)
    print("\nSaidas: resultados_reais.json" + ("" if args.no_cross else " + cross_domain.json"))
    shutil.rmtree(TMP, ignore_errors=True)

if __name__ == "__main__":
    main()
