# Projeto ESP-IDF de exemplo para o decoder GPA.
# Uso: idf.py set-target esp32 && idf.py build && idf.py size
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(gpa_decoder_example)
