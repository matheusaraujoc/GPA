/* gpa_example_main.c - Benchmark do decoder GPA no ESP32.
 *
 * Mede, no alvo fisico, o que a analise estatica (idf.py size) nao alcanca:
 *   - corretude bit a bit de cada mensagem held-out;
 *   - latencia de descompressao por mensagem (min, mediana, media, p95, max);
 *   - vazao equivalente;
 *   - heap dinamico consumido (deve ser zero: o decoder nao aloca);
 *   - folga de pilha da tarefa (stack high water mark).
 *
 * Os vetores vem de gpa_test_vectors.h, gerado por embedded/tools/gen_vectors.py
 * a partir de mensagens held-out, no mesmo protocolo do benchmark.py.
 *
 * Compile o modo frio (padrao, ~19 KB de .bss) ou o modo com prior
 * (-DGPA_ENABLE_PRIMED no CMakeLists do componente, ~259 KB de .bss).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "esp_system.h"

#include "gpa_decoder.h"
#include "gpa_test_vectors.h"

/* Repeticoes por mensagem. O timer tem resolucao de 1 us; com dezenas de
 * repeticoes a media fica estavel mesmo para decodificacoes muito rapidas.
 * O modo com prior reaquece o modelo a cada mensagem e custa ordens de
 * grandeza mais, entao usa menos repeticoes para o teste nao levar minutos. */
#define REPS 200
#define REPS_PRIMED 10

static unsigned char out_buf[2048];
static int64_t samples[REPS];
/* ultimo retorno do decoder, para distinguir erro de round-trip de erro de recurso */
static int ultimo_n = 0;

static int cmp_i64(const void *a, const void *b) {
    int64_t x = *(const int64_t *)a, y = *(const int64_t *)b;
    return (x > y) - (x < y);
}

typedef struct {
    int64_t min, med, mean, p95, max;
} stats_t;

static stats_t compute_stats(int64_t *v, int n) {
    stats_t s;
    int64_t sum = 0;
    qsort(v, n, sizeof(int64_t), cmp_i64);
    for (int i = 0; i < n; i++) sum += v[i];
    s.min = v[0];
    s.max = v[n - 1];
    s.med = v[n / 2];
    s.p95 = v[(int)(n * 0.95) >= n ? n - 1 : (int)(n * 0.95)];
    s.mean = sum / n;
    return s;
}

/* Executa REPS decodificacoes de um vetor e devolve as estatisticas de latencia.
 * `ok` recebe 1 se a saida bate byte a byte com o original. */
static stats_t bench_one(const unsigned char *in, unsigned in_len,
                         const unsigned char *orig, unsigned orig_len,
                         int primed, int *ok)
{
    const int reps = primed ? REPS_PRIMED : REPS;
    *ok = 1;
    int64_t lote_ini = esp_timer_get_time();
    for (int r = 0; r < reps; r++) {
        int64_t t0 = esp_timer_get_time();
        int n;
#ifdef GPA_ENABLE_PRIMED
        if (primed)
            n = gpa_decompress_primed(in, in_len, GPA_PRIMER, GPA_PRIMER_LEN,
                                      out_buf, sizeof(out_buf));
        else
#endif
            n = gpa_decompress(in, in_len, out_buf, sizeof(out_buf));
        int64_t t1 = esp_timer_get_time();
        samples[r] = t1 - t0;
        ultimo_n = n;

        if (n != (int)orig_len || memcmp(out_buf, orig, orig_len) != 0) *ok = 0;
    }
    int64_t lote_fim = esp_timer_get_time();

    stats_t s = compute_stats(samples, reps);
    /* A media vem do tempo do lote inteiro dividido pelas repeticoes: nao sofre
     * o arredondamento de 1 us que afeta cada medida individual. */
    s.mean = (lote_fim - lote_ini) / reps;
    return s;
}

