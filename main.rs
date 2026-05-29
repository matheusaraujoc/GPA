// GhostPredict v9 - Interface CLI e Suíte de Testes Bit-Exatos
// Implementação em conformidade estrita com a Especificação Algorítmica v9

mod ghost_core;

use ghost_core::{GhostPredictEngine, LZ77, lz77_reconstruct};
use std::env;
use std::fs::File;
use std::io::{Read, Write};
use std::time::Instant;

fn main() {
    let args: Vec<String> = env::args().collect();

    if args.len() < 2 {
        print_banner();
        run_conformance_tests();
        println!("\nPressione Enter para fechar...");
        let mut input = String::new();
        let _ = std::io::stdin().read_line(&mut input);
        return;
    }

    let command = &args[1];

    match command.as_str() {
        "c" | "compress" => {
            if args.len() < 4 {
                eprintln!("Erro: Faltam argumentos. Uso: main.exe c [entrada] [saida.gpa]");
                return;
            }
            compress_file_cmd(&args[2], &args[3]);
        }
        "d" | "decompress" => {
            if args.len() < 4 {
                eprintln!("Erro: Faltam argumentos. Uso: main.exe d [entrada.gpa] [saida]");
                return;
            }
            decompress_file_cmd(&args[2], &args[3]);
        }
        "t" | "test" => {
            run_conformance_tests();
        }
        _ => {
            eprintln!("Erro: Comando desconhecido '{}'.", command);
            print_usage();
        }
    }
}

fn print_banner() {
    println!("============================================================");
    println!("        GHOSTPREDICT v9 - CLI & SUÍTE DE CONFORMIDADE");
    println!("      Engine Híbrida Lossless Zero-Overhead (Rust)");
    println!("============================================================");
}

fn print_usage() {
    println!("\nUso:");
    println!("  main.exe c [entrada] [saida.gpa]  : Comprimir arquivo");
    println!("  main.exe d [entrada.gpa] [saida]  : Descomprimir arquivo");
    println!("  main.exe t                        : Executar testes de conformidade Seção 13\n");
}

fn compress_file_cmd(input_path: &str, output_path: &str) {
    let start_time = Instant::now();
    println!("Lendo arquivo original: {}...", input_path);

    let mut file = match File::open(input_path) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("Erro ao abrir arquivo de entrada: {}", e);
            return;
        }
    };

    let mut raw_bytes = Vec::new();
    if let Err(e) = file.read_to_end(&mut raw_bytes) {
        eprintln!("Erro ao ler arquivo: {}", e);
        return;
    }

    let orig_size = raw_bytes.len();
    println!("Tamanho Original: {} bytes", orig_size);

    println!("Executando pré-pass LZ77 (janela 4KB + lazy match)...");
    let mut lz = LZ77::new();
    let tokens = lz.parse(&raw_bytes);

    println!("Codificando via PPM-D Ordem-2 e Histórico MTF...");
    let mut engine = GhostPredictEngine::new();
    let comp_bytes = engine.compress(&tokens);

    let comp_size = comp_bytes.len();
    
    let mut out_file = match File::create(output_path) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("Erro ao criar arquivo de saída: {}", e);
            return;
        }
    };

    if let Err(e) = out_file.write_all(&comp_bytes) {
        eprintln!("Erro ao escrever payload comprimido: {}", e);
        return;
    }

    let elapsed = start_time.elapsed().as_secs_f64();
    let reduction = if orig_size > 0 {
        (1.0 - (comp_size as f64 / orig_size as f64)) * 100.0
    } else {
        0.0
    };

    println!("------------------------------------------------------------");
    println!("Tamanho Comprimido: {} bytes", comp_size);
    println!("Redução de Tamanho: {:.2}%", reduction);
    println!("Tempo Decorrido: {:.4} segundos", elapsed);
    println!("Operação concluída com sucesso!");
    println!("------------------------------------------------------------");
}

