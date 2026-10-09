# Componente ESP-IDF do decoder GPA (no_std, sem alocacao dinamica).
# Por padrao registra apenas o modo normal (footprint ~19 KB de .bss).
# Para habilitar o modo com prior, descomente a linha de definicao abaixo
# (adiciona as tabelas LZ; ver README, secao Footprint).
idf_component_register(SRCS "gpa_decoder.c"
                       INCLUDE_DIRS "include")
target_compile_definitions(${COMPONENT_LIB} PUBLIC GPA_ENABLE_PRIMED)
# Buffer de trabalho ajustado ao primer real (16 KB) mais a maior mensagem, em vez
# do padrao de 48 KB. Libera 30 KB do segmento estatico, que viram heap para as
# tabelas LZ. O decoder valida os limites, entao um valor pequeno demais retorna
# erro em vez de corromper.
target_compile_definitions(${COMPONENT_LIB} PUBLIC GPA_WORK_SIZE=18432)
