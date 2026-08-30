"""
Leitura leve (best-effort) da página inicial do site oficial do negócio,
usada como FALLBACK para preencher lacunas que o Google Maps não expõe
de forma confiável via busca pública — mas que costumam estar na cara
na própria página do cliente: descrição, logotipo e link do Instagram.

Importante:
- Só olha a home page do site (não navega o site inteiro).
- Nunca derruba a análise: qualquer falha (site fora do ar, bloqueio,
  timeout) devolve os campos vazios, não uma exceção.
- É FALLBACK: só é usado quando o dado não veio do Google Maps.
"""

import re
import urllib.parse

import requests

_TIMEOUT = 8
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# meta name="description" ou property="og:description"
_PADRAO_META_DESC = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](og:description|description)["\']'
    r'[^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_PADRAO_OG_IMAGE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_PADRAO_ICON = re.compile(
    r'<link[^>]+rel=["\'](?:apple-touch-icon|icon)["\'][^>]+href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_PADRAO_INSTAGRAM = re.compile(
    r'https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.\-]+/?',
    re.IGNORECASE,
)


def _absolutizar(url_base: str, possivel_relativa: str) -> str:
    return urllib.parse.urljoin(url_base, possivel_relativa)


def extrair_dados_site(website_url: str) -> dict:
    """Devolve {'descricao', 'logo_url', 'instagram_url'} (cada um str
    ou None) lendo a home page do site informado. Nunca levanta exceção
    — qualquer problema de rede/parsing devolve tudo None."""
    vazio = {"descricao": None, "logo_url": None, "instagram_url": None}
    if not website_url:
        return vazio

    try:
        resp = requests.get(website_url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        html = resp.text
    except requests.RequestException:
        return vazio

    # Descrição: prioriza og:description (pensada pra compartilhamento,
    # geralmente mais completa) sobre a meta description comum.
    descricao = None
    melhor_prioridade = -1
    for casa in _PADRAO_META_DESC.finditer(html):
        propriedade, conteudo = casa.group(1).lower(), casa.group(2).strip()
        prioridade = 1 if propriedade == "og:description" else 0
        if conteudo and prioridade >= melhor_prioridade:
            descricao = conteudo
            melhor_prioridade = prioridade

    # Logo: og:image primeiro (normalmente a arte principal da marca);
    # se não tiver, cai pro ícone do site (favicon/apple-touch-icon).
    logo_url = None
    casa_og = _PADRAO_OG_IMAGE.search(html)
    if casa_og:
        logo_url = _absolutizar(resp.url, casa_og.group(1))
    else:
        casa_icon = _PADRAO_ICON.search(html)
        if casa_icon:
            logo_url = _absolutizar(resp.url, casa_icon.group(1))

    # Instagram: primeiro link pro instagram.com encontrado na página
    # (normalmente no rodapé ou nos ícones de redes sociais).
    instagram_url = None
    casa_ig = _PADRAO_INSTAGRAM.search(html)
    if casa_ig:
        instagram_url = casa_ig.group(0)

    return {"descricao": descricao, "logo_url": logo_url, "instagram_url": instagram_url}
