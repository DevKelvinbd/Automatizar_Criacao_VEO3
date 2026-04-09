"""
app.py
======
Interface web para a automação VEO3.

Para rodar:
  python app.py
  → Abra http://localhost:5000 no navegador
"""

import os
import re
import sys
import json
import queue
import platform
import threading
import subprocess
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

# ── Paths (PyInstaller-aware) ────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    # Binário congelado: recursos em BUNDLE_DIR (read-only), dados em DATA_DIR
    BUNDLE_DIR = Path(sys._MEIPASS)
    _default = (
        str(Path(os.environ.get("APPDATA", Path.home())) / "VEO3")
        if sys.platform == "win32"
        else str(Path.home() / "Library" / "Application Support" / "VEO3")
    )
    DATA_DIR   = Path(os.environ.get("VEO3_DATA_DIR", _default))
    # Subprocessos: reinvoca o próprio binário com flag bootstrap
    BOT_CMD    = [sys.executable, "--bot"]
    FATIAR_CMD = [sys.executable, "--fatiar"]
else:
    BUNDLE_DIR = Path(__file__).parent
    DATA_DIR   = Path(os.environ.get("VEO3_DATA_DIR", str(BUNDLE_DIR)))
    BOT_CMD    = [sys.executable, str(BUNDLE_DIR / "bot_flow.py")]
    FATIAR_CMD = [sys.executable, str(BUNDLE_DIR / "fatiador.py")]

PROMPTS_DIR  = DATA_DIR / "prompts"
ROTEIRO_FILE = DATA_DIR / "roteiro.txt"
TAKES_FILE   = DATA_DIR / "takes.txt"

PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder=str(BUNDLE_DIR / "templates"))

_bot_process: subprocess.Popen | None = None
_log_queue: queue.Queue = queue.Queue()


# ── Helpers ──────────────────────────────────────────────────────────────────

def sanitize_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name.strip())


