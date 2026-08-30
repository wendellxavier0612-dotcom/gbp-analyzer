import re
import unicodedata
from typing import Any

import requests

BASE_URL = "https://serpapi.com/search"


def _normalizar(texto: str | None) -> str:
    texto = (texto or "").lower().strip()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _slug(texto: str | None) -> str:
    return re.sub(r"[^a-z0-9_]", "", _normalizar(texto).replace(" ", ""))


def extrair_username(url: str | None) -> str | None:
    if not url or "instagram.com" not in url.lower():
        return None
    m = re.search(r"instagram\.com/([^/?#]+)", url, re.I)
    return m.group(1).lstrip("@") if m else None


class InstagramClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key da SerpApi não foi informada.")
        self.api_key = api_key

    def _requisitar(self, params: dict) -> dict:
        p = {"api_key": self.api_key, **params}
        r = requests.get(BASE_URL, params=p, timeout=25)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(f"SerpApi/Instagram: {data['error']}")
        return data

    def buscar_username(self, nome: str, cidade: str | None = None) -> str | None:
        q = f'site:instagram.com "{nome}"'
        if cidade:
            q += f' "{cidade}"'
        data = self._requisitar({"engine": "google", "q": q, "num": 10, "hl": "pt-BR", "gl": "br"})
        candidatos = []
        for row in data.get("organic_results", []):
            link = row.get("link") or ""
            user = extrair_username(link)
            if not user or user in {"explore", "accounts", "p", "reel", "reels"}:
                continue
            title = row.get("title") or ""
            snippet = row.get("snippet") or ""
            score = self._score(nome, cidade, user, title, snippet)
            candidatos.append((score, user))
        candidatos.sort(reverse=True)
        return candidatos[0][1] if candidatos and candidatos[0][0] >= 0.48 else None

    @staticmethod
    def _score(nome: str, cidade: str | None, username: str, title: str, snippet: str) -> float:
        alvo = _normalizar(nome)
        campos = [_normalizar(username), _normalizar(title), _normalizar(snippet)]
        score = 0.0
        if _slug(nome) in _slug(username):
            score += 0.55
        alvo_tokens = set(alvo.split())
        texto = " ".join(campos)
        if alvo_tokens:
            score += 0.35 * (len(alvo_tokens & set(texto.split())) / len(alvo_tokens))
        if cidade and _normalizar(cidade) in texto:
            score += 0.10
        return min(score, 1.0)

    def buscar_perfil(self, username: str) -> dict | None:
        data = self._requisitar({"engine": "instagram_profile", "profile_id": username})
        return data.get("profile_results") or None

    def analisar(self, nome: str, cidade: str | None = None, instagram_url: str | None = None) -> dict:
        username = extrair_username(instagram_url) or self.buscar_username(nome, cidade)
        if not username:
            return {"encontrado": False, "status": "nao_encontrado", "mensagem": "Nenhum perfil do Instagram foi confirmado para este negócio."}
        perfil = self.buscar_perfil(username)
        if not perfil:
            return {"encontrado": False, "status": "erro_consulta", "username": username, "mensagem": "O perfil foi localizado, mas os dados públicos não puderam ser lidos."}

        posts = perfil.get("posts") or []
        fotos = sum(1 for p in posts if not p.get("is_video"))
        videos = sum(1 for p in posts if p.get("is_video"))
        return {
            "encontrado": True,
            "status": "confirmado",
            "username": perfil.get("username") or username,
            "url": f"https://www.instagram.com/{perfil.get('username') or username}/",
            "nome": perfil.get("full_name"),
            "bio": perfil.get("biography"),
            "foto_perfil": perfil.get("profile_pic_url_hd") or perfil.get("profile_pic_url") or perfil.get("serpapi_profile_pic_url_hd"),
            "seguidores": perfil.get("followers"),
            "seguindo": perfil.get("following"),
            "publicacoes_total": perfil.get("posts_count"),
            "amostra_fotos": fotos,
            "amostra_videos": videos,
            "tem_reels": perfil.get("has_reels"),
            "conta_profissional": perfil.get("is_professional_account"),
            "conta_empresa": perfil.get("is_business_account"),
            "verificado": perfil.get("is_verified"),
            "privado": perfil.get("is_private"),
            "categoria": perfil.get("category_name"),
            "site_externo": perfil.get("external_url"),
            "bio_links": perfil.get("bio_links") or [],
            "posts": [self._normalizar_post(p) for p in posts[:12]],
        }

    @staticmethod
    def _normalizar_post(post: dict[str, Any]) -> dict:
        return {
            "tipo": "vídeo/reel" if post.get("is_video") else "foto/carrossel",
            "imagem": post.get("serpapi_display_url") or post.get("display_url") or post.get("thumbnail_src") or post.get("serpapi_thumbnail_src"),
            "link": post.get("link") or post.get("shortcode"),
            "legenda": (post.get("media_captions") or [None])[0],
            "curtidas": post.get("liked_by_count"),
            "comentarios": post.get("comments_count"),
            "data": post.get("timestamp") or post.get("taken_at"),
        }
