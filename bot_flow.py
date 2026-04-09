import os
import time
import glob
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ============================================================
# CONFIGURAÇÃO — AJUSTE AQUI QUANDO NECESSÁRIO
# ============================================================

# Número do primeiro take no takes.txt atual (ex: 5 se os takes 1-4 já foram feitos)
# Pode ser sobrescrito via variável de ambiente VEO3_START_TAKE (definida pela interface web)
START_TAKE_NUMBER = int(os.environ.get("VEO3_START_TAKE", 1))

# ⭐ ARQUIVO DE PROMPTS — altere aqui para trocar o conjunto de prompts
PROMPTS_FILE = os.environ.get("VEO3_PROMPTS_FILE", "avatar_de_frente.txt")

# Diretório de dados (gravável) — usa VEO3_DATA_DIR se definido (modo frozen)
_DATA_DIR    = os.environ.get("VEO3_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))

# Pasta com a imagem de referência
IMG_BASE_DIR = os.path.join(_DATA_DIR, "img_base")

# Pausa entre takes (segundos)
PAUSA_ENTRE_TAKES = 3

# ============================================================
# SELETORES — CALIBRE AQUI SE O FLOW ATUALIZAR O LAYOUT
# Dica: Mande um print de tela para o Antigravity ajustar.
# ============================================================

# Campo de prompt (contenteditable div — NÃO um textarea)
TEXTAREA_SELECTOR = "div[role='textbox']"

# Botão de envio (seta →, texto "Criar")
GENERATE_SELECTORS = [
    "button:has-text('Criar')",
    "button:has-text('arrow_forward')",
    "button[aria-label*='Generate']",
    "button[aria-label*='Create']",
    "button:has-text('Generate')",
    "button:has-text('Create')",
    "button:has-text('Gerar')",
]

# ============================================================
# PROMPTS ROTATIVOS — carregados do arquivo selecionado
# ============================================================
# Os prompts são lidos de prompts/PROMPTS_FILE ao iniciar.
# Para trocar, edite PROMPTS_FILE no topo deste arquivo.
PROMPTS = []  # preenchido por carregar_prompts() no main()
_PLACEHOLDER = [
    # PROMPT 01 — mãos simétricas
    (
        "A hyper-realistic human avatar speaking directly to the camera in a continuous shot. "
        "The avatar maintains absolute visual consistency across all frames, with no changes in identity, "
        "facial structure, skin texture, lighting, color grading, sharpness, or contrast. The character must "
        "remain identical throughout the video and across multiple generations. Prevent any accumulation of "
        "saturation, contrast, or color shifts between clips. "
        "The camera is completely static: no zoom, no pan, no tilt, no shake, no reframing. Fixed focal length and framing. "
        "The avatar keeps constant eye contact with the camera at all times, never looking away. Head position "
        "remains stable with only minimal natural micro-movements. "
        "Facial expressions are subtle, controlled, and neutral, with very slight natural variation. "
        "The avatar is actively speaking the following exact script (8 seconds duration): {take} "
        "Lip movement must be perfectly synchronized, highly precise and clearly visible. "
        "Hand movement pattern: both hands positioned near the center of the torso, performing small, symmetrical, "
        "slow opening and closing gestures, moving slightly forward and back in a calm, repetitive rhythm. Hands never leave the frame. "
        "Motion is smooth, calm, symmetrical, and temporally coherent, with no jitter, flicker, deformation, or visual drift. "
        "Lighting remains perfectly constant: no flickering, no shifting shadows, no exposure or saturation changes. "
        "Background remains completely unchanged and stable. "
        "The animation must start and end in the exact same neutral pose and color state, enabling seamless continuation "
        "using the last frame as reference. No visual drift, no morphing, no style shift, no identity change, no cumulative color degradation."
    ),
    # PROMPT 02 — mão direita explicativa
    (
        "A hyper-realistic human avatar speaking directly to the camera in a continuous shot. "
        "The avatar maintains absolute visual consistency across all frames, with no changes in identity, "
        "facial structure, skin texture, lighting, color grading, sharpness, or contrast. Prevent any increase "
        "in saturation or image degradation across generations. "
        "The camera is completely static. "
        "The avatar maintains constant eye contact, with minimal head movement. "
        "Facial expressions remain subtle and neutral. "
        "The avatar is actively speaking the following exact script (8 seconds duration): {take} "
        "Lip movement must be perfectly synchronized and highly precise. "
        "Hand movement pattern: one dominant hand (right hand) performs gentle explanatory gestures, moving slowly "
        "from chest level outward and back, while the other hand remains mostly still. Movements are smooth, minimal, and repeatable. "
        "Motion is stable, fluid, and consistent with no jitter or flicker. "
        "Lighting and color must remain perfectly unchanged, with no variation in brightness, contrast, or saturation. "
        "Background remains fixed and identical. "
        "The animation must start and end in the same neutral pose and visual state for seamless chaining. "
        "No visual drift, no morphing, no color shift, no quality degradation between clips."
    ),
    # PROMPT 03 — mãos alternadas conversacional
    (
        "A hyper-realistic human avatar speaking directly to the camera in a continuous shot. "
        "The avatar must remain visually identical across all frames and future generations, with zero changes in "
        "identity, lighting, skin tone, sharpness, contrast, or saturation. Prevent cumulative image degradation or color amplification. "
        "The camera is completely fixed. "
        "The avatar maintains constant eye contact and stable posture. "
        "Facial expressions are minimal and controlled. "
        "The avatar is actively speaking the following exact script (8 seconds duration): {take} "
        "Lip sync must be perfectly accurate and clearly visible. "
        "Hand movement pattern: both hands alternate in subtle movements, one hand slightly lifting while the other relaxes, "
        "creating a slow, natural conversational rhythm. Movements are small, controlled, and loopable. "
        "Motion must be smooth, symmetrical over time, and free of jitter, flicker, or deformation. "
        "Lighting must remain perfectly constant, with no shifts in exposure, shadows, or color. "
        "Background remains unchanged and stable. "
        "The animation must begin and end in the exact same neutral pose and identical visual state, enabling perfect "
        "continuation from the last frame. No visual drift, no morphing, no style inconsistency, no saturation increase, no loss of quality."
    ),
]


# ============================================================
# HELPERS
# ============================================================

def carregar_prompts(nome_arquivo=None):
    if nome_arquivo is None:
        nome_arquivo = PROMPTS_FILE
    pasta   = os.path.join(_DATA_DIR, "prompts")
    caminho = os.path.join(pasta, nome_arquivo)

    if not os.path.exists(caminho):
        print(f"⚠ Arquivo de prompts '{caminho}' não encontrado — usando prompts embutidos.")
        return None  # fallback para lista hardcoded abaixo

    prompts    = []
    atual      = []
    dentro     = False

    with open(caminho, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.rstrip("\n")
            if linha.startswith("=== PROMPT"):
                if dentro and atual:
                    texto = " ".join(atual).strip()
                    if texto:
                        prompts.append(texto)
                atual  = []
                dentro = True
                continue
            if dentro and not linha.startswith("#"):
                if linha.strip():
                    atual.append(linha.strip())

    if dentro and atual:
        texto = " ".join(atual).strip()
        if texto:
            prompts.append(texto)

    if not prompts:
        print(f"⚠ Nenhum prompt lido de '{nome_arquivo}' — usando prompts embutidos.")
        return None

    print(f"✅ {len(prompts)} prompt(s) carregado(s) de: prompts/{nome_arquivo}")
    return prompts


def setup_paths():
    takes_file = os.path.join(_DATA_DIR, "takes.txt")
    erros_dir  = os.path.join(_DATA_DIR, "erros")
    videos_dir = os.path.join(_DATA_DIR, "videos_gerados")
    os.makedirs(erros_dir,  exist_ok=True)
    os.makedirs(videos_dir, exist_ok=True)
    return takes_file, erros_dir, videos_dir


def get_imagem_referencia():
    """Retorna o caminho da primeira imagem encontrada em img_base/."""
    for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
        matches = glob.glob(os.path.join(IMG_BASE_DIR, ext))
        if matches:
            return matches[0]
    return None


def screenshot_erro(page, erros_dir, nome):
    try:
        path = os.path.join(erros_dir, nome)
        page.screenshot(path=path)
        print(f"   📸 Screenshot: {path}")
    except Exception:
        pass


def clicar_primeiro_visivel(page, seletores, descricao="botão", timeout_ms=15000):
    """Tenta cada seletor e clica no primeiro visível. Usa force=True se overlay interceptar."""
    for sel in seletores:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout_ms)
            try:
                loc.click(timeout=5000)
            except Exception:
                loc.click(force=True, timeout=5000)
            print(f"   ✔ Clicou em '{descricao}' via: {sel}")
            return True
        except PlaywrightTimeoutError:
            continue
    return False


def inserir_imagem_slot_inicial(page, img_nome, erros_dir):
    """
    Insere a imagem de referência no slot 'Inicial' do Google Flow.

    Fluxo:
    1. Limpar slot se preenchido
    2. Localizar thumbnail no painel esquerdo
    3. Disparar contextmenu via JavaScript (contorna overlay de pointer events)
    4. Clicar em 'Incluir no comando'
    5. Clicar em 'Concluir' (se aparecer)

    Lança RuntimeError se falhar.
    """

    # 1. Limpar slot Inicial se já estiver preenchido
    try:
        apagar = page.locator("button:has-text('Apagar comando')").first
        if apagar.is_visible():
            apagar.click()
            time.sleep(0.5)
            print("   🗑 Slot Inicial limpo.")
    except Exception:
        pass

    # 2. Navegar para aba 'Ver imagens' no painel esquerdo
    #    OBRIGATÓRIO: sem isso o bot pega thumbnails de vídeos gerados
    try:
        ver_img = page.locator("button:has-text('Ver imagens')").first
        ver_img.wait_for(state="visible", timeout=5000)
        ver_img.click()
        time.sleep(0.8)
        print("   🖼 Aba 'Ver imagens' selecionada.")
    except Exception as e:
        print(f"   ⚠ Não encontrou 'Ver imagens' — continuando ({e})")

    # 3. Localizar thumbnail da imagem de referência (agora só imagens estão visíveis)
    #    Na aba 'Ver imagens' só a Prancheta está — o primeiro 'div[role=button]:has(img)' é ela
    thumb_sels = [
        f"div[role='button']:has-text('{img_nome}')",
        f"[aria-label*='{img_nome}']",
        f"[title*='{img_nome}']",
        "div[role='button']:has(img)",  # fallback confiável quando na aba de imagens
    ]
    thumbnail = None
    for sel in thumb_sels:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                thumbnail = loc
                print(f"   🖼 Thumbnail encontrada via: {sel}")
                break
        except Exception:
            continue

    if thumbnail is None:
        screenshot_erro(page, erros_dir, "erro_thumbnail.png")
        raise RuntimeError(
            f"🚨 Thumbnail '{img_nome}' não encontrada no painel esquerdo.\n"
            "Certifique-se de que a imagem está no projeto do Google Flow."
        )

    # 3. Disparar contextmenu via JavaScript (contorna overlay pointer events)
    print("   ⚙ Abrindo menu de contexto via JavaScript...")
    try:
        page.evaluate("""
            el => {
                const rect = el.getBoundingClientRect();
                const cx = rect.left + rect.width / 2;
                const cy = rect.top + rect.height / 2;
                const evt = new MouseEvent('contextmenu', {
                    bubbles: true, cancelable: true,
                    view: window,
                    clientX: cx, clientY: cy,
                    button: 2, buttons: 2
                });
                el.dispatchEvent(evt);
            }
        """, thumbnail.element_handle())
        time.sleep(0.8)
    except Exception:
        pass

    # Verificar se menu abriu; fallback: force=True
    try:
        page.locator("button[role='menuitem']:has-text('Incluir no comando')").first.wait_for(
            state="visible", timeout=2000
        )
        print("   📋 Menu de contexto aberto.")
    except Exception:
        print("   ⚠ JS contextmenu não abriu menu — tentando force=True...")
        try:
            thumbnail.click(button="right", force=True)
            time.sleep(0.8)
            page.locator("button[role='menuitem']:has-text('Incluir no comando')").first.wait_for(
                state="visible", timeout=3000
            )
            print("   📋 Menu aberto via force=True.")
        except Exception as e:
            screenshot_erro(page, erros_dir, "erro_menu_contexto.png")
            raise RuntimeError(f"🚨 Não foi possível abrir o menu de contexto: {e}")

    # 4. Clicar em 'Incluir no comando'
    incluir = page.locator("button[role='menuitem']:has-text('Incluir no comando')").first
    try:
        incluir.wait_for(state="visible", timeout=5000)
        incluir.click()
        print("   ✔ Clicou em 'Incluir no comando'.")
        time.sleep(1.0)
    except Exception as e:
        screenshot_erro(page, erros_dir, "erro_incluir_comando.png")
        raise RuntimeError(f"🚨 'Incluir no comando' não encontrado no menu: {e}")

    # 5. Clicar em 'Concluir' na tela de preview (se aparecer)
    concluir = page.locator("button:has-text('Concluir')").first
    try:
        concluir.wait_for(state="visible", timeout=5000)
        concluir.click()
        print("   ✅ Imagem adicionada ao slot Inicial.")
        time.sleep(0.8)
    except Exception:
        page.keyboard.press("Escape")
        print("   ⚠ 'Concluir' não encontrado — fechado com Escape.")






def processar_take(page, index, take, erros_dir, img_nome):
    numero_take = START_TAKE_NUMBER + index
    prompt_final = PROMPTS[index % 3].format(take=take)

    print(f"\n{'='*60}")
    print(f"[Take {numero_take}] '{take[:60]}...'")
    print(f"   Prompt rotativo #{index % 3 + 1}")

    # 1. INSERIR IMAGEM NO SLOT INICIAL (obrigatório — sem imagem não gera)
    print("   📷 Inserindo imagem no slot Inicial...")
    inserir_imagem_slot_inicial(page, img_nome, erros_dir)
    # Se falhar, lança RuntimeError e o take é pulado com screenshot

    # 2. Preencher o campo de prompt
    page.wait_for_selector(TEXTAREA_SELECTOR, state="visible", timeout=15000)
    campo = page.locator(TEXTAREA_SELECTOR).first
    campo.click()
    time.sleep(0.3)
    page.keyboard.press("Meta+A")
    page.keyboard.press("Backspace")
    time.sleep(0.3)
    page.keyboard.type(prompt_final, delay=5)
    print("   ✔ Prompt inserido.")

    # 3. Clicar em Criar (→)
    gerou = clicar_primeiro_visivel(page, GENERATE_SELECTORS, descricao="Criar")
    if not gerou:
        raise RuntimeError("🚨 Nenhum botão de geração encontrado. Calibre os seletores.")

    print(f"   🚀 Take {numero_take} enviado para geração!")


# ============================================================
# MAIN
# ============================================================

def main():
    global PROMPTS

    # ── Carregar prompts do arquivo selecionado ──────────────────────────────
    prompts_carregados = carregar_prompts(PROMPTS_FILE)
    if prompts_carregados:
        PROMPTS = prompts_carregados
    else:
        PROMPTS = _PLACEHOLDER  # fallback: prompts embutidos

    takes_file, erros_dir, videos_dir = setup_paths()

    if not os.path.exists(takes_file):
        print(f"Erro: '{takes_file}' não encontrado. Execute o fatiador.py primeiro.")
        return

    with open(takes_file, "r", encoding="utf-8") as f:
        takes = [l.strip() for l in f if l.strip()]

    if not takes:
        print("Nenhum take encontrado em takes.txt.")
        return

    # Nome da imagem de referência (deve estar no painel esquerdo do Google Flow)
    img_path = get_imagem_referencia()
    img_nome = os.path.basename(img_path) if img_path else None
    if img_nome:
        print(f"📷 Imagem de referência: {img_nome}")
    else:
        print(f"⚠ Nenhuma imagem em img_base/ — usando fallback: 'Prancheta 1.png'")
        img_nome = "Prancheta 1.png"  # Nome padrão quando img_base está vazia

    print(f"=== Bot Flow — {len(takes)} takes a partir do Take {START_TAKE_NUMBER} ===")
    print(f"⚙ Prompts: {PROMPTS_FILE} ({len(PROMPTS)} prompts rotativos)")
    print(f"⚙ Configurações: VEO 3 | Vídeo | 9:16 | 1x (verifique no Flow)")

    with sync_playwright() as p:
        browser = None
        try:
            print("\nConectando ao Chrome via CDP (porta 9222)...")
            browser = p.chromium.connect_over_cdp("http://localhost:9222")

            context = browser.contexts[0]
            if not context.pages:
                print("Nenhuma aba aberta. Abra o Google Flow antes de rodar o bot.")
                return

            # Busca a aba do Google Flow pela URL — prioriza a aba do PROJETO
            # (URLs com /project/ ou /tools/flow/) sobre a página inicial/about
            page = None

            # 1ª prioridade: aba do projeto (tem "project" na URL)
            for p_candidate in context.pages:
                url = p_candidate.url
                if ("labs.google" in url or "flow.google" in url) and "project" in url:
                    page = p_candidate
                    print(f"   🎯 Aba do projeto encontrada: {url[:80]}...")
                    break

            # 2ª prioridade: qualquer aba do Flow/labs (exceto about)
            if page is None:
                for p_candidate in context.pages:
                    url = p_candidate.url
                    if ("flow.google" in url or "labs.google" in url or "ai.google" in url) \
                            and "about" not in url:
                        page = p_candidate
                        break

            # Fallback: última aba aberta
            if page is None:
                page = context.pages[-1]

            page.set_default_timeout(15000)
            print(f"Conectado! Página ativa: '{page.title()}'")

            sucesso = 0
            falhas  = 0

            for index, take in enumerate(takes):
                numero_take = START_TAKE_NUMBER + index
                try:
                    processar_take(page, index, take, erros_dir, img_nome)
                    sucesso += 1
                    print(f"   ⏸ Pausa de {PAUSA_ENTRE_TAKES}s...")
                    time.sleep(PAUSA_ENTRE_TAKES)

                except Exception as e:
                    falhas += 1
                    print(f"\n   ⚠ [ERRO] Take {numero_take}: {e}")
                    screenshot_erro(page, erros_dir, f"erro_take_{numero_take:03d}.png")
                    print("   ↩ Pulando para o próximo take...\n")
                    continue

            print(f"\n{'='*60}")
            print(f"=== Bot Flow finalizado! ===")
            print(f"   ✅ Enviados com sucesso: {sucesso}")
            print(f"   ❌ Falhas: {falhas}")
            if sucesso > 0:
                print("   Os vídeos estão sendo gerados no Google Flow.")

        except Exception as e:
            print(f"\n[FALHA CRÍTICA] {e}")
            print("Verifique se o Chrome está aberto com --remote-debugging-port=9222.")
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
