/* vectors_test.c - Valida no PC os vetores gerados para o firmware do ESP32.
 *
 * Roda o MESMO decoder C que vai para a placa sobre gpa_test_vectors.h e confere
 * o round-trip byte a byte. Serve para pegar erro de geracao antes de gravar.
 *
 * Compilar (modo frio):
 *   gcc -O2 -I ../components/gpa_decoder/include -I ../main \
 *       ../components/gpa_decoder/gpa_decoder.c vectors_test.c -o vectors_test.exe
 *
 * Compilar (modo com prior):
 *   gcc -O2 -DGPA_ENABLE_PRIMED -I ../components/gpa_decoder/include -I ../main \
 *       ../components/gpa_decoder/gpa_decoder.c vectors_test.c -o vectors_test.exe
 */
#include <stdio.h>
#include <string.h>
#include "gpa_decoder.h"
#include "gpa_test_vectors.h"

static unsigned char out_buf[4096];

int main(void) {
    int falhas = 0;
    unsigned soma_orig = 0, soma_cold = 0, soma_primed = 0;

    printf("validando %d vetores com o decoder C\n\n", GPA_N_VECTORS);
    for (int i = 0; i < GPA_N_VECTORS; i++) {
        const gpa_vector_t *v = &GPA_VECTORS[i];

        int n = gpa_decompress(v->cold, v->cold_len, out_buf, sizeof(out_buf));
        int ok_cold = (n == (int)v->orig_len) && (memcmp(out_buf, v->orig, v->orig_len) == 0);
        if (!ok_cold) falhas++;

        int ok_primed = 1;
#ifdef GPA_ENABLE_PRIMED
        memset(out_buf, 0, sizeof(out_buf));
        int m = gpa_decompress_primed(v->primed, v->primed_len,
                                      GPA_PRIMER, GPA_PRIMER_LEN,
                                      out_buf, sizeof(out_buf));
        ok_primed = (m == (int)v->orig_len) && (memcmp(out_buf, v->orig, v->orig_len) == 0);
        if (!ok_primed) falhas++;
        soma_primed += v->primed_len;
#endif
        soma_orig += v->orig_len;
        soma_cold += v->cold_len;

        printf("  msg %2d: orig %3u B  frio %3u B [%s]", i, v->orig_len, v->cold_len,
               ok_cold ? "OK" : "FALHOU");
#ifdef GPA_ENABLE_PRIMED
        printf("  primed %3u B [%s]", v->primed_len, ok_primed ? "OK" : "FALHOU");
#endif
        printf("\n");
    }

    printf("\nmedia: orig %.1f B  frio %.1f B", (double)soma_orig / GPA_N_VECTORS,
           (double)soma_cold / GPA_N_VECTORS);
#ifdef GPA_ENABLE_PRIMED
    printf("  primed %.1f B (fator %.2fx sobre o original)",
           (double)soma_primed / GPA_N_VECTORS, (double)soma_orig / (double)soma_primed);
#endif
    printf("\n\n%s\n", falhas == 0 ? "TODOS OS VETORES BIT-EXATOS" : "HOUVE FALHA");
    return falhas == 0 ? 0 : 1;
}
