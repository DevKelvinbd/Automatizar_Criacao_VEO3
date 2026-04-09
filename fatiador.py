import os


PONTUACOES = ['.', '?', '!', ',']
MAX_CHARS  = 150
MIN_CHARS  = 50   # takes menores que isso são mesclados com o adjacente


def mesclar_takes_curtos(takes: list[str], min_chars: int = MIN_CHARS) -> list[str]:
    """Mescla takes com menos de min_chars caracteres com o take seguinte.
    Se o último take for curto, mescla com o anterior."""
    if not takes:
        return takes

    mesclados: list[str] = []
    acumulado = ""

    for take in takes:
        if acumulado:
            # Junta o acumulado com o take atual
            acumulado = acumulado + " " + take
        else:
            acumulado = take

        if len(acumulado) >= min_chars:
            mesclados.append(acumulado)
            acumulado = ""

    # Se sobrou texto acumulado no final
    if acumulado:
        if mesclados:
            # Mescla com o último take
            mesclados[-1] = mesclados[-1] + " " + acumulado
        else:
            # Único take — mantém mesmo se curto
            mesclados.append(acumulado)

    return mesclados


def fatiar_texto(input_file: str, output_file: str, max_chars: int = MAX_CHARS) -> None:
    """
    Lê o roteiro.txt e divide em takes de até max_chars caracteres.
    A lógica de corte é:
      1. Procura a última pontuação no bloco (., ?, !, ,) → corta APÓS ela.
      2. Se não encontrar, corta no último espaço (sem quebrar palavras).
      3. Se não houver espaço, corta no limite exato (segurança).

    Após o fatiamento, takes com menos de MIN_CHARS caracteres são
    mesclados com o take seguinte para evitar prompts curtos demais.
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            texto = f.read()
    except FileNotFoundError:
        print(f"Erro: Arquivo '{input_file}' não encontrado.")
        return

    # Normaliza quebras de linha e espaços múltiplos em um único espaço
    texto: str = ' '.join(texto.split())

    if not texto:
        print("Arquivo de roteiro está vazio. Insira o seu texto em roteiro.txt.")
        return

    takes = []

    while texto:
        # Caso o texto restante caiba num bloco, adicionamos direto
        if len(texto) <= max_chars:
            takes.append(texto.strip())  # type: ignore[union-attr]
            break

        bloco: str = texto[:max_chars]  # type: ignore[index]

        # 1. Última pontuação no bloco
        corte_idx: int = max([bloco.rfind(p) for p in PONTUACOES])

        if corte_idx > 0:
            corte = corte_idx + 1          # inclui o sinal de pontuação
        else:
            # 2. Último espaço (não quebra palavra)
            corte_idx = bloco.rfind(' ')
            if corte_idx > 0:
                corte = corte_idx          # exclui o espaço
            else:
                # 3. Corte rígido (fallback extremo — palavra muito longa)
                corte = max_chars

        # ── Anti-orfão: se o texto restante começa com um fragmento MUITO curto
        # antes da próxima frase (. ? !), estende o corte para incluí-lo.
        # Ex: evita que "rápida." fique sozinho no próximo take.
        # Threshold baixo (30 chars) para não absorver fragmentos longos.
        ORFAO_THRESHOLD = 30  # só absorve fragmentos < 30 chars
        HARD_CAP = max_chars + 20  # nunca ultrapassar 170 chars
        restante = texto[corte:].strip()  # type: ignore[index]
        if restante:
            # Procura o próximo ponto final de frase no restante
            fim_frases = ['.', '?', '!']
            prox_fim = -1
            for p in fim_frases:
                idx = restante.find(p)
                if idx >= 0:
                    if prox_fim < 0 or idx < prox_fim:
                        prox_fim = idx
            # Se o fragmento até o próximo fim de frase é MUITO curto,
            # estende o corte para absorvê-lo (mas respeitando o teto)
            if 0 <= prox_fim < ORFAO_THRESHOLD:
                novo_corte = corte + len(texto[corte:]) - len(restante) + prox_fim + 1  # type: ignore[index]
                if novo_corte <= HARD_CAP:
                    corte = novo_corte

        take_atual: str = texto[:corte].strip()  # type: ignore[index]
        if take_atual:                     # evita takes vazios
            takes.append(take_atual)

        texto = texto[corte:].strip()  # type: ignore[index]

    # Pós-processamento: mescla takes curtos (< MIN_CHARS) com o adjacente
    takes_antes = len(takes)
    takes = mesclar_takes_curtos(takes)
    if len(takes) < takes_antes:
        print(f"⚠ {takes_antes - len(takes)} take(s) curto(s) (< {MIN_CHARS} chars) mesclado(s) com adjacente(s).")

    # Salva no arquivo de saída, um take por linha
    with open(output_file, 'w', encoding='utf-8') as f:
        for take in takes:
            f.write(take + '\n')

    print(f"✔ Sucesso! {len(takes)} takes gerados → '{output_file}'")
    print()
    for i, take in enumerate(takes, 1):
        print(f"  [{i:03d}] ({len(take)} chars) {take}")


if __name__ == "__main__":
    base      = os.environ.get("VEO3_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
    roteiro   = os.path.join(base, 'roteiro.txt')
    takes_out = os.path.join(base, 'takes.txt')

    fatiar_texto(roteiro, takes_out)
