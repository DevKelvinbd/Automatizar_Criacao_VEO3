"""
launcher.py
===========
Ponto de entrada do executável distribuído (PyInstaller).

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
from pathlib import Path

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

# ── Bootstrap de subprocesso ─────────────────────────────────────────────────
# Quando o binário é relançado como subprocesso (ex: para rodar o bot),
# ele checa o argumento e executa só aquele módulo, sem iniciar o Flask.
if __name__ == "__main__" and "--bot" in sys.argv:
    sys.path.insert(0, str(BUNDLE_DIR))
    import bot_flow
    bot_flow.main()
    sys.exit(0)

if __name__ == "__main__" and "--fatiar" in sys.argv:
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
    sys.path.insert(0, str(BUNDLE_DIR))

    _setup_data_dir()
    _ensure_playwright()

    port = _free_port()

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