static void run_suite(int primed)
{
    const char *modo = primed ? "COM PRIOR (primed)" : "FRIO (sem prior)";
    printf("\n=== MODO %s === (%d repeticoes por mensagem)\n",
           modo, primed ? REPS_PRIMED : REPS);
    printf("msg  orig  .gpa  fator   ok    min    med   media    p95    max   (us)\n");
    printf("---------------------------------------------------------------------\n");

    int64_t soma_media = 0, soma_orig = 0, soma_comp = 0;
    int falhas = 0;

    for (int i = 0; i < GPA_N_VECTORS; i++) {
        const gpa_vector_t *v = &GPA_VECTORS[i];
        const unsigned char *in = v->cold;
        unsigned in_len = v->cold_len;
#ifdef GPA_ENABLE_PRIMED
        if (primed) { in = v->primed; in_len = v->primed_len; }
#endif
        int ok = 0;
        stats_t s = bench_one(in, in_len, v->orig, v->orig_len, primed, &ok);
        if (!ok) falhas++;
        if (!ok && i == 0 && ultimo_n < 0)
            printf("  !! decoder retornou %d: sem heap para as tabelas LZ ou "
                   "buffer pequeno demais\n", ultimo_n);

        printf("%3d  %4u  %4u  %5.2fx  %-3s %6lld %6lld %6lld %6lld %6lld\n",
               i, v->orig_len, in_len, (double)v->orig_len / (double)in_len,
               ok ? "OK" : "ERR",
               (long long)s.min, (long long)s.med, (long long)s.mean,
               (long long)s.p95, (long long)s.max);

        soma_media += s.mean;
        soma_orig += v->orig_len;
        soma_comp += in_len;

        /* Cede a CPU entre mensagens. No modo com prior cada mensagem ocupa
         * dezenas de ms e a tarefa ociosa nao rodaria, disparando o watchdog. */
        vTaskDelay(1);
    }

    int64_t lat_media = soma_media / GPA_N_VECTORS;
    double vazao = lat_media > 0
        ? ((double)soma_orig / (double)GPA_N_VECTORS) / ((double)lat_media / 1e6) / 1024.0
        : 0.0;

    printf("---------------------------------------------------------------------\n");
    printf("mensagens.......: %d (%d falha(s) de round-trip)\n", GPA_N_VECTORS, falhas);
    printf("tamanho medio...: original %.1f B -> comprimido %.1f B (fator %.2fx)\n",
           (double)soma_orig / GPA_N_VECTORS, (double)soma_comp / GPA_N_VECTORS,
           (double)soma_orig / (double)soma_comp);
    printf("latencia media..: %lld us por mensagem\n", (long long)lat_media);
    printf("vazao equiv.....: %.1f KB/s de dados reconstruidos\n", vazao);
    printf("integridade.....: %s\n", falhas == 0 ? "TODAS bit-exatas" : "HOUVE FALHA");
}

void app_main(void)
{
    printf("\n============================================================\n");
    printf(" GhostPredict - benchmark do decoder no ESP32\n");
    printf("============================================================\n");
    printf("CPU.............: %d MHz\n", CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ);
    printf("repeticoes/msg..: %d\n", REPS);
#ifdef GPA_ENABLE_PRIMED
    printf("primer..........: %d B (na flash)\n", GPA_PRIMER_LEN);
#else
    printf("primer..........: desabilitado (modo frio)\n");
#endif

    size_t heap_ini = heap_caps_get_free_size(MALLOC_CAP_DEFAULT);
    size_t heap_min_ini = esp_get_minimum_free_heap_size();

    run_suite(0);
#ifdef GPA_ENABLE_PRIMED
    run_suite(1);
#endif

    size_t heap_fim = heap_caps_get_free_size(MALLOC_CAP_DEFAULT);
    size_t heap_min_fim = esp_get_minimum_free_heap_size();
    UBaseType_t folga_pilha = uxTaskGetStackHighWaterMark(NULL);

    printf("\n=== RECURSOS ===\n");
    printf("heap livre......: %u B antes, %u B depois (delta %d B)\n",
           (unsigned)heap_ini, (unsigned)heap_fim, (int)heap_ini - (int)heap_fim);
    printf("heap min. hist..: %u B antes, %u B depois\n",
           (unsigned)heap_min_ini, (unsigned)heap_min_fim);
    printf("folga de pilha..: %u B nunca usados na tarefa app_main\n",
           (unsigned)folga_pilha * (unsigned)sizeof(StackType_t));
    printf("\nO decoder nao aloca: o delta de heap deve ser 0 e todo o consumo\n"
           "aparece no .bss estatico. Confirme com: idf.py size-components\n");
    printf("============================================================\n");
}
