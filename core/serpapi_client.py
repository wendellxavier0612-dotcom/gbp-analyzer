import re
import urllib.parse
from typing import Any

import requests

BASE_URL = "https://serpapi.com/search"
_PADRAO_URL = re.compile(r"^https?://", re.IGNORECASE)
_PADRAO_DATA_ID = re.compile(r"!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)")


def eh_link_maps(texto: str) -> bool:
    return bool(_PADRAO_URL.match((texto or "").strip()))


def _normalizar_categorias(valor) -> list[str]:
    if not valor:
        return []
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, list):
        out = []
        for item in valor:
            out.extend(_normalizar_categorias(item))
        return out
    return []


class SerpApiClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key da SerpApi não foi informada.")
        self.api_key = api_key

    def _requisitar(self, params_extra: dict) -> dict:
        params = {"hl": "pt-BR", "google_domain": "google.com.br", "api_key": self.api_key, **params_extra}
        r = requests.get(BASE_URL, params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(f"SerpApi retornou erro: {data['error']}")
        return data

    def buscar(self, texto_busca: str) -> dict | None:
        data = self._requisitar({"engine": "google_maps", "type": "search", "q": texto_busca})
        if data.get("place_results"):
            return data["place_results"]
        rows = data.get("local_results", [])
        return rows[0] if rows else None

    def buscar_por_link(self, url_maps: str) -> dict | None:
        final = self._resolver_url(url_maps)
        m = _PADRAO_DATA_ID.search(final)
        if m:
            cid = str(int(m.group(1).split(":")[-1], 16))
            bruto = self._buscar_por_data_cid(cid)
            if bruto:
                return bruto
        if "/place/" in final:
            nome = final.split("/place/")[-1].split("/")[0]
            nome = urllib.parse.unquote(nome.replace("+", " "))
            if nome:
                return self.buscar(nome)
        return None

    def _resolver_url(self, url: str) -> str:
        try:
            r = requests.get(url, timeout=15, allow_redirects=True)
            return r.url
        except requests.RequestException:
            return url

    def _buscar_por_data_cid(self, data_cid: str) -> dict | None:
        data = self._requisitar({"engine": "google_maps", "type": "place", "data_cid": data_cid})
        return data.get("place_results")

    def buscar_detalhes(self, resultado: dict) -> dict:
        data_id = resultado.get("data_id")
        place_id = resultado.get("place_id")
        if not data_id and not place_id:
            return resultado
        params = {"engine": "google_maps", "type": "place"}
        if data_id:
            params["data_id"] = data_id
        else:
            params["place_id"] = place_id
        try:
            data = self._requisitar(params)
            return data.get("place_results") or resultado
        except Exception:
            return resultado

    def buscar_fotos(self, data_id: str, category_id: str | None = None, limite: int = 100) -> dict:
        if not data_id:
            return {"photos": [], "categories": []}
        params = {"engine": "google_maps_photos", "data_id": data_id}
        if category_id:
            params["category_id"] = category_id
        data = self._requisitar(params)
        photos = data.get("photos") or []
        return {"photos": photos[:limite], "categories": data.get("categories") or [], "next_page_token": (data.get("serpapi_pagination") or {}).get("next_page_token")}

    @staticmethod
    def _categoria_id(categories: list[dict], *termos: str) -> str | None:
        for c in categories:
            title = (c.get("title") or "").lower()
            if any(t in title for t in termos):
                return c.get("id")
        return None

    def buscar_reviews(self, data_id: str | None, place_id: str | None = None, limite: int = 100) -> list[dict]:
        if not data_id and not place_id:
            return []
        params = {"engine": "google_maps_reviews", "sort_by": "newestFirst"}
        if data_id:
            params["data_id"] = data_id
        else:
            params["place_id"] = place_id
        try:
            data = self._requisitar(params)
            return (data.get("reviews") or [])[:limite]
        except Exception:
            return []

    def buscar_posts(self, data_id: str | None, limite: int = 20) -> list[dict]:
        if not data_id:
            return []
        try:
            data = self._requisitar({"engine": "google_maps_posts", "data_id": data_id})
            return (data.get("posts") or [])[:limite]
        except Exception:
            return []

    def enriquecer_reviews_e_posts(self, data_id: str | None, place_id: str | None) -> dict:
        reviews = self.buscar_reviews(data_id, place_id)
        posts = self.buscar_posts(data_id)
        sem_comentario = sum(1 for r in reviews if not (r.get("snippet") or r.get("extracted_snippet")))
        sem_resposta = sum(1 for r in reviews if not r.get("response"))
        datas = [r.get("iso_date") for r in reviews if r.get("iso_date")]
        return {
            "reviews_amostra": reviews,
            "reviews_amostra_qtd": len(reviews),
            "reviews_sem_comentario": sem_comentario,
            "reviews_sem_resposta": sem_resposta,
            "reviews_comentadas": len(reviews) - sem_comentario,
            "reviews_respondidas": len(reviews) - sem_resposta,
            "tendencia_reviews_datas": datas,
            "posts_google": posts,
            "total_posts_google": len(posts),
            "ultimo_post_google": posts[0].get("posted_at") or posts[0].get("posted_at_text") if posts else None,
        }

    def enriquecer_midia(self, data_id: str | None) -> dict:
        if not data_id:
            return {"midia_fotos": [], "midia_videos": [], "midia_dono": [], "midia_clientes": [], "categorias_fotos": []}
        base = self.buscar_fotos(data_id)
        cats = base["categories"]
        video_id = self._categoria_id(cats, "video", "vídeo", "videos", "vídeos")
        owner_id = self._categoria_id(cats, "owner", "propriet", "proprietário")
        try:
            videos = self.buscar_fotos(data_id, video_id).get("photos", []) if video_id else []
        except Exception:
            videos = []
        try:
            owner = self.buscar_fotos(data_id, owner_id).get("photos", []) if owner_id else []
        except Exception:
            owner = []
        video_keys = {p.get("image") or p.get("thumbnail") for p in videos}
        owner_keys = {p.get("image") or p.get("thumbnail") for p in owner}
        fotos = [p for p in base["photos"] if (p.get("image") or p.get("thumbnail")) not in video_keys]
        clientes = [p for p in base["photos"] if (p.get("image") or p.get("thumbnail")) not in owner_keys]
        return {
            "midia_fotos": fotos,
            "midia_videos": videos,
            "midia_dono": owner,
            "midia_clientes": clientes,
            "categorias_fotos": cats,
        }

    def para_analise(self, bruto: dict, enriquecer: bool = True) -> dict:
        resultado = self.buscar_detalhes(bruto) if enriquecer else bruto
        categorias = _normalizar_categorias(resultado.get("types")) or _normalizar_categorias(resultado.get("type"))
        imagens = resultado.get("images") if isinstance(resultado.get("images"), list) else []
        logo_url = resultado.get("logo") or resultado.get("profile_photo") or resultado.get("logo_url")
        thumbnail = resultado.get("thumbnail")
        desc = resultado.get("description")
        if isinstance(desc, dict):
            desc = desc.get("snippet") or desc.get("text")
        dados = {
            "nome": resultado.get("title"),
            "telefone": resultado.get("phone"),
            "website": resultado.get("website") or (resultado.get("links") or {}).get("website"),
            "categorias": categorias,
            "horario_funcionamento": bool(resultado.get("operating_hours") or resultado.get("hours")),
            "total_avaliacoes": resultado.get("reviews", 0),
            "nota_media": resultado.get("rating", 0),
            "total_fotos": len(imagens) if imagens else None,
            "tem_foto_capa": bool(thumbnail),
            "descricao": desc,
            "endereco": resultado.get("address"),
            "status": "Fechado" if resultado.get("permanently_closed") else "Ativo",
            "place_id": resultado.get("place_id"),
            "data_id": resultado.get("data_id"),
            "logo_url": logo_url,
            "foto_perfil_url": thumbnail,
            "horario_especial": resultado.get("special_hours") or resultado.get("holiday_hours"),
            "servicos": resultado.get("services"),
            "raw": resultado,
        }
        if enriquecer and dados["data_id"]:
            dados.update(self.enriquecer_midia(dados["data_id"]))
            dados.update(self.enriquecer_reviews_e_posts(dados["data_id"], dados.get("place_id")))
            dados["total_videos"] = len(dados.get("midia_videos") or [])
            dados["total_fotos"] = len(dados.get("midia_fotos") or [])
            dados["total_midia"] = dados["total_fotos"] + dados["total_videos"]
            dados["tem_logotipo"] = bool(logo_url)
        return dados

    def buscar_e_analisar(self, texto_busca: str) -> dict | None:
        texto_busca = (texto_busca or "").strip()
        if not texto_busca:
            return None
        bruto = self.buscar_por_link(texto_busca) if eh_link_maps(texto_busca) else self.buscar(texto_busca)
        return self.para_analise(bruto) if bruto else None

    def buscar_lista(self, texto_busca: str, limite: int = 6) -> list[dict]:
        data = self._requisitar({"engine": "google_maps", "type": "search", "q": texto_busca})
        rows = data.get("local_results") or []
        if not rows and data.get("place_results"):
            rows = [data["place_results"]]
        return rows[:limite]

    def buscar_concorrentes(self, texto_busca: str, excluir_place_id: str | None = None, excluir_data_id: str | None = None, limite: int = 5) -> list[dict]:
        out = []
        for bruto in self.buscar_lista(texto_busca, limite=limite + 2):
            if excluir_place_id and bruto.get("place_id") == excluir_place_id:
                continue
            if excluir_data_id and bruto.get("data_id") == excluir_data_id:
                continue
            out.append(self.para_analise(bruto, enriquecer=True))
            if len(out) >= limite:
                break
        return out
