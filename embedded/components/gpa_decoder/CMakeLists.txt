# Componente ESP-IDF do decoder GPA (no_std, sem alocacao dinamica).
# Por padrao registra apenas o modo normal (footprint ~19 KB de .bss).
# Para habilitar o modo com prior, descomente a linha de definicao abaixo
# (adiciona as tabelas LZ; ver README, secao Footprint).
idf_component_register(SRCS "gpa_decoder.c"
                       INCLUDE_DIRS "include")
# target_compile_definitions(${COMPONENT_LIB} PUBLIC GPA_ENABLE_PRIMED)
