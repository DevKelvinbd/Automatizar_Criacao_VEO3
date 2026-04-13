"""
launcher.py
===========
Ponto de entrada do executável distribuído (PyInstaller).
# Build v1.0-trava-maio2026

Modos de operação
-----------------
  Normal  → inicia Flask + abre browser automaticamente
  --bot   → bootstrap interno: executa bot_flow.main()
  --fatiar → bootstrap interno: executa fatiador
"""

import os
import sys
import shutil
import socket
import threading
import webbrowser
import time
import io
from datetime import date
from pathlib import Path

# ── Força UTF-8 no stdout/stderr (Windows usa cp1252 por padrão) ────────────
if sys.stdout is None or not hasattr(sys.stdout, "reconfigure"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer if sys.stdout else open(os.devnull, "wb"), encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer if sys.stderr else open(os.devnull, "wb"), encoding="utf-8", errors="replace")
else:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Diretórios ────────────────────────────────────────────────────────────────
def _default_data_dir() -> Path:
    """Retorna o diretório de dados do usuário conforme o sistema operacional."""
    if sys.platform == "win32":
        # Windows: C:\Users\usuario\AppData\Roaming\VEO3
        return Path(os.environ.get("APPDATA", Path.home())) / "VEO3"
    else:
        # macOS
        return Path.home() / "Library" / "Application Support" / "VEO3"


if getattr(sys, "frozen", False):
    # Dentro do executável — recursos read-only extraídos pelo PyInstaller
    BUNDLE_DIR = Path(sys._MEIPASS)
    # Dados do usuário: gravável, persiste entre execuções
    DATA_DIR = _default_data_dir()
else:
    BUNDLE_DIR = Path(__file__).parent
    DATA_DIR   = BUNDLE_DIR

# Expõe para todos os módulos importados (app.py, bot_flow.py, fatiador.py)
os.environ["VEO3_BUNDLE_DIR"] = str(BUNDLE_DIR)
os.environ["VEO3_DATA_DIR"]   = str(DATA_DIR)

# ── Trava de expiração ────────────────────────────────────────────────────────
_EXPIRATION_DATE = date(2026, 5, 10)

def _check_expiration() -> None:
    """Bloqueia completamente o sistema após a data de expiração."""
    if date.today() >= _EXPIRATION_DATE:
        msg = (
            "Esta versão do VEO3 expirou em 10/05/2026.\n"
            "Entre em contato com o suporte para obter uma versão atualizada."
        )
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("VEO3 — Versão Expirada", msg)
            root.destroy()
        except Exception:
            print("=" * 55)
            print("  VEO3 — VERSÃO EXPIRADA")
            print(f"  {msg}")
            print("=" * 55)
        sys.exit(1)

# ── Verificação de licença ────────────────────────────────────────────────────

