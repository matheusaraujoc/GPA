/* gpa_decoder.h - Decodificador de referencia do GhostPredict (GPA) em C, no_std,
 * SEM alocacao dinamica (modelo e tabelas em memoria estatica).
 *
 * Bit-exato com o motor Rust (ghost_core.rs). Porta apenas a DESCOMPRESSAO:
 *   - gpa_decompress         : modo normal (.gpa sem prior). Footprint ~19 KB (so o modelo).
 *   - gpa_decompress_primed  : modo com prior. Requer GPA_ENABLE_PRIMED; adiciona as
 *                              tabelas LZ (~192 KB) usadas para aquecer o modelo com o primer.
 *
 * Nenhuma chamada a malloc/Vec: todo o estado vive em variaveis estaticas no .c.
 * Veja README.md (idf.py size) para a validacao do footprint sem hardware.
 */
#ifndef GPA_DECODER_H
#define GPA_DECODER_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Descomprime um buffer .gpa (modo normal) em `out`.
 * Retorna o numero de bytes decodificados, ou -1 em erro (estouro de `out_cap`). */
int gpa_decompress(const uint8_t *in, size_t in_len, uint8_t *out, size_t out_cap);

#ifdef GPA_ENABLE_PRIMED
/* Descomprime um buffer .gpa gerado com prior (cp/cpf). O MESMO `primer`, byte a byte,
 * usado na compressao deve ser fornecido. Retorna bytes decodificados ou -1.
 * Usa tabelas LZ estaticas para aquecer o modelo (footprint maior; ver README). */
int gpa_decompress_primed(const uint8_t *in, size_t in_len,
                          const uint8_t *primer, size_t primer_len,
                          uint8_t *out, size_t out_cap);
#endif

#ifdef __cplusplus
}
#endif

#endif /* GPA_DECODER_H */