fn decompress_file_cmd(input_path: &str, output_path: &str) {
    let start_time = Instant::now();
    println!("Lendo arquivo comprimido: {}...", input_path);

    let mut file = match File::open(input_path) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("Erro ao abrir arquivo de entrada: {}", e);
            return;
        }
    };

    let mut payload = Vec::new();
    if let Err(e) = file.read_to_end(&mut payload) {
        eprintln!("Erro ao ler arquivo: {}", e);
        return;
    }

    println!("Decodificando bits com PPM-D Ordem-2...");
    let mut engine = GhostPredictEngine::new();
    let tokens = engine.decompress(payload);

    println!("Reconstruindo fluxo original LZ77...");
    let restored_bytes = lz77_reconstruct(&tokens);

    let mut out_file = match File::create(output_path) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("Erro ao criar arquivo de saída: {}", e);
            return;
        }
    };

    if let Err(e) = out_file.write_all(&restored_bytes) {
        eprintln!("Erro ao escrever arquivo restaurado: {}", e);
        return;
    }

    let elapsed = start_time.elapsed().as_secs_f64();
    println!("------------------------------------------------------------");
    println!("Tamanho Restaurado: {} bytes", restored_bytes.len());
    println!("Tempo Decorrido: {:.4} segundos", elapsed);
    println!("Operação concluída com sucesso!");
    println!("------------------------------------------------------------");
}

// Suíte de testes automáticos bit-exatos descritos na Seção 13 do spec.md
fn run_conformance_tests() {
    println!("\n=== INICIANDO BATERIA DE TESTES DE CONFORMIDADE BIT-EXATOS (SEÇÃO 13) ===");

    let test_cases = vec!(
        ("Input Vazio", vec![], 1),
        ("Literal Único", vec![b'A'], 2),
        ("Hello World!", b"Hello World!".to_vec(), 13),
        ("Range Completo 256", (0..=255u8).collect::<Vec<u8>>(), 285),
        ("Repetição Curta (b'A' * 100)", vec![b'A'; 100], 6),
        ("Payload IoT JSON Complexo", {
            let base = b"{\"sensor_id\":42,\"temp\":23.5,\"hum\":60}";
            let mut p = Vec::new();
            for _ in 0..30 {
                p.extend_from_slice(base);
            }
            p
        }, 45)
    );

    let mut passed_all = true;

    for (name, raw_input, expected_gpa_size) in test_cases {
        print!("  -> Teste '{}'... ", name);
        
        // 1. Compressão
        let mut lz = LZ77::new();
        let tokens = lz.parse(&raw_input);
        
        let mut engine_comp = GhostPredictEngine::new();
        let comp_bytes = engine_comp.compress(&tokens);
        let actual_size = comp_bytes.len();

        if actual_size != expected_gpa_size {
            println!("FALHOU! Tamanho gerado ({} B) difere do esperado ({} B)", actual_size, expected_gpa_size);
            passed_all = false;
            continue;
        }

        // 2. Descompressão e Integridade (Lossless)
        let mut engine_decomp = GhostPredictEngine::new();
        let decomp_tokens = engine_decomp.decompress(comp_bytes);
        let restored_bytes = lz77_reconstruct(&decomp_tokens);

        if restored_bytes != raw_input {
            println!("FALHOU! O arquivo decodificado difere dos bytes originais (Integridade Violada)");
            passed_all = false;
            continue;
        }

        println!("PASSOU (Bit-Exato: {} bytes)", actual_size);
    }

    println!("============================================================");
    if passed_all {
        println!("  RESULTADO FINAL: TODOS OS TESTES PASSARAM COM SUCESSO!");
        println!("  A implementação Rust é 100% CONFORME com a especificação v9.");
    } else {
        println!("  RESULTADO FINAL: ALGUNS TESTES FALHARAM. VERIFIQUE A LÓGICA.");
    }
    println!("============================================================\n");
}
