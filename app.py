import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import time
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BG_COLOR = "#1e1e2e"
PANEL_COLOR = "#313244"
TEXT_COLOR = "#cdd6f4"
ACCENT_COLOR = "#89b4fa"
SUCCESS_COLOR = "#a6e3a1"
WARN_COLOR = "#fab387"

class GhostPredictApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GhostPredict v11 - O Predador de Micro-Payloads")
        self.geometry("650x620")
        self.configure(bg=BG_COLOR)
        self._build_ui()

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=10)
        style.configure("Action.TButton", background=ACCENT_COLOR, foreground="#111")
        style.configure("Verify.TButton", background=SUCCESS_COLOR, foreground="#111")

        main_frame = tk.Frame(self, bg=BG_COLOR, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(main_frame, text="GhostPredict v11", font=("Segoe UI", 22, "bold"), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=(0, 5))
        tk.Label(main_frame, text="Micro-Payload Engine (< 4KB) | LZ77 + PPM-D + Aritmético | + modo Primed (prior)", font=("Segoe UI", 10, "italic"), bg=BG_COLOR, fg=TEXT_COLOR).pack(pady=(0, 15))


        btn_frame = tk.Frame(main_frame, bg=BG_COLOR)
        btn_frame.pack(fill=tk.X, pady=10)

        self.btn_compress = ttk.Button(btn_frame, text="1. Comprimir (.gpa)", style="Action.TButton", command=lambda: self.cmd_compress(False))
        self.btn_compress.pack(fill=tk.X, pady=5)

        self.btn_compress_p = ttk.Button(btn_frame, text="1b. Comprimir COM Prior — primed (.gpa)", style="Action.TButton", command=lambda: self.cmd_compress(True))
        self.btn_compress_p.pack(fill=tk.X, pady=5)

        self.btn_decompress = ttk.Button(btn_frame, text="2. Extrair (.gpa)", style="Verify.TButton", command=lambda: self.cmd_decompress(False))
        self.btn_decompress.pack(fill=tk.X, pady=5)

        self.btn_decompress_p = ttk.Button(btn_frame, text="2b. Extrair COM Prior — primed (.gpa)", style="Verify.TButton", command=lambda: self.cmd_decompress(True))
        self.btn_decompress_p.pack(fill=tk.X, pady=5)

        tk.Label(main_frame, text="Console de Telemetria:", bg=BG_COLOR, fg=TEXT_COLOR, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(20, 5))
        self.txt_log = tk.Text(main_frame, height=12, bg=PANEL_COLOR, fg=TEXT_COLOR, font=("Consolas", 9), state=tk.DISABLED, relief=tk.FLAT)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def log(self, message, color=None):
        self.after(0, self._append_log, message, color)

    def _append_log(self, message, color):
        self.txt_log.config(state=tk.NORMAL)
        if color:
            tag_name = f"color_{color}"
            self.txt_log.tag_config(tag_name, foreground=color)
            self.txt_log.insert(tk.END, message + "\n", tag_name)
        else:
            self.txt_log.insert(tk.END, message + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    def toggle_buttons(self, state):
        self.btn_compress.config(state=state)
        self.btn_compress_p.config(state=state)
        self.btn_decompress.config(state=state)
        self.btn_decompress_p.config(state=state)

    def format_size(self, size_bytes):
        if size_bytes < 1024: return f"{size_bytes} Bytes"
        elif size_bytes < 1024 * 1024: return f"{size_bytes / 1024:.2f} KB"
        else: return f"{size_bytes / (1024 * 1024):.2f} MB"

    def compile_rust_engine(self):
        rs_file   = os.path.join(BASE_DIR, "ghost_core.rs")
        main_file = os.path.join(BASE_DIR, "main.rs")
        exe_file  = os.path.join(BASE_DIR, "main.exe")
        
        outdated = False
        if not os.path.exists(exe_file):
            outdated = True
        else:
            exe_mtime = os.path.getmtime(exe_file)
            if os.path.getmtime(main_file) > exe_mtime or os.path.getmtime(rs_file) > exe_mtime:
                outdated = True
                
        if outdated:
            self.log("Detectando compilador Rust nativo (rustc)...", color=ACCENT_COLOR)
            try:
                res = subprocess.run(
                    ["rustc", "+stable-x86_64-pc-windows-gnu", "-C", "opt-level=3", main_file, "-o", exe_file],
                    capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
                    cwd=BASE_DIR
                )
                if res.returncode == 0:
                    self.log("Engine Rust compilada com sucesso (-C opt-level=3)!", color=SUCCESS_COLOR)
                    return True
                else:
                    self.log(f"Falha na compilação Rust: {res.stderr}", color=WARN_COLOR)
            except Exception as e:
                self.log(f"Erro ao tentar executar rustc: {str(e)}", color=WARN_COLOR)
            
            if not os.path.exists(exe_file):
                self.log("AVISO: rustc não detectado no PATH ou falhou ao compilar.", color=WARN_COLOR)
                self.log("Compile manualmente: rustc +stable-x86_64-pc-windows-gnu -C opt-level=3 main.rs -o main.exe", color=WARN_COLOR)
                return False
        return True

    def cmd_compress(self, primed=False):
        input_path = filedialog.askopenfilename(title="Selecione o arquivo para comprimir")
        if not input_path: return

        output_path = filedialog.asksaveasfilename(title="Salvar como", defaultextension=".gpa", filetypes=[("GhostPredict Archive", "*.gpa")])
        if not output_path: return

        self.toggle_buttons(tk.DISABLED)
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.config(state=tk.DISABLED)

        threading.Thread(target=self._worker_compress, args=(input_path, output_path, "cp" if primed else "c"), daemon=True).start()

    def _worker_compress(self, input_path, output_path, cmd="c"):
        try:
            start_time = time.time()
            modo = "PRIMED (com prior embutido)" if cmd == "cp" else "FAST-START"
            self.log(f"\n--- INICIANDO COMPRESSÃO {modo} ---", color=ACCENT_COLOR)

            orig_size = os.path.getsize(input_path)
            self.log(f"Tamanho Original: {self.format_size(orig_size)}")

            if self.compile_rust_engine():
                self.log("Executando compressão nativa em Rust...")
                exe_path = os.path.join(BASE_DIR, "main.exe")
                res = subprocess.run([exe_path, cmd, input_path, output_path],
                                     capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
                                     cwd=BASE_DIR)
                if res.stdout:
                    self.log(res.stdout.strip())
                if res.stderr:
                    self.log(res.stderr.strip(), color=WARN_COLOR)
                
                if res.returncode != 0:
                    raise RuntimeError(f"Engine Rust retornou erro (código {res.returncode})")
            else:
                self.log("Falha ao preparar Engine Rust. Abortando.", color=WARN_COLOR)
                return
            
            comp_size = os.path.getsize(output_path)
            elapsed = time.time() - start_time
            taxa = (1 - (comp_size / orig_size)) * 100 if orig_size > 0 else 0
            
            self.log("-" * 30)
            self.log(f"Tamanho Final: {self.format_size(comp_size)}")
            if taxa > 0:
                self.log(f"Redução de Tamanho: {taxa:.2f}%", color=SUCCESS_COLOR)
            else:
                self.log(f"Inflação de Tamanho: {abs(taxa):.2f}%", color=WARN_COLOR)
            self.log(f"Tempo Decorrido: {elapsed:.2f} segundos", color=TEXT_COLOR)

        except Exception as e:
            self.log(f"ERRO: {str(e)}", color=WARN_COLOR)
        finally:
            self.after(0, lambda: self.toggle_buttons(tk.NORMAL))

    def cmd_decompress(self, primed=False):
        input_path = filedialog.askopenfilename(title="Selecione o arquivo .gpa", filetypes=[("GhostPredict Archive", "*.gpa")])
        if not input_path: return

        output_path = filedialog.asksaveasfilename(title="Salvar extração como")
        if not output_path: return

        self.toggle_buttons(tk.DISABLED)
        modo = "PRIMED (com prior)" if primed else "padrão"
        self.log(f"\n--- INICIANDO DESCOMPRESSÃO {modo} ---", color=ACCENT_COLOR)
        threading.Thread(target=self._worker_decompress, args=(input_path, output_path, "dp" if primed else "d"), daemon=True).start()

    def _worker_decompress(self, input_path, output_path, cmd="d"):
        try:
            start_time = time.time()
            comp_size = os.path.getsize(input_path)
            self.log(f"Arquivo GPA: {self.format_size(comp_size)}")

            if self.compile_rust_engine():
                self.log("Executando descompressão nativa em Rust...")
                exe_path = os.path.join(BASE_DIR, "main.exe")
                res = subprocess.run([exe_path, cmd, input_path, output_path],
                                     capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
                                     cwd=BASE_DIR)
                if res.stdout:
                    self.log(res.stdout.strip())
                if res.stderr:
                    self.log(res.stderr.strip(), color=WARN_COLOR)
                    
                if res.returncode != 0:
                    raise RuntimeError(f"Engine Rust retornou erro (código {res.returncode})")
            else:
                self.log("Falha ao preparar Engine Rust. Abortando.", color=WARN_COLOR)
                return
            
            restored_size = os.path.getsize(output_path)
            elapsed = time.time() - start_time
            
            self.log("-" * 30)
            self.log(f"Tamanho Restaurado: {self.format_size(restored_size)}", color=SUCCESS_COLOR)
            self.log(f"Tempo Decorrido: {elapsed:.2f} segundos", color=TEXT_COLOR)

        except Exception as e:
            self.log(f"ERRO CRÍTICO: {str(e)}", color=WARN_COLOR)
        finally:
            self.after(0, lambda: self.toggle_buttons(tk.NORMAL))

if __name__ == "__main__":
    app = GhostPredictApp()
    app.mainloop()