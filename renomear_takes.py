"""
renomear_takes.py
=================
Renomeia os vídeos gerados no Google Flow como TK01, TK02, TK03 ...

Estratégia (vista em LOTE, de baixo para cima):
  1. Clica em 'Ver vídeos'
  2. Abre configurações (engrenagem) e seleciona modo 'Lote'
  3. Lê todos os cards de vídeo — o mais recente (topo) = TKlast, o mais antigo (fundo) = TK01
  4. Itera do último para o primeiro (reversed), renomeando cada um
  5. Usa scrollIntoView 'nearest' para não arrastar a tela inteira

Pré-requisito:
  - Chrome rodando com --remote-debugging-port=9222
  - Google Flow aberto com os vídeos gerados e concluídos
"""

import time
import os
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ============================================================
# CONFIGURAÇÕES
# ============================================================
START_INDEX = 1      # número do primeiro TK (1 → TK01)
PREFIX      = "TK"   # prefixo do nome
CDP_PORT    = 9222   # porta do Chrome debug
ERROS_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erros")


# ─────────────────────────────────────────────────────────────
def screenshot_erro(page, nome):
    os.makedirs(ERROS_DIR, exist_ok=True)
    path = os.path.join(ERROS_DIR, nome)
    page.screenshot(path=path)
    print(f"   📸 Screenshot: {path}")


def mudar_para_lote(page):
    """Abre configurações da grade (engrenagem) e seleciona modo 'Lote'."""
    # 1. Clicar na engrenagem
    engrenagem_sels = [
        "button:has-text('settings_2')",
        "button:has-text('Ver configurações da grade de blocos')",
        "button[aria-label*='configuração' i]",
        "button[aria-label*='setting' i]",
    ]
    abriu = False
    for sel in engrenagem_sels:
        try:
            btn = page.locator(sel).first
            if btn.is_visible():
                btn.click()
                time.sleep(0.7)
                abriu = True
                print("   ⚙ Painel de configurações aberto.")
                break
        except Exception:
            continue
    if not abriu:
        print("   ⚠ Engrenagem não encontrada — tentando 'Lote' diretamente...")

    # 2. Clicar em 'Lote'
    lote_sels = [
        "button[aria-label='Lote']",
        "button:has-text('Lote')",
        "button[role='tab']:has-text('Lote')",
        "[aria-label*='Lote' i]",
    ]
    for sel in lote_sels:
        try:
            btn = page.locator(sel).first
            if btn.is_visible():
                btn.click()
                time.sleep(0.5)
                print("   ✔ Modo 'Lote' selecionado.")
                page.keyboard.press("Escape")
                time.sleep(0.5)
                return True
        except Exception:
            continue
    print("   ⚠ Botão 'Lote' não encontrado — continuando com a vista atual.")
    page.keyboard.press("Escape")
    return False


def ler_nome_do_item(item):
    """Lê o nome atual do card diretamente do DOM (sem abrir menus)."""
    try:
        texto = item.evaluate("el => el.innerText || ''")
        match = re.search(r'\b(TK\d+)\b', texto)
        if match:
            return match.group(1)
        linhas = [l.strip() for l in texto.split('\n') if l.strip()]
        return linhas[0] if linhas else ""
    except Exception:
        return ""


def card_tem_erro(item):
    """Verifica se o card apresenta indicador de falha."""
    try:
        texto = item.evaluate("el => el.innerText || ''")
        keywords = ["Falha", "falha", "Error", "error", "políticas", "policy"]
        if any(kw in texto for kw in keywords):
            return True
        tem_retry = item.evaluate("""el => {
            const btns = el.querySelectorAll('button');
            for (const b of btns) {
                const lbl = b.getAttribute('aria-label') || '';
                if (/tentar|retry|retentar/i.test(lbl)) return true;
            }
            return false;
        }""")
        return tem_retry
    except Exception:
        return False


