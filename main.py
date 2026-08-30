"""
Ponto de entrada: roda a análise de um perfil a partir do terminal,
usando dados reais da SerpApi (Google Maps).

Uso:
    python main.py "Instituto Nail Studio Campinas"
    python main.py "https://maps.app.goo.gl/xxxxx"

    # Se você já conectou o acesso admin (veja core/admin_session.py /
    # a aba "Acesso Admin" no site), pode pedir a análise completa:
    python main.py --admin "Instituto Nail Studio Campinas"
"""

import os
import sys
from dotenv import load_dotenv

from core.serpapi_client import SerpApiClient
from core.engine import gerar_relatorio
from core.criteria import Nivel
from core.concorrentes import gerar_comparativo
from core.site_scraper import extrair_dados_site
from core.admin_session import sessao_existe
from core.admin_client import coletar_dados_admin
from core.instagram_client import InstagramClient

load_dotenv()  # lê o arquivo .env com a SERPAPI_KEY

_MARCADOR = {
    Nivel.BOM: "✅",
    Nivel.RAZOAVEL: "🟡",
    Nivel.FRACO: "🔴",
    Nivel.NAO_VERIFICADO: "⚪",
}


def _reforcar_com_site_oficial(dados: dict) -> None:
    """Ver docstring da mesma função em app.py — só preenche o que
    faltar (descrição/logo/instagram), lendo o site oficial do negócio,
    sem nunca sobrescrever o que já veio do Google Maps."""
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


def imprimir_relatorio(rel):
    print(f"\n{'=' * 60}")
    print(f"  {rel.nome_negocio}")
    print(f"{'=' * 60}")
    print(f"Índice: {rel.indice}/100  |  Cobertura de dados públicos: {rel.cobertura_pct}%  |  "
          f"Classificação: {rel.classificacao}\n")

    for categoria, itens in rel.resumo_por_categoria.items():
        print(f"-- {categoria} --")
        for item in itens:
            marcador = _MARCADOR[item.nivel]
            print(f"  {marcador} {item.nome}: {item.mensagem}")
        print()

    if rel.pontos_melhorar:
        print(f"-- Pontos a Melhorar ({len(rel.pontos_melhorar)}) --")
        print("  (Itens que estão puxando o índice pra baixo, em ordem de prioridade)")
        for item in rel.pontos_melhorar:
            marcador = _MARCADOR[item.nivel]
            print(f"  {marcador} {item.nome}: {item.mensagem}")
        print()
    elif rel.indice == 100:
        print("-- Pontos a Melhorar --")
        print("  Nenhum — todos os critérios verificados estão \"Bom\". 🎉\n")

    if rel.resultados_admin:
        print(f"-- Somente com acesso de administrador ({len(rel.resultados_admin)} itens) --")
        print("  (Esses critérios existem no relatório completo, mas só podem ser")
        print("   avaliados com login de administrador no Perfil da Empresa — não")
        print("   entram na cobertura acima nem contam contra o índice.)")
        for item in rel.resultados_admin:
            print(f"  ⚪ {item.nome}")
        print()

    if rel.concorrencia:
        c = rel.concorrencia
        print(f"-- Comparativo com Concorrentes da Região ({len(c.concorrentes)} encontrados) --")
        if c.posicao:
            total = len(c.concorrentes) + 1
            print(f"  Posição estimada: {c.posicao}º de {total} (por índice)")
        print(f"  Média do mercado local — Índice: {c.media_mercado_indice}  |  "
              f"Nota: {c.media_mercado_nota}  |  Avaliações: {c.media_mercado_avaliacoes}")
        print(f"  Este negócio — Índice: {rel.indice}  |  Nota: {c.nota_negocio}  |  "
              f"Avaliações: {c.avaliacoes_negocio}")
        print()
        for conc in c.concorrentes:
            print(f"  • {conc.nome} — Índice: {conc.indice}  |  Nota: {conc.nota_media}  |  "
                  f"Avaliações: {conc.total_avaliacoes}")
        print()
    else:
        print("-- Comparativo com Concorrentes da Região --")
        print("  Não foi possível montar o comparativo (sem categoria/cidade suficiente")
        print("  nos dados públicos, ou nenhum concorrente encontrado na busca).\n")


def main():
    argumentos = sys.argv[1:]
    usar_admin = "--admin" in argumentos
    if usar_admin:
        argumentos = [a for a in argumentos if a != "--admin"]

    if len(argumentos) < 1:
        print('Uso: python main.py "Nome do negócio + cidade"  (ou cole um link do Maps)')
        print('     python main.py --admin "Nome do negócio"   (usa o acesso admin já conectado)')
        sys.exit(1)

    entrada = " ".join(argumentos)
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        print("Defina SERPAPI_KEY no arquivo .env antes de rodar.")
        sys.exit(1)

    if usar_admin and not sessao_existe():
        print("--admin foi pedido, mas não há sessão conectada ainda.")
        print("Conecte primeiro pela aba \"Acesso Admin\" no site (python app.py).")
        sys.exit(1)

    client = SerpApiClient(api_key)
    dados = client.buscar_e_analisar(entrada)

    if not dados:
        print(f"Não encontrei nenhum perfil para: {entrada}")
        sys.exit(1)

    if usar_admin:
        extras = coletar_dados_admin(dados.get("nome") or entrada)
        dados.update(extras)

    _reforcar_com_site_oficial(dados)

    dados["instagram"] = InstagramClient(api_key).analisar(dados.get("nome") or entrada, instagram_url=dados.get("instagram_url"))
    if not dados.get("logo_url") and dados.get("instagram", {}).get("encontrado"):
        dados["logo_url"] = dados["instagram"].get("foto_perfil")
    dados["tem_logotipo"] = bool(dados.get("logo_url"))

    relatorio = gerar_relatorio(dados, modo="cliente" if usar_admin else "prospeccao")
    relatorio.concorrencia = gerar_comparativo(client, dados)
    imprimir_relatorio(relatorio)
    ig = dados.get("instagram") or {}
    print("-- Instagram --")
    if ig.get("encontrado"):
        print(f"  @{ig.get('username')} · {ig.get('seguidores')} seguidores · {ig.get('publicacoes_total')} publicações")
        print(f"  Bio: {ig.get('bio') or 'Sem bio pública'}")
        print(f"  Profissional: {ig.get('conta_profissional')} · Empresa: {ig.get('conta_empresa')} · Verificado: {ig.get('verificado')}")
    else:
        print(f"  {ig.get('mensagem', 'Nenhum perfil confirmado.')}")


if __name__ == "__main__":
    main()
