"""
Gerencia o login usado para acessar o Perfil da Empresa como
administrador (aba "Acesso Admin" do site).

Em vez de guardar seu e-mail/senha no programa — o que o Google costuma
bloquear como "login automatizado" e é bem menos seguro — a gente abre
uma janela de navegador de verdade, você faz login manualmente do jeito
normal (inclusive com verificação em duas etapas, se tiver), e o
Playwright salva só a "sessão" (os cookies) num arquivo local. As
próximas análises reaproveitam essa sessão sem precisar logar de novo.

⚠️ IMPORTANTE — SEGURANÇA:
O arquivo de sessão (core/.sessions/admin_session.json) equivale a uma
cópia da sua chave de acesso: quem tiver esse arquivo consegue entrar na
sua conta Google sem digitar senha. Ele fica só na sua máquina.
NUNCA suba esse arquivo pro GitHub nem mande pra ninguém — adicione a
linha abaixo no seu .gitignore:

    core/.sessions/
"""

from datetime import datetime
from pathlib import Path

SESSAO_DIR = Path(__file__).parent / ".sessions"
SESSAO_ARQUIVO = SESSAO_DIR / "admin_session.json"

# Manda direto pro login do Google já "pedindo" pra continuar dentro do
# painel do Perfil da Empresa depois de autenticar.
URL_LOGIN = "https://accounts.google.com/ServiceLogin?continue=https://business.google.com/locations"
URL_PAINEL = "https://business.google.com/**"


def sessao_existe() -> bool:
    return SESSAO_ARQUIVO.exists()


def data_ultima_conexao() -> str | None:
    """Data/hora em que a sessão foi salva (aproximação de 'desde
    quando' você está logado no programa)."""
    if not sessao_existe():
        return None
    ts = SESSAO_ARQUIVO.stat().st_mtime
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")


def desconectar() -> None:
    """Apaga a sessão salva — próxima análise 'como cliente' vai pedir
    login de novo."""
    if sessao_existe():
        SESSAO_ARQUIVO.unlink()


def iniciar_login(timeout_min: int = 10) -> bool:
    """Abre uma janela de navegador de verdade pra você logar manualmente
    na sua conta Google. Detecta sozinha quando o login deu certo (a
    página chegou dentro de business.google.com) e salva a sessão.

    Devolve True se salvou a sessão, False se deu timeout ou a janela
    foi fechada antes de completar o login.

    Requer o navegador do Playwright instalado uma vez, com:
        playwright install chromium
    """
    from playwright.sync_api import sync_playwright

    SESSAO_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=False)
        contexto = navegador.new_context()
        pagina = contexto.new_page()
        pagina.goto(URL_LOGIN)

        try:
            pagina.wait_for_url(URL_PAINEL, timeout=timeout_min * 60 * 1000)
            contexto.storage_state(path=str(SESSAO_ARQUIVO))
            navegador.close()
            return True
        except Exception:
            navegador.close()
            return False
