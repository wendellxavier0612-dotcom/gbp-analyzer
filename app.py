"""
Interface web do GBP Analyzer.

Roda um servidor local (Flask) com um formulário de busca; ao enviar,
consulta a SerpApi e mostra o relatório completo estilizado no navegador
— mesma lógica de análise do main.py (terminal), só que com uma cara
melhor pra apresentar pra cliente/prospect.

Uso:
    python app.py
    (depois abra http://127.0.0.1:5000 no navegador)
"""

import os
from dataclasses import asdict

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for

from core.serpapi_client import SerpApiClient
from core.engine import gerar_relatorio
from core.criteria import Nivel
from core.concorrentes import gerar_comparativo
from core.site_scraper import extrair_dados_site
from core.admin_session import (
    sessao_existe, data_ultima_conexao, desconectar, iniciar_login,
    NavegadorIndisponivelError,
)
from core.admin_client import coletar_dados_admin
from core.instagram_client import InstagramClient

load_dotenv()

app = Flask(__name__)

# ---------------------------------------------------------------------
# Mapas usados só pela camada de apresentação (não mexem na lógica de
# análise, que continua 100% em core/).
# ---------------------------------------------------------------------
NIVEL_CSS = {
    Nivel.BOM: "bom",
    Nivel.RAZOAVEL: "razoavel",
    Nivel.FRACO: "fraco",
    Nivel.NAO_VERIFICADO: "nv",
}
NIVEL_ICON = {
    Nivel.BOM: "✓",
    Nivel.RAZOAVEL: "!",
    Nivel.FRACO: "✕",
    Nivel.NAO_VERIFICADO: "·",
}
CLS_CSS = {
    "Forte": "cls-forte",
    "Bom": "cls-bom",
    "Razoável": "cls-razoavel",
    "Fraco": "cls-fraco",
}
GAUGE_COR = {
    "Forte": "#34D399",
    "Bom": "#22D3C7",
    "Razoável": "#FBBF24",
    "Fraco": "#FB7185",
}


def _cidade_do_endereco(endereco):
    if not endereco:
        return None
    partes = [p.strip() for p in endereco.split(",")]
    for parte in reversed(partes):
        if " - " in parte:
            return parte.split(" - ")[0].strip()
    return partes[-2] if len(partes) >= 2 else None


def _reforcar_com_site_oficial(dados: dict) -> None:
    """Quando o Google Maps não trouxe descrição, logo ou instagram, mas
    o negócio tem um website vinculado, dá uma segunda chance lendo a
    home page do próprio site — é exatamente onde essas informações
    costumam estar 'escancaradas', só que fora do alcance da busca do
    Maps. Só preenche o que estiver faltando; nunca sobrescreve dado que
    já veio do Google."""
    website = dados.get("website")
    falta_algo = not dados.get("descricao") or not dados.get("logo_url") or not dados.get("instagram_url")
    if not website or not falta_algo:
        return

    extra = extrair_dados_site(website)
    if not dados.get("descricao") and extra.get("descricao"):
        dados["descricao"] = extra["descricao"]
    if not dados.get("logo_url") and extra.get("logo_url"):
        dados["logo_url"] = extra["logo_url"]
    if not dados.get("instagram_url") and extra.get("instagram_url"):
        dados["instagram_url"] = extra["instagram_url"]


def _analisar_instagram(dados, api_key):
    try:
        ig = InstagramClient(api_key)
        instagram_url = dados.get("instagram_url")
        cidade = _cidade_do_endereco(dados.get("endereco"))
        return ig.analisar(dados.get("nome") or "", cidade=cidade, instagram_url=instagram_url)
    except Exception as exc:
        return {"encontrado": False, "status": "erro_consulta", "mensagem": f"Não foi possível consultar o Instagram: {exc}"}


def _score_instagram(ig):
    if not ig.get("encontrado"):
        return None
    checks = [
        bool(ig.get("bio")),
        bool(ig.get("foto_perfil")),
        ig.get("conta_profissional") is True or ig.get("conta_empresa") is True,
        bool(ig.get("publicacoes_total") or 0),
        bool(ig.get("seguidores") is not None),
        bool(ig.get("tem_reels")),
    ]
    return int(sum(checks)/len(checks)*100)


def _montar_ranking_concorrencia(rel, comparativo):
    """Combina o negócio analisado + concorrentes numa lista única,
    ordenada por índice, pronta pra desenhar as barras no template."""
    if not comparativo:
        return []
    linhas = [{
        "nome": rel.nome_negocio,
        "indice": rel.indice,
        "nota": comparativo.nota_negocio,
        "avaliacoes": comparativo.avaliacoes_negocio,
        "voce": True,
    }]
    for c in comparativo.concorrentes:
        linhas.append({
            "nome": c.nome,
            "indice": c.indice,
            "nota": c.nota_media,
            "avaliacoes": c.total_avaliacoes,
            "voce": False,
        })
    linhas.sort(key=lambda l: l["indice"], reverse=True)
    return linhas


