// GhostPredict v9 - Interface CLI e Suíte de Testes Bit-Exatos
// Implementação em conformidade estrita com a Especificação Algorítmica v9

mod ghost_core;

use ghost_core::{GhostPredictEngine, PRIMER};
use std::env;
use std::fs::File;
use std::io::{Read, Write};
use std::time::Instant;
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering};

// ----------------------------------------------------------------------------
// Tracking allocator: mede o pico de heap REALMENTE alocado pelo algoritmo,
// sem o baseline do runtime nem o RSS do SO. Usado pelo subcomando `bench`
// para responder "quanto de RAM a engine pura precisa?" (relevante p/ embarcados).
// ----------------------------------------------------------------------------
struct TrackingAlloc;
static CURRENT: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);

unsafe impl GlobalAlloc for TrackingAlloc {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = System.alloc(layout);
        if !ptr.is_null() {
            let cur = CURRENT.fetch_add(layout.size(), Ordering::Relaxed) + layout.size();
            let mut peak = PEAK.load(Ordering::Relaxed);
            while cur > peak {
                match PEAK.compare_exchange_weak(peak, cur, Ordering::Relaxed, Ordering::Relaxed) {
                    Ok(_) => break,
                    Err(p) => peak = p,
                }
            }
        }
        ptr
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        CURRENT.fetch_sub(layout.size(), Ordering::Relaxed);
        System.dealloc(ptr, layout);
    }
}

#[global_allocator]
static GLOBAL: TrackingAlloc = TrackingAlloc;

/// Zera o pico, fixando-o no nivel atual de heap vivo. Retorna o baseline.
fn heap_reset_peak() -> usize {
    let cur = CURRENT.load(Ordering::Relaxed);
    PEAK.store(cur, Ordering::Relaxed);
    cur
}

