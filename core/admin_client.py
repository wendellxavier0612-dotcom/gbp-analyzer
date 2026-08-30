"""
Coleta os critérios que só existem com acesso de administrador (os
mesmos marcados como Acesso.ADMIN em core/criteria.py), navegando pelo
painel do Perfil da Empresa (business.google.com) com a sessão salva por
core/admin_session.py.

⚠️ AVISO HONESTO SOBRE ESTE ARQUIVO:
Diferente do resto do programa (que usa a API pública da SerpApi, com
formato de resposta estável e documentado), o painel business.google.com
é uma aplicação sem API pública pra isso — o layout muda com frequência
e os nomes internos dos elementos não são previsíveis sem abrir a tela
de verdade e inspecionar. Eu não tenho como abrir seu painel logado
daqui, então não consigo garantir de antemão os seletores exatos.

O que já está pronto e funciona: abrir o navegador com a sessão salva e
chegar até o negócio certo. O que falta (marcado com TODO abaixo): o
"onde clicar/ler" de cada campo específico.

Fluxo recomendado pra fechar isso com precisão:
1. Rode uma análise "como cliente" uma vez — a janela abre visível
   (headless=False), então dá pra ver o painel em tempo real.
2. Clique com o botão direito no campo que quer capturar (ex: a data de
   fundação, o horário especial) → "Inspecionar" → copia o HTML daquele
   trecho.
3. Me manda esse HTML (ou um print) que eu escrevo o seletor certo.

Cada campo que não for preenchido aqui simplesmente continua aparecendo
como "Não verificado" no relatório — nunca inventa um valor errado.
"""

from core.admin_session import SESSAO_ARQUIVO, sessao_existe

URL_LISTA_LOCAIS = "https://business.google.com/locations"


def coletar_dados_admin(nome_negocio: str) -> dict:
    """Devolve um dict só com os campos extras que exigem admin (mesmas
    chaves usadas em core/criteria.py, ex: 'data_fundacao',
    'horario_especial', 'reviews_sem_comentario' etc.). Chaves que não
    conseguirmos confirmar ficam de fora do dict."""
    if not sessao_existe():
        return {}

    from playwright.sync_api import sync_playwright

    extras: dict = {}

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=False)
        contexto = navegador.new_context(storage_state=str(SESSAO_ARQUIVO))
        pagina = contexto.new_page()
        pagina.goto(URL_LISTA_LOCAIS)

        # TODO: localizar, dentro da lista de negócios que você
        # administra, o card com o nome certo. Hoje só filtra por texto
        # visível na tela — se você administra vários locais com nomes
        # parecidos, vale conferir o endereço também antes de clicar.
        try:
            pagina.get_by_text(nome_negocio, exact=False).first.click(timeout=15000)
            pagina.wait_for_timeout(2000)
        except Exception:
            navegador.close()
            return extras

        # A partir daqui, cada bloco tenta um critério ADMIN de
        # core/criteria.py. Todos comentados até termos os seletores
        # reais (ver aviso no topo do arquivo).

        # extras["data_fundacao"] = ...          # aba "Informações" > "Sobre"
        # extras["horario_especial"] = ...       # aba "Informações" > "Horário especial"
        # extras["reviews_sem_comentario"] = ...  # aba "Avaliações", filtrar sem texto
        # extras["reviews_sem_resposta"] = ...    # aba "Avaliações", filtrar sem resposta sua
        # extras["tendencia_reviews"] = ...       # aba "Avaliações" > gráfico de tendência
        # extras["atividade_dono"] = ...          # aba "Postagens"/"Fotos", data do último envio seu
        # extras["midia_dono"] = ...              # aba "Fotos", filtro "Adicionadas por você"
        # extras["midia_clientes"] = ...          # aba "Fotos", filtro "Adicionadas por clientes"

        navegador.close()

    return extras
