"""
Cliente da Places API (New) do Google — busca dados públicos de um
negócio (sem precisar de acesso administrador ao perfil).

Uso típico:
    client = PlacesClient(api_key="SUA_CHAVE")
    place_id = client.buscar_place_id("Instituto Nail Studio Campinas")
    dados = client.detalhes_para_analise(place_id)
"""

import requests

BASE_URL = "https://places.googleapis.com/v1"


class PlacesClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key da Places API não foi informada.")
        self.api_key = api_key

    # -----------------------------------------------------------------
    # Busca (Text Search) — usada quando o usuário digita nome + cidade
    # -----------------------------------------------------------------
    def buscar_place_id(self, texto_busca: str) -> str | None:
        """Busca por texto livre (ex: 'Instituto Nail Studio Campinas')
        e devolve o place_id do primeiro resultado, ou None."""
        url = f"{BASE_URL}/places:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            # FieldMask: só pedimos os campos que vamos usar, pra gastar
            # menos cota. Mais campos = mais caro por chamada.
            "X-Goog-FieldMask": "places.id,places.displayName",
        }
        body = {"textQuery": texto_busca, "languageCode": "pt-BR"}
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        resp.raise_for_status()
        dados = resp.json()
        lugares = dados.get("places", [])
        return lugares[0]["id"] if lugares else None

    def buscar_place_ids(self, texto_busca: str, limite: int = 6) -> list[str]:
        """Igual a buscar_place_id, mas devolve até `limite` ids — usado
        no comparativo de concorrentes."""
        url = f"{BASE_URL}/places:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "places.id,places.displayName",
        }
        body = {"textQuery": texto_busca, "languageCode": "pt-BR"}
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        resp.raise_for_status()
        dados = resp.json()
        lugares = dados.get("places", [])
        return [p["id"] for p in lugares[:limite]]

    def place_id_por_url_maps(self, url_maps: str) -> str | None:
        """Aceita um link do Google Maps (ex: colado pelo usuário) e tenta
        extrair/redirecionar até achar o place_id. Links curtos
        (maps.app.goo.gl) redirecionam para uma URL com o nome do local —
        nesse caso caímos de volta para busca por texto."""
        try:
            resp = requests.get(url_maps, timeout=15, allow_redirects=True)
            # A URL final geralmente contém o nome do lugar; melhor
            # extrair e usar busca por texto do que tentar parsear coordenadas.
            nome_aproximado = resp.url.split("/place/")[-1].split("/")[0]
            nome_aproximado = nome_aproximado.replace("+", " ")
            return self.buscar_place_id(nome_aproximado)
        except (requests.RequestException, IndexError):
            return None

    # -----------------------------------------------------------------
    # Detalhes do local
    # -----------------------------------------------------------------
    def detalhes(self, place_id: str) -> dict:
        url = f"{BASE_URL}/places/{place_id}"
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": ",".join([
                "id", "displayName", "nationalPhoneNumber",
                "internationalPhoneNumber", "websiteUri",
                "regularOpeningHours", "primaryType", "types",
                "rating", "userRatingCount", "reviews",
                "photos", "editorialSummary", "businessStatus",
                "formattedAddress",
            ]),
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def detalhes_para_analise(self, place_id: str) -> dict:
        """Converte a resposta bruta da API pro formato que o
        core/engine.py espera (ver core/criteria.py)."""
        d = self.detalhes(place_id)
        fotos = d.get("photos", [])
        return {
            "nome": d.get("displayName", {}).get("text"),
            "telefone": d.get("nationalPhoneNumber"),
            "website": d.get("websiteUri"),
            "categorias": d.get("types", []),
            "horario_funcionamento": bool(d.get("regularOpeningHours")),
            "total_avaliacoes": d.get("userRatingCount", 0),
            "nota_media": d.get("rating", 0),
            "total_fotos": len(fotos),
            # Na Places API (New), o primeiro item de "photos" é a foto
            # que aparece como capa/destaque do perfil.
            "tem_foto_capa": len(fotos) > 0,
            "descricao": d.get("editorialSummary", {}).get("text"),
            "endereco": d.get("formattedAddress"),
            "status": d.get("businessStatus"),
            "place_id": d.get("id"),
        }

    def buscar_concorrentes(self, texto_busca: str, excluir_place_id: str | None = None,
                             limite: int = 5) -> list[dict]:
        """Busca uma lista de negócios (ex: 'salão de unhas em Campinas')
        já convertida pro formato interno, excluindo o próprio negócio
        analisado, para montar o comparativo de concorrência."""
        ids = self.buscar_place_ids(texto_busca, limite=limite + 1)
        convertidos = []
        for pid in ids:
            if excluir_place_id and pid == excluir_place_id:
                continue
            convertidos.append(self.detalhes_para_analise(pid))
            if len(convertidos) >= limite:
                break
        return convertidos
