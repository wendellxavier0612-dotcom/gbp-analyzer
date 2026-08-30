"""
Comparativo com concorrentes da região.

Busca outros negócios parecidos (mesma categoria + cidade) e compara o
índice, nota média e quantidade de avaliações do negócio analisado contra
a média do mercado local — um dos pontos fortes dos relatórios de
referência (Lumos), que aqui é feito só com dados públicos.
"""

from core.engine import calcular_indice_simples, Concorrente, ComparativoConcorrencia


def _cidade_do_endereco(endereco: str | None) -> str | None:
    """Tenta extrair só a cidade de um endereço formatado tipo
    'Rua X, 123 - Bairro, Campinas - SP, 13000-000'. Não precisa ser
    perfeito — é só pra montar a query de busca dos concorrentes."""
    if not endereco:
        return None
    partes = [p.strip() for p in endereco.split(",")]
    # Geralmente o penúltimo ou último trecho antes do CEP tem "Cidade - UF".
    for parte in reversed(partes):
        if " - " in parte and any(c.isalpha() for c in parte):
            return parte.split(" - ")[0].strip()
    return partes[-2].strip() if len(partes) >= 2 else None


def montar_query_concorrentes(dados_negocio: dict) -> str | None:
    """Monta a query de busca dos concorrentes a partir da categoria
    principal e da cidade do negócio analisado. Devolve None se não tiver
    informação suficiente (nesse caso o comparativo é pulado)."""
    categorias = dados_negocio.get("categorias") or []
    # Blindagem: se por algum motivo vier algo que não seja uma lista de
    # strings (ex: dado malformado vindo de uma fonte diferente),
    # ignoramos em vez de quebrar o programa.
    primeira_categoria = categorias[0] if categorias else None
    categoria = primeira_categoria.replace("_", " ") if isinstance(primeira_categoria, str) else None
    cidade = _cidade_do_endereco(dados_negocio.get("endereco"))

    if not categoria and not cidade:
        return None
    if categoria and cidade:
        return f"{categoria} em {cidade}"
    return categoria or cidade


def gerar_comparativo(client, dados_negocio: dict, limite: int = 5) -> ComparativoConcorrencia | None:
    """
    client: SerpApiClient ou PlacesClient — precisa ter o método
            `buscar_concorrentes(query, excluir_place_id=..., limite=...)`.
    dados_negocio: dict no formato interno (saída de para_analise /
                   detalhes_para_analise) do negócio já analisado.

    Devolve None quando não foi possível montar uma busca de concorrentes
    (ex: sem categoria nem endereço) ou quando a busca não trouxe nenhum
    concorrente além do próprio negócio.
    """
    query = montar_query_concorrentes(dados_negocio)
    if not query:
        return None

    kwargs = {"limite": limite}
    if "place_id" in dados_negocio:
        kwargs["excluir_place_id"] = dados_negocio.get("place_id")
    if hasattr(client, "buscar_concorrentes") and "excluir_data_id" in client.buscar_concorrentes.__code__.co_varnames:
        kwargs["excluir_data_id"] = dados_negocio.get("data_id")

    try:
        brutos_concorrentes = client.buscar_concorrentes(query, **kwargs)
    except TypeError:
        # client (ex: PlacesClient) não aceita excluir_data_id
        kwargs.pop("excluir_data_id", None)
        brutos_concorrentes = client.buscar_concorrentes(query, **kwargs)

    if not brutos_concorrentes:
        return None

    concorrentes = []
    for c in brutos_concorrentes:
        concorrentes.append(Concorrente(
            nome=c.get("nome") or "Concorrente sem nome",
            indice=calcular_indice_simples(c),
            nota_media=c.get("nota_media") or 0,
            total_avaliacoes=c.get("total_avaliacoes") or 0,
            total_fotos=c.get("total_fotos"),
        ))

    indice_negocio = calcular_indice_simples(dados_negocio)

    todos = concorrentes + [Concorrente(
        nome=dados_negocio.get("nome") or "Seu negócio",
        indice=indice_negocio,
        nota_media=dados_negocio.get("nota_media") or 0,
        total_avaliacoes=dados_negocio.get("total_avaliacoes") or 0,
        total_fotos=dados_negocio.get("total_fotos"),
    )]
    ranking = sorted(todos, key=lambda c: c.indice, reverse=True)
    posicao = next((i + 1 for i, c in enumerate(ranking) if c.nome == dados_negocio.get("nome")), None)

    n = len(concorrentes)
    media_indice = sum(c.indice for c in concorrentes) / n
    media_nota = sum(c.nota_media for c in concorrentes) / n
    media_avaliacoes = sum(c.total_avaliacoes for c in concorrentes) / n

    return ComparativoConcorrencia(
        concorrentes=concorrentes,
        posicao=posicao,
        media_mercado_indice=round(media_indice, 1),
        media_mercado_nota=round(media_nota, 2),
        media_mercado_avaliacoes=round(media_avaliacoes, 1),
        nota_negocio=dados_negocio.get("nota_media") or 0,
        avaliacoes_negocio=dados_negocio.get("total_avaliacoes") or 0,
    )