def parse_prompts_file(filepath: Path) -> list[str]:
    prompts: list[str] = []
    atual: list[str] = []
    dentro = False
    with open(filepath, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.rstrip("\n")
            if linha.startswith("=== PROMPT"):
                if dentro and atual:
                    texto = " ".join(atual).strip()
                    if texto:
                        prompts.append(texto)
                atual = []
                dentro = True
                continue
            if dentro and not linha.startswith("#"):
                if linha.strip():
                    atual.append(linha.strip())
    if dentro and atual:
        texto = " ".join(atual).strip()
        if texto:
            prompts.append(texto)
    return prompts


def write_prompts_file(filepath: Path, prompts: list[str]) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("# ============================================================\n")
        f.write(f"# ARQUIVO DE PROMPTS — {filepath.name}\n")
        f.write("# ============================================================\n")
        f.write("# Use {take} onde o texto do roteiro deve ser inserido.\n")
        f.write("# O bot rotaciona: Take1->P1, Take2->P2, Take3->P3, Take4->P1...\n")
        f.write("# ============================================================\n\n")
        for i, prompt in enumerate(prompts, 1):
            f.write(f"=== PROMPT {i:02d} ===\n")
            f.write(prompt.strip() + "\n\n")


def find_chrome() -> str | None:
    system = platform.system()
    candidates: dict[str, list[str]] = {
        "Darwin": [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ],
        "Windows": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "Linux": [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ],
    }
    for path in candidates.get(system, []):
        if os.path.exists(path):
            return path
    return None


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/avatars", methods=["GET"])
def list_avatars():
    names = sorted(p.stem for p in PROMPTS_DIR.glob("*.txt"))
    return jsonify(names)


@app.route("/api/avatars/<name>", methods=["GET"])
def get_avatar(name: str):
    safe = sanitize_name(name)
    filepath = PROMPTS_DIR / f"{safe}.txt"
    if not filepath.exists():
        return jsonify({"error": "Formato não encontrado"}), 404
    prompts = parse_prompts_file(filepath)
    while len(prompts) < 3:
        prompts.append("")
    return jsonify({"name": safe, "prompts": prompts[:3]})


@app.route("/api/avatars", methods=["POST"])
def create_avatar():
    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    prompts = data.get("prompts", [])
    if not name:
        return jsonify({"error": "Nome obrigatório"}), 400
    if len(prompts) != 3:
        return jsonify({"error": "Exatamente 3 prompts são obrigatórios"}), 400
    safe = sanitize_name(name)
    if not safe:
        return jsonify({"error": "Nome inválido"}), 400
    filepath = PROMPTS_DIR / f"{safe}.txt"
    if filepath.exists():
        return jsonify({"error": "Formato já existe com esse nome"}), 409
    write_prompts_file(filepath, prompts)
    return jsonify({"name": safe}), 201


@app.route("/api/avatars/<name>", methods=["PUT"])
def update_avatar(name: str):
    safe = sanitize_name(name)
    data = request.get_json(force=True) or {}
    prompts = data.get("prompts", [])
    if len(prompts) != 3:
        return jsonify({"error": "Exatamente 3 prompts são obrigatórios"}), 400
    filepath = PROMPTS_DIR / f"{safe}.txt"
    write_prompts_file(filepath, prompts)
    return jsonify({"ok": True})


@app.route("/api/avatars/<name>", methods=["DELETE"])
def delete_avatar(name: str):
    safe = sanitize_name(name)
    filepath = PROMPTS_DIR / f"{safe}.txt"
    if not filepath.exists():
        return jsonify({"error": "Formato não encontrado"}), 404
    filepath.unlink()
    return jsonify({"ok": True})


@app.route("/api/roteiro", methods=["GET"])
def get_roteiro():
    if not ROTEIRO_FILE.exists():
        return jsonify({"text": ""})
    return jsonify({"text": ROTEIRO_FILE.read_text(encoding="utf-8")})


@app.route("/api/roteiro", methods=["POST"])
def save_roteiro():
    data = request.get_json(force=True) or {}
    text = data.get("text", "")
    ROTEIRO_FILE.write_text(text, encoding="utf-8")
    return jsonify({"ok": True})


@app.route("/api/fatiar", methods=["POST"])
def fatiar():
    result = subprocess.run(
        FATIAR_CMD,
        capture_output=True,
        text=True,
    )
    takes: list[str] = []
    if TAKES_FILE.exists():
        takes = [line.strip() for line in TAKES_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    return jsonify({
        "ok":     result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "takes":  takes,
        "count":  len(takes),
    })


@app.route("/api/takes", methods=["GET"])
def get_takes():
    if not TAKES_FILE.exists():
        return jsonify({"takes": [], "count": 0})
    takes = [line.strip() for line in TAKES_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    return jsonify({"takes": takes, "count": len(takes)})


@app.route("/api/setup/chrome", methods=["POST"])
def open_chrome():
    data = request.get_json(force=True) or {}
    try:
        port = int(data.get("port", 9222))
        if not (1024 <= port <= 65535):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Porta inválida (use 1024–65535)"}), 400
    chrome = find_chrome()
    if not chrome:
        return jsonify({"error": "Chrome não encontrado. Instale o Google Chrome."}), 404
    profile_dir = DATA_DIR / ".chrome_profile_veo3"
    cmd = [
        chrome,
        f"--remote-debugging-port={port}",
        "--no-first-run",
        f"--user-data-dir={profile_dir}",
        "https://labs.google.com/flow/create",
    ]
    subprocess.Popen(cmd)
    return jsonify({"ok": True, "port": port})


@app.route("/api/run", methods=["POST"])
def run_bot():
    global _bot_process
    if _bot_process and _bot_process.poll() is None:
        return jsonify({"error": "Bot já está rodando"}), 409
    data = request.get_json(force=True) or {}
    avatar = sanitize_name(data.get("avatar", "avatar_de_frente"))
    try:
        start_take = max(1, int(data.get("start_take", 1)))
    except (TypeError, ValueError):
        start_take = 1
    while not _log_queue.empty():
        try:
            _log_queue.get_nowait()
        except queue.Empty:
            break
    env = os.environ.copy()
    env["VEO3_PROMPTS_FILE"] = f"{avatar}.txt"
    env["VEO3_START_TAKE"] = str(start_take)
    _bot_process = subprocess.Popen(
        BOT_CMD,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    def _reader():
        assert _bot_process and _bot_process.stdout
        for line in _bot_process.stdout:
            _log_queue.put(line)
        _bot_process.wait()
        _log_queue.put(f"[PROCESSO ENCERRADO com código {_bot_process.returncode}]\n")
    threading.Thread(target=_reader, daemon=True).start()
    return jsonify({"ok": True, "pid": _bot_process.pid})


@app.route("/api/stop", methods=["POST"])
def stop_bot():
    global _bot_process
    if _bot_process and _bot_process.poll() is None:
        _bot_process.terminate()
        return jsonify({"ok": True})
    return jsonify({"error": "Nenhum processo rodando"}), 404


@app.route("/api/logs")
def stream_logs():
    def generate():
        while True:
            try:
                line = _log_queue.get(timeout=30)
                yield f"data: {json.dumps(line)}\n\n"
            except queue.Empty:
                yield ": heartbeat\n\n"
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/status", methods=["GET"])
def status():
    running = _bot_process is not None and _bot_process.poll() is None
    return jsonify({"running": running})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