def renomear_card(page, item, novo_nome):
    """Renomeia um card via right-click → Renomear → digita nome → Enter."""
    # Fechar qualquer menu aberto
    try:
        page.keyboard.press("Escape")
        time.sleep(0.2)
    except Exception:
        pass

    # Right-click no card
    item.click(button="right", force=True)
    time.sleep(0.7)

    # Clicar em 'Renomear'
    try:
        renomear_btn = page.locator("button[role='menuitem']:has-text('Renomear')").first
        renomear_btn.wait_for(state="visible", timeout=4000)
        renomear_btn.click()
        time.sleep(0.6)
    except PlaywrightTimeoutError:
        screenshot_erro(page, f"erro_menu_{novo_nome}.png")
        raise RuntimeError(f"'Renomear' não apareceu no menu para {novo_nome}")

    # Localizar input de renomeação (Y > 60px — ignora cabeçalho)
    campo = None
    for loc in page.locator("input[aria-label='Texto editável']").all():
        try:
            if not loc.is_visible():
                continue
            bbox = loc.bounding_box()
            if bbox and bbox["y"] > 60:
                campo = loc
                break
        except Exception:
            continue

    # Fallback: input type=text visível com valor
    if campo is None:
        for loc in page.locator("input[type='text']").all():
            try:
                if not loc.is_visible():
                    continue
                bbox = loc.bounding_box()
                if bbox and bbox["y"] > 60:
                    val = loc.input_value()
                    if val and val != "O que você quer criar?":
                        campo = loc
                        break
            except Exception:
                continue

    if campo is None:
        screenshot_erro(page, f"erro_input_{novo_nome}.png")
        raise RuntimeError(f"Input de renomeação não encontrado para {novo_nome}")

    # Limpar e digitar novo nome
    campo.click()
    page.keyboard.press("Control+a")
    time.sleep(0.1)
    campo.fill(novo_nome)
    time.sleep(0.3)
    page.keyboard.press("Enter")
    time.sleep(0.8)
    print(f"   ✅ Renomeado para '{novo_nome}'.")


def carregar_takes():
    takes_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "takes.txt")
    if not os.path.exists(takes_path):
        return []
    with open(takes_path, "r", encoding="utf-8") as f:
        return [linha.strip() for linha in f if linha.strip()]


def salvar_relatorio(erros):
    if not erros:
        return
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relatorio_erros.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("=== RELATÓRIO DE TAKES COM ERRO ===\n")
        f.write(f"Gerado em: {time.strftime('%d/%m/%Y %H:%M:%S')}\n")
        f.write("=" * 50 + "\n\n")
        for item in erros:
            f.write(f"  {item['tk']}  (posição {item['pos']:02d})\n")
            f.write(f"  Frase: {item['frase']}\n")
            f.write(f"  Motivo: {item['motivo']}\n\n")
    print(f"\n📄 Relatório salvo em: {path}")