fn heap_peak() -> usize {
    PEAK.load(Ordering::Relaxed)
}

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
        "cp" => {
            if args.len() < 4 { eprintln!("Uso: main.exe cp [entrada] [saida.gpa]"); return; }
            let raw = std::fs::read(&args[2]).expect("erro lendo entrada");
            let mut e = GhostPredictEngine::new();
            let comp = e.compress_primed(&raw, PRIMER);
            std::fs::write(&args[3], &comp).expect("erro escrevendo saida");
            println!("primed: {} -> {} bytes", raw.len(), comp.len());
        }
        "dp" => {
            if args.len() < 4 { eprintln!("Uso: main.exe dp [entrada.gpa] [saida]"); return; }
            let payload = std::fs::read(&args[2]).expect("erro lendo entrada");
            let mut e = GhostPredictEngine::new();
            let out = e.decompress_primed(payload, PRIMER);
            std::fs::write(&args[3], &out).expect("erro escrevendo saida");
            println!("primed-dec: {} bytes", out.len());
        }
        "t" | "test" => {
            run_conformance_tests();
        }
        "b" | "bench" => {
            if args.len() < 3 {
                eprintln!("Erro: Uso: main.exe bench [entrada] [iteracoes opcional]");
                return;
            }
            let iters: u32 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(50);
            bench_cmd(&args[2], iters);
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

    println!("Codificando (streaming: LZ77 4KB + PPM-D Ordem-2 + MTF, com fallback stored)...");
    let mut engine = GhostPredictEngine::new();
    let comp_bytes = engine.compress_stream(&raw_bytes);

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

    println!("Decodificando (streaming: PPM-D Ordem-2 + reconstrucao LZ77 inline)...");
    let mut engine = GhostPredictEngine::new();
    let restored_bytes = engine.decompress_stream(payload);

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

// Benchmark IN-MEMORY: cronometra apenas o algoritmo (sem I/O de disco) e mede
// o pico de heap da engine pura. Saida parseable em uma linha "BENCH ...".
fn bench_cmd(input_path: &str, iters: u32) {
    let mut file = match File::open(input_path) {
        Ok(f) => f,
        Err(e) => { eprintln!("Erro ao abrir entrada: {}", e); return; }
    };
    let mut raw_bytes = Vec::new();
    if let Err(e) = file.read_to_end(&mut raw_bytes) {
        eprintln!("Erro ao ler: {}", e); return;
    }
    let orig = raw_bytes.len();

    // --- Heap de COMPRESSAO (working set alem da entrada ja carregada) ---
    let base_c = heap_reset_peak();
    let comp_bytes = {
        let mut engine = GhostPredictEngine::new();
        engine.compress_stream(&raw_bytes)
    };
    let c_heap = heap_peak().saturating_sub(base_c);
    let comp = comp_bytes.len();

    // --- Tempo de COMPRESSAO in-memory (media de `iters`) ---
    let t0 = Instant::now();
    for _ in 0..iters {
        let mut engine = GhostPredictEngine::new();
        let out = engine.compress_stream(&raw_bytes);
        std::hint::black_box(&out);
    }
    let c_time_us = t0.elapsed().as_secs_f64() * 1e6 / iters as f64;

    // --- Heap de DESCOMPRESSAO ---
    let base_d = heap_reset_peak();
    let restored = {
        let mut engine = GhostPredictEngine::new();
        engine.decompress_stream(comp_bytes.clone())
    };
    let d_heap = heap_peak().saturating_sub(base_d);
    let ok = restored == raw_bytes;

    // --- Tempo de DESCOMPRESSAO in-memory ---
    let t1 = Instant::now();
    for _ in 0..iters {
        let mut engine = GhostPredictEngine::new();
        let out = engine.decompress_stream(comp_bytes.clone());
        std::hint::black_box(&out);
    }
    let d_time_us = t1.elapsed().as_secs_f64() * 1e6 / iters as f64;

    println!(
        "BENCH orig={} comp={} c_time_us={:.3} d_time_us={:.3} c_heap={} d_heap={} ok={}",
        orig, comp, c_time_us, d_time_us, c_heap, d_heap, if ok { 1 } else { 0 }
    );
}

// Suíte de conformidade (formato v12: streaming + flag enviesada / nunca inflar).
// Criterios de aprovacao por caso:
//   1. Round-trip lossless (integridade) -- OBRIGATORIO.
//   2. Nunca inflar de forma relevante (modo stored) -- comp <= orig + ~0.1% + 4 B.
//   3. Tamanho gerado == tamanho de referencia (guarda de regressao).
fn run_conformance_tests() {
    println!("\n=== BATERIA DE CONFORMIDADE v12 (streaming, flag enviesada / nunca inflar) ===");

    let test_cases = vec!(
        ("Input Vazio", vec![], 1),
        ("Literal Único", vec![b'A'], 2),
        ("Hello World!", b"Hello World!".to_vec(), 13),
        ("Range Completo 256", (0..=255u8).collect::<Vec<u8>>(), 259),
        ("Repetição Curta (b'A' * 100)", vec![b'A'; 100], 6),
        ("Payload IoT JSON Complexo", {
            let base = b"{\"sensor_id\":42,\"temp\":23.5,\"hum\":60}";
            let mut p = Vec::new();
            for _ in 0..30 {
                p.extend_from_slice(base);
            }
            p
        }, 46)
    );

    let mut passed_all = true;

    for (name, raw_input, expected_gpa_size) in test_cases {
        print!("  -> Teste '{}'... ", name);

        let mut engine_comp = GhostPredictEngine::new();
        let comp_bytes = engine_comp.compress_stream(&raw_input);
        let actual_size = comp_bytes.len();

        // 1. Integridade (lossless)
        let mut engine_decomp = GhostPredictEngine::new();
        let restored_bytes = engine_decomp.decompress_stream(comp_bytes);
        if restored_bytes != raw_input {
            println!("FALHOU! Integridade violada (decodificado != original)");
            passed_all = false;
            continue;
        }

        // 2. Nunca inflar de forma relevante (garantia do modo stored)
        if actual_size > raw_input.len() + 4 + raw_input.len() / 64 {
            println!("FALHOU! Inflou demais: {} B de {} B", actual_size, raw_input.len());
            passed_all = false;
            continue;
        }

        // 3. Regressao de tamanho
        if actual_size != expected_gpa_size {
            println!("ATENCAO: round-trip OK, mas tamanho {} B difere da referencia ({} B)",
                     actual_size, expected_gpa_size);
            passed_all = false;
            continue;
        }

        println!("PASSOU ({} B, integro, sem inflar)", actual_size);
    }

    println!("============================================================");
    if passed_all {
        println!("  RESULTADO FINAL: TODOS OS TESTES PASSARAM COM SUCESSO!");
        println!("  Conformidade v12: lossless + nunca inflar + tamanhos de referencia.");
    } else {
        println!("  RESULTADO FINAL: ALGUNS TESTES FALHARAM. VERIFIQUE A LÓGICA.");
    }
    println!("============================================================\n");
}
