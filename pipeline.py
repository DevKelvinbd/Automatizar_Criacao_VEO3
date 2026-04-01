"""
pipeline.py
===========
Orquestra o fluxo de produção de vídeos VEO3 no Google Flow:

  ETAPA 1 — Geração
    └─ Roda bot_flow.py e aguarda a conclusão de todos os takes

Para rodar:
  python pipeline.py

Pré-requisitos:
  - Chrome rodando com --remote-debugging-port=9222
  - Google Flow aberto com a imagem de referência no projeto
"""

import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON   = sys.executable
BOT_FLOW = os.path.join(BASE_DIR, "bot_flow.py")
SEP      = "=" * 60


def rodar_script(script, label, args=None):
    """Executa um script Python e exibe output em tempo real. Retorna exit code."""
    print(f"\n{SEP}")
    print(f"▶ Iniciando: {label}")
    print(SEP)
    cmd = [PYTHON, script] + (args or [])
    resultado = subprocess.run(cmd)
    return resultado.returncode


def main():
    print(f"""
{SEP}
   PIPELINE DE PRODUÇÃO VEO3
{SEP}
  ETAPA 1 → Geração dos vídeos
{SEP}
""")

    # ── ETAPA 1: Geração ──────────────────────────────────────────────────────
    print("[ ETAPA 1 ] Gerando vídeos com bot_flow.py...")
    codigo = rodar_script(BOT_FLOW, "bot_flow.py — Geração dos takes")

    if codigo == 0:
        print(f"""
{SEP}
✅ PIPELINE CONCLUÍDO!
   Todos os takes foram enviados para geração no Google Flow.
{SEP}
""")
    else:
        print(f"""
{SEP}
⚠  bot_flow.py encerrou com código {codigo}.
   Verifique os takes que falharam no Google Flow.
{SEP}
""")


if __name__ == "__main__":
    main()