def _show_activation_screen(client) -> None:
    """Tkinter window for license key activation. Blocks until success or close."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.title("VEO3 — Ativação de Licença")
        root.geometry("480x260")
        root.resizable(False, False)

        tk.Label(root, text="🔑 Ativar VEO3 Automator", font=("Helvetica", 16, "bold")).pack(pady=(20, 5))
        tk.Label(root, text="Insira sua chave de licença para continuar.", font=("Helvetica", 11)).pack(pady=(0, 15))

        entry_var = tk.StringVar()
        entry = tk.Entry(root, textvariable=entry_var, width=36, font=("Courier", 13), justify="center")
        entry.pack(pady=5)
        entry.insert(0, "VEO3-")

        status_var = tk.StringVar()
        status_label = tk.Label(root, textvariable=status_var, font=("Helvetica", 10), fg="red")
        status_label.pack(pady=5)

        activated = [False]

        def on_activate():
            key = entry_var.get().strip()
            if not key or len(key) < 10:
                status_var.set("Chave inválida. Formato: VEO3-XXXX-XXXX-XXXX-XXXX")
                return
            status_var.set("Ativando...")
            root.update()
            result = client.activate(key)
            if result.success:
                activated[0] = True
                root.destroy()
            else:
                status_var.set(f"Erro: {result.error}")

        tk.Button(root, text="Ativar", command=on_activate, width=18, font=("Helvetica", 11, "bold"),
                  bg="#C62828", fg="white", activebackground="#8E0000", activeforeground="white").pack(pady=10)

        root.protocol("WM_DELETE_WINDOW", lambda: (root.destroy(),))
        root.mainloop()

        if not activated[0]:
            sys.exit(0)
    except ImportError:
        # No tkinter — console fallback
        print("=" * 55)
        print("  VEO3 — ATIVAÇÃO DE LICENÇA")
        print("  Insira sua chave (VEO3-XXXX-XXXX-XXXX-XXXX):")
        print("=" * 55)
        key = input("> ").strip()
        if not key:
            sys.exit(0)
        result = client.activate(key)
        if result.success:
            print("Licença ativada com sucesso!")
        else:
            print(f"Erro: {result.error}")
            sys.exit(1)


def _show_blocked_screen(status) -> None:
    """Show error popup for blocked license states."""
    from licensing.license_client import LicenseStatus

    messages = {
        LicenseStatus.REVOKED: (
            "Licença Revogada",
            "Sua licença foi revogada.\nEntre em contato com o suporte."
        ),
        LicenseStatus.EXPIRED_OFFLINE: (
            "Período Offline Expirado",
            "Você está offline há mais de 7 dias.\nConecte-se à internet para validar sua licença."
        ),
        LicenseStatus.EXPIRED: (
            "Licença Expirada",
            "Sua licença expirou.\nEntre em contato para renovar."
        ),
    }
    title, msg = messages.get(status, ("Licença Inválida", "Sua licença não é válida."))

    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(f"VEO3 — {title}", msg)
        root.destroy()
    except Exception:
        print("=" * 55)
        print(f"  VEO3 — {title}")
        print(f"  {msg}")
        print("=" * 55)


def _license_watchdog(client, interval_hours: float = 6.0) -> None:
    """Background thread that re-validates the license periodically."""
    from licensing.license_client import LicenseStatus
    while True:
        time.sleep(interval_hours * 3600)
        try:
            status = client.validate()
            os.environ["VEO3_LICENSE_STATUS"] = status.value
            if status in (LicenseStatus.REVOKED, LicenseStatus.EXPIRED_OFFLINE, LicenseStatus.EXPIRED):
                _show_blocked_screen(status)
                os._exit(1)
        except Exception:
            pass  # Silently continue — next cycle will retry


def _run_license_check() -> None:
    """Execute license validation flow. Called before Flask starts."""
    # Add licensing module to path (needed when frozen)
    sys.path.insert(0, str(BUNDLE_DIR))

    from licensing.license_client import LicenseClient, LicenseStatus

    client = LicenseClient()
    status = client.validate()

    if status == LicenseStatus.NOT_ACTIVATED:
        _show_activation_screen(client)
        # Re-validate after activation
        status = client.validate()

    if status in (LicenseStatus.REVOKED, LicenseStatus.EXPIRED_OFFLINE, LicenseStatus.EXPIRED):
        _show_blocked_screen(status)
        sys.exit(1)
    elif status == LicenseStatus.GRACE_PERIOD:
        pass  # Allow to run, UI will show warning

    os.environ["VEO3_LICENSE_STATUS"] = status.value

    # Store client reference for watchdog
    return client


# ── Bootstrap de subprocesso ─────────────────────────────────────────────────
# Quando o binário é relançado como subprocesso (ex: para rodar o bot),
# ele checa o argumento e executa só aquele módulo, sem iniciar o Flask.
if __name__ == "__main__" and "--bot" in sys.argv:
    _check_expiration()
    sys.path.insert(0, str(BUNDLE_DIR))
    import bot_flow
    bot_flow.main()
    sys.exit(0)

if __name__ == "__main__" and "--fatiar" in sys.argv:
    _check_expiration()
    sys.path.insert(0, str(BUNDLE_DIR))
    import fatiador
    roteiro = DATA_DIR / "roteiro.txt"
    takes   = DATA_DIR / "takes.txt"
    fatiador.fatiar_texto(str(roteiro), str(takes))
    sys.exit(0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _setup_data_dir() -> None:
    """Cria estrutura de pastas de dados e copia prompts padrão na 1ª execução."""
    for folder in ("prompts", "img_base", "erros", "videos_gerados"):
        (DATA_DIR / folder).mkdir(parents=True, exist_ok=True)

    # Copia prompts padrão do bundle para DATA_DIR apenas se ainda não existirem
    src = BUNDLE_DIR / "prompts"
    dst = DATA_DIR  / "prompts"
    if src.exists() and not any(dst.glob("*.txt")):
        for f in src.glob("*.txt"):
            shutil.copy(f, dst / f.name)
        print(f"[VEO3] Prompts padrão copiados para {dst}")

    # Copia imagens padrão do bundle (se houver)
    src_img = BUNDLE_DIR / "img_base"
    dst_img = DATA_DIR   / "img_base"
    if src_img.exists():
        for f in src_img.iterdir():
            if f.is_file() and not (dst_img / f.name).exists():
                shutil.copy(f, dst_img / f.name)


def _ensure_playwright() -> None:
    """Instala os browsers do Playwright na primeira execução."""
    try:
        from playwright._impl._driver import compute_driver_executable
        driver = compute_driver_executable()
        # Verifica se o chromium já está instalado checando o cache local
        cache = Path.home() / "Library" / "Caches" / "ms-playwright"
        chromium_ok = any(cache.glob("chromium-*/chrome-mac/Chromium.app")) if cache.exists() else False
        if not chromium_ok:
            print("[VEO3] Instalando Chromium (apenas na primeira execução)...")
            import subprocess
            result = subprocess.run(
                [str(driver), "install", "chromium"],
                capture_output=False,
            )
            if result.returncode == 0:
                print("[VEO3] Chromium instalado com sucesso.")
            else:
                print("[VEO3] Aviso: instalação do Chromium pode ter falhado.")
    except Exception as e:
        print(f"[VEO3] Aviso Playwright: {e}")


def main() -> None:
    _check_expiration()
    sys.path.insert(0, str(BUNDLE_DIR))

    _setup_data_dir()

    # License check (blocks if not activated)
    license_client = _run_license_check()

    _ensure_playwright()

    port = _free_port()

    # Start license watchdog (every 6 hours)
    if license_client:
        threading.Thread(target=_license_watchdog, args=(license_client,), daemon=True).start()

    # Importa e inicia Flask
    import app as flask_app

    def _run_flask():
        flask_app.app.run(
            host="127.0.0.1",
            port=port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )

    t = threading.Thread(target=_run_flask, daemon=True)
    t.start()
    time.sleep(1.5)

    url = f"http://127.0.0.1:{port}"
    print(f"[VEO3] Rodando em {url}")
    print(f"[VEO3] Dados salvos em: {DATA_DIR}")
    webbrowser.open(url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[VEO3] Encerrando.")
        sys.exit(0)


if __name__ == "__main__":
    main()
