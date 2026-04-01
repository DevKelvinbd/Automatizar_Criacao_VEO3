#!/usr/bin/env bash
# ==========================================================
# setup_e_rodar.sh — Configuração e execução da automação
# Uso:
#   bash setup_e_rodar.sh setup   → instala dependências
#   bash setup_e_rodar.sh fatiar  → divide o roteiro em takes
#   bash setup_e_rodar.sh bot     → roda o robô no Google Flow
# ==========================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/venv"
PYTHON="$VENV/bin/python"

case "$1" in

  setup)
    echo "==> Criando ambiente virtual..."
    python3 -m venv "$VENV"
    echo "==> Instalando Playwright..."
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet playwright
    echo "==> Baixando navegador Chromium do Playwright..."
    "$PYTHON" -m playwright install chromium
    echo ""
    echo "✔ Setup concluído! Agora rode:"
    echo "  bash setup_e_rodar.sh fatiar"
    ;;

  fatiar)
    echo "==> Fatiando o roteiro.txt..."
    "$PYTHON" "$SCRIPT_DIR/fatiador.py"
    ;;

  bot)
    echo "==> Iniciando o robô do Google Flow..."
    echo "    (certifique-se de que o Chrome está aberto com --remote-debugging-port=9222)"
    "$PYTHON" "$SCRIPT_DIR/bot_flow.py"
    ;;

  *)
    echo "Uso: bash setup_e_rodar.sh [setup|fatiar|bot]"
    exit 1
    ;;

esac