# ─────────────────────────────────────────────────────────────
def main():
    os.makedirs(ERROS_DIR, exist_ok=True)
    takes = carregar_takes()
    total_takes = len(takes)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        except Exception as e:
            print(f"❌ Não conectou ao Chrome ({CDP_PORT}): {e}")
            return

        context = browser.contexts[0]

        # Seleciona aba do Google Flow
        page = None
        for pg in context.pages:
            if any(d in pg.url for d in ["flow.google", "labs.google", "ai.google"]):
                page = pg
                break
        if page is None:
            page = context.pages[-1]

        print(f"Conectado! Página: '{page.title()}'")

        # ── 1. Ir para 'Ver vídeos' ─────────────────────────────────────────────
        print("\n📽 Navegando para aba 'Ver vídeos'...")
        for sel in ["button:has-text('Ver vídeos')", "button[aria-label*='vídeo' i]"]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible():
                    btn.click()
                    time.sleep(1.5)
                    print(f"   ✔ Aba selecionada.")
                    break
            except Exception:
                continue

        # ── 2. Mudar para modo Lote ─────────────────────────────────────────────
        print("\n🔀 Ativando modo 'Lote'...")
        mudar_para_lote(page)
        time.sleep(1.0)

        # ── 3. Mapear todos os cards ────────────────────────────────────────────
        SELETORES_ITEM = [
            "div[role='button']:has(video)",
            "tr:has(video)",
            "li:has(video)",
            "[role='row']:has(video)",
        ]

        # Localizar o container scrollável dos vídeos
        CONTAINER_SELS = [
            "div[class*='dHWSIe']",      # classe observada no DOM
            "div[class*='dQzxjo']",
            "div[class*='media-gallery']",
            "section:has(video)",
            "div:has(> div[role='button']:has(video))",  # pai direto dos cards
        ]

        # Pré-scroll: rola o painel de CIMA para BAIXO em passos de 300px
        # para forçar o lazy loading de todos os cards antes do scan
        print("\n🔄 Pré-scroll: carregando todos os vídeos do painel...")
        container = None
        for csel in CONTAINER_SELS:
            try:
                el = page.locator(csel).first
                if el.is_visible():
                    container = el
                    break
            except Exception:
                continue

        # Scroll do container (ou da janela se não achar) do topo ao fundo
        scroll_js = """
            (container) => {
                const el = container || document.querySelector('div[role="button"]:has(video)')?.closest('[style*="overflow"]') || document.scrollingElement;
                if (!el) return;
                el.scrollTop = 0;
            }
        """
        try:
            page.evaluate(scroll_js, container.element_handle() if container else None)
            time.sleep(0.5)
        except Exception:
            pass

        # Scroll passo a passo para baixo
        for _ in range(20):  # até 20 passos de 300px = 6000px
            try:
                page.evaluate("""
                    () => {
                        const candidates = Array.from(document.querySelectorAll('*')).filter(
                            el => el.scrollHeight > el.clientHeight + 10 &&
                                  getComputedStyle(el).overflow !== 'visible' &&
                                  el.querySelectorAll('video').length > 0
                        );
                        const el = candidates[0];
                        if (el) el.scrollTop += 300;
                    }
                """)
                time.sleep(0.3)
                # Para quando não há mais itens novos (verifica contagem)
                nova_contagem = len(page.locator("div[role='button']:has(video)").all())
                if nova_contagem >= total_takes:
                    break
            except Exception:
                break

        # Volta para o topo antes de fazer o scan final
        try:
            page.evaluate("""
                () => {
                    const candidates = Array.from(document.querySelectorAll('*')).filter(
                        el => el.scrollHeight > el.clientHeight + 10 &&
                              getComputedStyle(el).overflow !== 'visible' &&
                              el.querySelectorAll('video').length > 0
                    );
                    const el = candidates[0];
                    if (el) el.scrollTop = 0;
                }
            """)
            time.sleep(0.5)
        except Exception:
            pass

        # Scan final
        itens = []
        for sel in SELETORES_ITEM:
            candidatos = page.locator(sel).all()
            if candidatos:
                itens = candidatos
                print(f"   🎬 {len(itens)} vídeo(s) encontrado(s) via: {sel}")
                break

        if not itens:
            print("❌ Nenhum vídeo encontrado. Verifique se os vídeos terminaram de gerar.")
            return

        # ── 4. Renomear de baixo para cima ──────────────────────────────────────
        # Mais recente = topo (index 0). Mais antigo = fundo (index -1) = TK01.
        # reversed(itens) → começa do mais antigo
        itens_para_renomear = list(reversed(itens))
        total_itens = len(itens_para_renomear)

        if total_itens < total_takes:
            print(f"⚠ {total_takes} takes no roteiro mas só {total_itens} vídeos visíveis.")
            print("   Renomeando apenas os vídeos disponíveis.")

        print(f"\n=== Renomeando {min(total_itens, total_takes)} takes (de baixo para cima) ===\n")

        sucesso   = 0
        erros_log = []

        for i, item in enumerate(itens_para_renomear):
            if i >= total_takes:
                break

            tk_idx    = START_INDEX + i
            novo_nome = f"{PREFIX}{tk_idx:02d}"
            frase_idx = i
            frase     = takes[frase_idx] if frase_idx < len(takes) else "(frase não encontrada)"

            # Scroll suave só dentro do container (block='nearest' não arrasta a tela)
            try:
                handle = item.element_handle()
                if handle:
                    page.evaluate(
                        "el => el.scrollIntoView({block: 'nearest', behavior: 'instant'})",
                        handle
                    )
                    time.sleep(0.3)
            except Exception:
                pass

            # Verificar se já tem nome TK
            nome_atual = ler_nome_do_item(item)
            if re.match(r"^TK\d+$", nome_atual.strip()):
                print(f"[{tk_idx:02d}] ⏭ Já tem nome '{nome_atual}' — pulando.")
                sucesso += 1
                continue

            # Verificar erro de geração
            if card_tem_erro(item):
                print(f"[{tk_idx:02d}] ⚠ {novo_nome} — ERRO detectado (slot reservado)")
                trecho = str(frase)[:80] + ("..." if len(str(frase)) > 80 else "")
                print(f"       Frase: \"{trecho}\"")
                erros_log.append({"tk": novo_nome, "pos": tk_idx, "frase": frase,
                                  "motivo": "Vídeo com falha de geração"})
                continue

            # Renomear
            print(f"[{tk_idx:02d}] → {novo_nome}")
            try:
                renomear_card(page, item, novo_nome)
                sucesso += 1
                time.sleep(1.0)  # aguarda DOM estabilizar antes do próximo
            except RuntimeError as e:
                print(f"   ⚠ ERRO: {e}")
                erros_log.append({"tk": novo_nome, "pos": tk_idx, "frase": frase,
                                  "motivo": f"Falha técnica: {e}"})
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass

        # ── Resumo ─────────────────────────────────────────────────────────────
        print(f"\n{'='*50}")
        print(f"=== Renomeação finalizada! ===")
        print(f"   ✅ Renomeados : {sucesso}")
        print(f"   ❌ Com erro   : {len(erros_log)}")

        if erros_log:
            print(f"\n⚠ Takes com erro (precisam ser regerados):")
            for item in erros_log:
                trecho = str(item['frase'])[:70] + ("..." if len(str(item['frase'])) > 70 else "")
                print(f"   {item['tk']} — \"{trecho}\"")
            salvar_relatorio(erros_log)


if __name__ == "__main__":
    main()