@app.route("/", methods=["GET", "POST"])
def index():
    contexto = {
        "busca": "",
        "rel": None,
        "dados": None,
        "ranking": [],
        "erro": None,
        "NIVEL_CSS": NIVEL_CSS,
        "NIVEL_ICON": NIVEL_ICON,
        "CLS_CSS": CLS_CSS,
        "GAUGE_COR": GAUGE_COR,
        "admin_conectado": sessao_existe(),
        "usar_admin_marcado": False,
    }

    if request.method == "POST":
        busca = (request.form.get("busca") or "").strip()
        contexto["busca"] = busca

        # Só é possível marcar "analisar como cliente" se houver sessão
        # admin salva — mesmo que o campo venha marcado no POST, ignoramos
        # se a sessão não existir (evita erro estranho no meio da busca).
        usar_admin = request.form.get("usar_admin") == "on" and sessao_existe()
        contexto["usar_admin_marcado"] = usar_admin

        api_key = os.getenv("SERPAPI_KEY")
        if not api_key:
            contexto["erro"] = "SERPAPI_KEY não configurada no arquivo .env."
        elif not busca:
            contexto["erro"] = "Digite o nome do negócio, a cidade, ou cole o link do perfil no Google Maps."
        else:
            try:
                client = SerpApiClient(api_key)
                dados = client.buscar_e_analisar(busca)
                if not dados:
                    contexto["erro"] = f'Não encontrei nenhum perfil para "{busca}".'
                else:
                    if usar_admin:
                        extras = coletar_dados_admin(dados.get("nome") or busca)
                        dados.update(extras)

                    # Reforço com o site oficial ANTES do Instagram: se o
                    # site tiver o link do perfil, isso melhora bastante a
                    # chance da busca de Instagram acertar de primeira.
                    _reforcar_com_site_oficial(dados)

                    dados["instagram"] = _analisar_instagram(dados, api_key)
                    # O avatar do Instagram é usado como fallback de logo somente
                    # quando nenhuma imagem de logo já foi identificada (nem pelo
                    # Google, nem pelo site oficial).
                    if not dados.get("logo_url") and dados.get("instagram", {}).get("encontrado"):
                        dados["logo_url"] = dados["instagram"].get("foto_perfil")
                    dados["instagram"]["score"] = _score_instagram(dados["instagram"])

                    # Antes esse critério nunca era preenchido mesmo quando a
                    # gente já tinha achado uma logo (bug); agora reflete o
                    # que foi realmente encontrado, seja qual for a fonte.
                    dados["tem_logotipo"] = bool(dados.get("logo_url"))

                    modo = "cliente" if usar_admin else "prospeccao"
                    rel = gerar_relatorio(dados, modo=modo)
                    rel.concorrencia = gerar_comparativo(client, dados)
                    contexto["rel"] = rel
                    contexto["dados"] = dados
                    contexto["ranking"] = _montar_ranking_concorrencia(rel, rel.concorrencia)
            except Exception as exc:  # noqa: BLE001 — mostra erro amigável em vez de 500
                contexto["erro"] = f"Erro ao consultar a SerpApi: {exc}"

    return render_template("index.html", **contexto)


# ---------------------------------------------------------------------
# Aba de Acesso Admin — conectar/desconectar a sessão de login usada
# pra analisar perfis de clientes com dados completos (ver core/admin_*).
# ---------------------------------------------------------------------
@app.route("/admin", methods=["GET"])
def admin():
    return render_template(
        "admin.html",
        conectado=sessao_existe(),
        ultima_conexao=data_ultima_conexao(),
        erro=None,
    )


@app.route("/admin/conectar", methods=["POST"])
def admin_conectar():
    try:
        ok = iniciar_login()
    except NavegadorIndisponivelError as exc:
        return render_template(
            "admin.html",
            conectado=sessao_existe(),
            ultima_conexao=data_ultima_conexao(),
            erro=str(exc),
        )
    if not ok:
        return render_template(
            "admin.html",
            conectado=sessao_existe(),
            ultima_conexao=data_ultima_conexao(),
            erro="Não deu pra confirmar o login (a janela foi fechada antes de terminar, "
                 "ou passou do tempo limite). Clique em conectar e tenta de novo.",
        )
    return redirect(url_for("admin"))


@app.route("/admin/desconectar", methods=["POST"])
def admin_desconectar():
    desconectar()
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=True)
