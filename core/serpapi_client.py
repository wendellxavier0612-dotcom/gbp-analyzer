"""
Cliente que busca dados públicos de um perfil do Google Maps via SerpApi
(https://serpapi.com) — alternativa à Places API do Google que NÃO exige
conta de faturamento no Google Cloud, só um cadastro no site deles.

Aceita tanto texto livre quanto um link do Google Maps colado pelo
usuário (link completo, link curto "maps.app.goo.gl" ou "g.co/kgs").

Uso típico:
    client = SerpApiClient(api_key="SUA_CHAVE_SERPAPI")
    dados = client.buscar_e_analisar("Instituto Nail Studio Campinas")
    # ou
    dados = client.buscar_e_analisar("https://maps.app.goo.gl/xxxxx")
"""

import re
import urllib.parse

import requests

BASE_URL = "https://serpapi.com/search"

# Reconhece se o texto digitado é um link em vez de um nome de negócio.
_PADRAO_URL = re.compile(r"^https?://", re.IGNORECASE)

# Dentro de uma URL completa do Google Maps, o identificador exato do
# lugar (data_id) aparece no parâmetro "data", no trecho "!1s<hex>:<hex>".
# Ex: .../data=!4m5!3m4!1s0x94c8be...:0xabc123...!8m2!3d...!4d...
_PADRAO_DATA_ID = re.compile(r"!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)")


def eh_link_maps(texto: str) -> bool:
    """True se o texto parece ser um link (Maps ou encurtado) em vez de
    um nome de negócio digitado à mão."""
    return bool(_PADRAO_URL.match((texto or "").strip()))


def _normalizar_categorias(valor) -> list[str]:
    """A SerpApi não é 100% consistente: às vezes 'types'/'type' vem como
    string única, às vezes como lista de strings, e em alguns perfis
    aparece até lista aninhada. Essa função sempre devolve uma lista
    plana de strings (ou lista vazia), pra nunca quebrar quem consome
    esse campo depois (ex: categorias[0].replace(...))."""
    if not valor:
        return []
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, list):
        categorias: list[str] = []
        for item in valor:
            categorias.extend(_normalizar_categorias(item))
        return categorias
    return []


def _extrair_atributos_servico(extensions) -> list[str]:
    """A busca 'type=place' às vezes traz um bloco 'extensions' com
    listas de atributos do perfil (ex: {'service_options': ['Takeaway',
    'Delivery', ...]}, {'highlights': [...]}). Isso é DIFERENTE da lista
    de "Serviços" que o dono cadastra manualmente no painel (essa não é
    exposta em nenhuma fonte pública) — aqui pegamos só os atributos que
    o próprio Google mostra na busca, como um sinal parcial."""
    atributos: list[str] = []
    if not isinstance(extensions, list):
        return atributos
    for bloco in extensions:
        if isinstance(bloco, dict):
            valores = bloco.get("service_options")
            if isinstance(valores, list):
                atributos.extend(str(v) for v in valores)
    return atributos


def _extrair_galeria(imagens_brutas) -> list[dict]:
    """Converte a lista de imagens da SerpApi (dicts com 'thumbnail' e às
    vezes 'title') numa galeria com URL + um palpite de tipo (foto/vídeo).
    A SerpApi não documenta um campo confiável pra distinguir vídeo de
    foto nesse endpoint — o palpite abaixo é best-effort (usa a palavra
    'video' no título, quando existe) e pode errar; por isso a galeria é
    mostrada como "mídia" de forma geral na interface, não separada com
    garantia total."""
    galeria: list[dict] = []
    if not isinstance(imagens_brutas, list):
        return galeria
    for img in imagens_brutas:
        if not isinstance(img, dict):
            continue
        url = img.get("thumbnail") or img.get("image")
        if not url:
            continue
        titulo = (img.get("title") or "").strip()
        tipo = "video" if "video" in titulo.lower() else "foto"
        galeria.append({"url": url, "titulo": titulo or None, "tipo": tipo})
    return galeria


class SerpApiClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key da SerpApi não foi informada.")
        self.api_key = api_key

    # -----------------------------------------------------------------
    # Requisição de baixo nível (usada por todos os métodos de busca)
    # -----------------------------------------------------------------
    def _requisitar(self, params_extra: dict) -> dict:
        params = {
            "engine": "google_maps",
            "hl": "pt-BR",
            "google_domain": "google.com.br",
            "api_key": self.api_key,
            **params_extra,
        }
        resp = requests.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        dados = resp.json()

        erro = dados.get("error")
        if erro:
            raise RuntimeError(f"SerpApi retornou erro: {erro}")

        return dados

    # -----------------------------------------------------------------
    # Busca de um único negócio por texto livre
    # -----------------------------------------------------------------
    def buscar(self, texto_busca: str) -> dict | None:
        """Busca por texto livre (ex: 'Instituto Nail Studio Campinas')
        e devolve o primeiro resultado bruto da SerpApi, ou None."""
        dados = self._requisitar({"type": "search", "q": texto_busca})

        # Quando a busca casa com um único lugar específico, o Google
        # devolve "place_results" (objeto único) em vez de "local_results"
        # (lista) — precisamos checar os dois formatos.
        if dados.get("place_results"):
            return dados["place_results"]

        resultados = dados.get("local_results", [])
        return resultados[0] if resultados else None

    # -----------------------------------------------------------------
    # Busca de um único negócio a partir de um link do Google Maps
    # -----------------------------------------------------------------
    def _resolver_url(self, url: str) -> str:
        """Segue redirecionamentos (necessário pra links curtos como
        maps.app.goo.gl ou g.co/kgs) até chegar na URL final do Maps."""
        try:
            resp = requests.get(url, timeout=15, allow_redirects=True)
            return resp.url
        except requests.RequestException:
            return url

    def buscar_por_link(self, url_maps: str) -> dict | None:
        """Aceita um link do Google Maps colado pelo usuário e localiza
        o perfil correspondente, tentando nesta ordem:

        1) extrair o identificador exato do lugar (data_id) embutido no
           próprio link e buscar por ele — é o caminho mais preciso,
           porque não depende do nome bater;
        2) se não achar (ex: link curto cuja URL final não expõe esse
           identificador), extrair o nome aproximado do trecho
           "/place/Nome+Aqui/" da URL e cair para busca por texto.
        """
        url_final = self._resolver_url(url_maps)

        casa = _PADRAO_DATA_ID.search(url_final)
        if casa:
            data_id = casa.group(1)
            cid_decimal = str(int(data_id.split(":")[-1], 16))
            bruto = self._buscar_por_data_cid(cid_decimal)
            if bruto:
                return bruto

        if "/place/" in url_final:
            nome_aproximado = url_final.split("/place/")[-1].split("/")[0]
            nome_aproximado = urllib.parse.unquote(nome_aproximado.replace("+", " "))
            if nome_aproximado:
                return self.buscar(nome_aproximado)

        return None

    def _buscar_por_data_cid(self, data_cid: str) -> dict | None:
        """Busca direta por CID (Customer ID) — identificador único e
        estável do lugar no Google, obtido a partir do link."""
        dados = self._requisitar({"data_cid": data_cid})
        return dados.get("place_results")

    # -----------------------------------------------------------------
    # Enriquecimento: segunda consulta (type=place) pelo data_id
    # -----------------------------------------------------------------
    def buscar_detalhes_lugar(self, data_id: str | None) -> dict:
        """A busca inicial (type=search) às vezes devolve um resultado
        'enxuto', sem descrição completa nem os links reais das fotos.
        Essa segunda chamada, pelo data_id do mesmo lugar, costuma trazer
        mais campos preenchidos (description, extensions, images). Se
        falhar por qualquer motivo, devolve {} — nunca derruba a análise
        principal por causa de um enriquecimento que é só um "extra"."""
        if not data_id:
            return {}
        try:
            dados = self._requisitar({"type": "place", "data_id": data_id})
        except Exception:
            return {}
        return dados.get("place_results") or {}

    @staticmethod
    def _mesclar_detalhes(bruto: dict, detalhado: dict) -> dict:
        """Combina o resultado da busca inicial com o resultado detalhado
        do mesmo lugar, dando preferência ao que veio do detalhado nos
        campos em que ele tende a ser mais completo."""
        if not detalhado:
            return bruto
        mesclado = dict(bruto)
        for chave in ("description", "images", "extensions", "hours", "thumbnail"):
            if detalhado.get(chave):
                mesclado[chave] = detalhado[chave]
        return mesclado

    # -----------------------------------------------------------------
    # Busca de vários negócios (usado no comparativo de concorrentes)
    # -----------------------------------------------------------------
    def buscar_lista(self, texto_busca: str, limite: int = 6) -> list[dict]:
        """Busca por texto livre e devolve até `limite` resultados brutos
        (formato "local_results"). Útil para pesquisas tipo 'categoria +
        cidade', que tendem a devolver uma lista de negócios parecidos —
        é a base do comparativo de concorrência."""
        dados = self._requisitar({"type": "search", "q": texto_busca})

        if dados.get("local_results"):
            return dados["local_results"][:limite]

        # Se por acaso casou com um único lugar específico, devolvemos
        # ele sozinho numa lista.
        if dados.get("place_results"):
            return [dados["place_results"]]

        return []

    # -----------------------------------------------------------------
    # Conversão pro formato interno usado por core/engine.py
    # -----------------------------------------------------------------
    def para_analise(self, resultado_bruto: dict) -> dict:
        """Converte a resposta bruta da SerpApi pro formato que o
        core/engine.py espera (ver core/criteria.py).

        A SerpApi devolve dois formatos possíveis: "local_results" (lista,
        quando a busca é ampla) e "place_results" (objeto único, quando a
        busca casa com um lugar específico). Os nomes de campo mudam um
        pouco entre os dois — esse método lida com ambos."""
        categorias = _normalizar_categorias(resultado_bruto.get("types"))
        if not categorias:
            categorias = _normalizar_categorias(resultado_bruto.get("type"))

        galeria = _extrair_galeria(resultado_bruto.get("images"))
        total_fotos = len([g for g in galeria if g["tipo"] == "foto"]) or None
        total_videos = len([g for g in galeria if g["tipo"] == "video"]) or None

        # "Foto de capa" = a foto principal exibida no card/perfil. A
        # SerpApi normalmente traz isso no campo "thumbnail" (é a mesma
        # imagem que aparece de capa no Google Maps). Quando esse campo
        # existe, consideramos que há foto de capa definida; quando o
        # negócio não tem nenhuma foto, thumbnail também vem vazio.
        tem_foto_capa = bool(resultado_bruto.get("thumbnail"))

        atributos_servico = _extrair_atributos_servico(resultado_bruto.get("extensions"))

        return {
            "nome": resultado_bruto.get("title"),
            "telefone": resultado_bruto.get("phone"),
            "website": resultado_bruto.get("website") or resultado_bruto.get("links", {}).get("website"),
            "categorias": categorias or [],
            "horario_funcionamento": bool(resultado_bruto.get("operating_hours") or resultado_bruto.get("hours")),
            "total_avaliacoes": resultado_bruto.get("reviews", 0),
            "nota_media": resultado_bruto.get("rating", 0),
            "total_fotos": total_fotos,
            "total_videos": total_videos,
            "tem_foto_capa": tem_foto_capa,
            "descricao": resultado_bruto.get("description"),
            "endereco": resultado_bruto.get("address"),
            "status": "Fechado" if resultado_bruto.get("permanently_closed") else "Ativo",
            "place_id": resultado_bruto.get("place_id"),
            "data_id": resultado_bruto.get("data_id"),
            # Novos campos usados pela interface / critérios:
            "galeria": galeria,                    # [{'url','titulo','tipo'}, ...] — pra galeria visual
            "servicos": atributos_servico or None,  # atributos públicos (não é a lista cadastrada no painel)
        }

    def buscar_e_analisar(self, texto_busca: str) -> dict | None:
        """Ponto de entrada único: aceita tanto um nome de negócio quanto
        um link do Google Maps colado pelo usuário, busca os dados, tenta
        enriquecer com a consulta detalhada (type=place) e devolve tudo
        já no formato interno."""
        texto_busca = (texto_busca or "").strip()
        if not texto_busca:
            return None

        bruto = self.buscar_por_link(texto_busca) if eh_link_maps(texto_busca) else self.buscar(texto_busca)
        if bruto is None:
            return None

        detalhado = self.buscar_detalhes_lugar(bruto.get("data_id"))
        bruto = self._mesclar_detalhes(bruto, detalhado)

        return self.para_analise(bruto)

    def buscar_concorrentes(self, texto_busca: str, excluir_place_id: str | None = None,
                             excluir_data_id: str | None = None, limite: int = 5) -> list[dict]:
        """Busca uma lista de negócios (ex: 'salão de unhas em Campinas')
        já convertida pro formato interno, excluindo o próprio negócio
        analisado (por place_id/data_id) para não comparar ele consigo
        mesmo."""
        brutos = self.buscar_lista(texto_busca, limite=limite + 1)
        convertidos = []
        for bruto in brutos:
            pid = bruto.get("place_id")
            did = bruto.get("data_id")
            if excluir_place_id and pid == excluir_place_id:
                continue
            if excluir_data_id and did == excluir_data_id:
                continue
            convertidos.append(self.para_analise(bruto))
            if len(convertidos) >= limite:
                break
        return convertidos
