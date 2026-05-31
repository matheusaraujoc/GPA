/* host_test.c - driver de PC para validar o gpa_decoder contra o main.exe (Rust).
 * Le um .gpa (e opcionalmente um primer), decodifica e grava a saida.
 * Compilar:
 *   gcc -O2 -DGPA_ENABLE_PRIMED -I ../components/gpa_decoder/include \
 *       ../components/gpa_decoder/gpa_decoder.c host_test.c -o gpa_host.exe
 */
#include <stdio.h>
#include <stdlib.h>
#include "gpa_decoder.h"

static long readfile(const char *p, uint8_t **buf) {
    FILE *f = fopen(p, "rb"); if (!f) return -1;
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    *buf = (uint8_t *)malloc(n > 0 ? (size_t)n : 1);
    if (n > 0 && fread(*buf, 1, (size_t)n, f) != (size_t)n) { fclose(f); return -1; }
    fclose(f); return n;
}

static uint8_t OUT[1 << 20]; /* 1 MB de saida (host) */

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "uso: %s in.gpa out [primer]\n", argv[0]); return 2; }
    uint8_t *in; long inl = readfile(argv[1], &in);
    if (inl < 0) { perror("entrada"); return 1; }
    int n;
    if (argc >= 4) {
#ifdef GPA_ENABLE_PRIMED
        uint8_t *pr; long pl = readfile(argv[3], &pr);
        if (pl < 0) { perror("primer"); return 1; }
        n = gpa_decompress_primed(in, (size_t)inl, pr, (size_t)pl, OUT, sizeof(OUT));
#else
        fprintf(stderr, "compilado sem GPA_ENABLE_PRIMED\n"); return 2;
#endif
    } else {
        n = gpa_decompress(in, (size_t)inl, OUT, sizeof(OUT));
    }
    if (n < 0) { fprintf(stderr, "erro de decodificacao\n"); return 1; }
    FILE *fo = fopen(argv[2], "wb"); if (!fo) { perror("saida"); return 1; }
    fwrite(OUT, 1, (size_t)n, fo); fclose(fo);
    fprintf(stderr, "decodificado: %d bytes\n", n);
    return 0;
}
