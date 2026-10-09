#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reseta o ESP32 e captura a saida serial do benchmark por N segundos.

Alternativa nao interativa ao `idf.py monitor`, que so termina com Ctrl+].
Usa o circuito de auto-reset das placas de desenvolvimento: RTS liga em EN
(reset) e DTR em GPIO0 (modo de boot).

Uso: python embedded/tools/capture_serial.py [porta] [segundos] [saida.txt]
"""
import sys
import time

import serial

porta = sys.argv[1] if len(sys.argv) > 1 else "COM3"
segundos = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
saida = sys.argv[3] if len(sys.argv) > 3 else None

with serial.Serial(porta, 115200, timeout=0.2) as s:
    # reset para boot normal: GPIO0 alto, pulso de EN em baixo
    s.setDTR(False)
    s.setRTS(True)
    time.sleep(0.15)
    s.reset_input_buffer()
    s.setRTS(False)

    fim = time.time() + segundos
    linhas = []
    viu_recursos = False
    while time.time() < fim:
        raw = s.readline()
        if not raw:
            continue
        linha = raw.decode("utf-8", "replace").rstrip("\r\n")
        linhas.append(linha)
        print(linha, flush=True)
        # o relatorio termina com uma regua de '=' logo apos a secao de recursos
        if "RECURSOS" in linha:
            viu_recursos = True
        elif viu_recursos and linha.startswith("=" * 20):
            break

if saida:
    with open(saida, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    print("\n[salvo em %s]" % saida)
