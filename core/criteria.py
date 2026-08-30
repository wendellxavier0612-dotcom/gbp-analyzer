from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

class Nivel(str, Enum):
    FRACO = "Fraco"
    RAZOAVEL = "Razoável"
    BOM = "Bom"
    NAO_VERIFICADO = "Não verificado"

class Acesso(str, Enum):
    PUBLICO = "publico"
    ADMIN = "admin"
    PARCIAL = "parcial"

@dataclass
class ResultadoCriterio:
    chave: str
    nome: str
    categoria: str
    nivel: Nivel
    percentual: int
    mensagem: str
    acesso: Acesso = Acesso.PUBLICO

@dataclass
class Criterio:
    chave: str
    nome: str
    categoria: str
    acesso: Acesso
    explicacao: str
    avaliar: Callable[[dict], Optional[ResultadoCriterio]]
    def rodar(self, dados: dict) -> ResultadoCriterio:
        resultado = self.avaliar(dados)
        if resultado is None:
            # Mensagem diferente conforme o MOTIVO de não ter dado: item que
            # exige login de administrador, item que nenhuma fonte pública
            # expõe hoje (parcial), ou item público que só não veio nesta
            # busca específica (site fora do ar, perfil incompleto etc.).
            if self.acesso == Acesso.ADMIN:
                msg = "Este item só pode ser avaliado com acesso de administrador ao Perfil da Empresa."
            elif self.acesso == Acesso.PARCIAL:
                msg = "Não é possível confirmar este item com as fontes públicas atuais (o Google não expõe esse dado via busca)."
            else:
                msg = "Não foi possível verificar este item com os dados disponíveis nesta busca."
            return ResultadoCriterio(self.chave, self.nome, self.categoria, Nivel.NAO_VERIFICADO, 0, msg, self.acesso)
        resultado.acesso = self.acesso
        return resultado

def _nivel_por_faixa(valor: int, min_razoavel: int, min_bom: int) -> Nivel:
    return Nivel.BOM if valor >= min_bom else Nivel.RAZOAVEL if valor >= min_razoavel else Nivel.FRACO

def _sim(tem, chave, nome, cat, ok, nok, acesso=Acesso.PUBLICO):
    return ResultadoCriterio(chave, nome, cat, Nivel.BOM if tem else Nivel.FRACO, 100 if tem else 0, ok if tem else nok, acesso)

def _avaliar_nome(d):
    nome=d.get("nome") or ""; bom=0 < len(nome) <= 98
    return _sim(bom,"nome_negocio","Nome do Negócio","Identidade",f"Nome com {len(nome)} caracteres (máximo recomendado: 98).","Nome não encontrado no resultado.")
def _avaliar_telefone(d): return _sim(bool(d.get("telefone")),"telefone","Número de Telefone","Identidade","Telefone definido.","Nenhum telefone encontrado no perfil.")
def _avaliar_website(d): return _sim(bool(d.get("website")),"website","Website","Identidade","Endereço do site definido.","Nenhum website vinculado ao perfil.")
def _avaliar_categoria(d):
    cats=d.get("categorias") or []; return ResultadoCriterio("categoria","Categoria Principal e Adicionais","Identidade",Nivel.BOM if cats else Nivel.FRACO,100 if cats else 0,f"{len(cats)} categoria(s) identificada(s)." if cats else "Nenhuma categoria identificada.")
def _avaliar_servicos(d):
    v=d.get("servicos")
    if v is None:return None
    # v aqui é uma lista de ATRIBUTOS públicos do perfil (ex: "Takeaway",
    # "Delivery"), não a lista de serviços com nome/preço que o dono
    # cadastra no painel — essa não é exposta em nenhuma fonte pública.
    msg=(f"{len(v)} atributo(s) de serviço identificado(s) publicamente ({', '.join(v)}). "
         f"A lista completa cadastrada no painel (com nome e preço) só é visível com acesso de administrador.") if v else \
        "Nenhum atributo de serviço público identificado."
    return ResultadoCriterio("servicos","Serviços Cadastrados","Identidade",Nivel.BOM if len(v)>=3 else Nivel.RAZOAVEL if v else Nivel.FRACO,min(100,int(len(v)/3*100)),msg)
def _avaliar_data_fundacao(d):
    v=d.get("data_fundacao")
    if v is None:return None
    return ResultadoCriterio("data_fundacao","Data de Fundação","Identidade",Nivel.BOM,100,f"Data de fundação identificada: {v}.")
def _avaliar_horario(d): return _sim(bool(d.get("horario_funcionamento")),"horario_funcionamento","Horário de Funcionamento","Horários","Horário de funcionamento definido.","Horário de funcionamento não encontrado.")
def _avaliar_horario_especial(d):
    v=d.get("horario_especial")
    if v is None:return None
    return ResultadoCriterio("horario_especial","Horário Especial (feriados)","Horários",Nivel.BOM if v else Nivel.FRACO,100 if v else 0,"Horário especial definido." if v else "Nenhum horário especial informado pela empresa.")
def _avaliar_descricao(d):
    v=d.get("descricao")
    if v is None:return None
    n=len(v); nivel=Nivel.BOM if n>=50 else Nivel.FRACO
    return ResultadoCriterio("descricao","Descrição da Empresa","Descrição",nivel,100 if nivel==Nivel.BOM else 0,f"Descrição oficial encontrada com {n} caracteres.")
def _avaliar_qtd_reviews(d):
    q=d.get("total_avaliacoes") or 0; nivel=_nivel_por_faixa(q,3,10)
    return ResultadoCriterio("qtd_avaliacoes","Quantidade de Avaliações","Avaliações",nivel,min(100,int(q/10*100)) if q else 0,f"{q} avaliação(ões) encontradas.")
def _avaliar_media_reviews(d):
    m=d.get("nota_media") or 0; nivel=Nivel.BOM if m>=4.3 else Nivel.RAZOAVEL if m>=3.5 else Nivel.FRACO
    return ResultadoCriterio("media_avaliacoes","Média de Avaliações","Avaliações",nivel,int(m/5*100),f"Nota média atual: {m}.")
def _avaliar_reviews_sem_comentario(d):
    n=d.get("reviews_amostra_qtd"); v=d.get("reviews_sem_comentario")
    if n is None or v is None:return None
    pct=(v/n*100) if n else 0; nivel=Nivel.BOM if pct<=10 else Nivel.RAZOAVEL if pct<=25 else Nivel.FRACO
    return ResultadoCriterio("reviews_sem_comentario","Avaliações Sem Comentário","Avaliações",nivel,100-int(min(100,pct)),f"{v} de {n} avaliações coletadas estão sem comentário.")
def _avaliar_reviews_sem_resposta(d):
    n=d.get("reviews_amostra_qtd"); v=d.get("reviews_sem_resposta")
    if n is None or v is None:return None
    pct=(v/n*100) if n else 0; nivel=Nivel.BOM if pct<=20 else Nivel.RAZOAVEL if pct<=50 else Nivel.FRACO
    return ResultadoCriterio("reviews_sem_resposta","Avaliações Sem Resposta","Avaliações",nivel,100-int(min(100,pct)),f"{v} de {n} avaliações coletadas estão sem resposta do negócio.")
def _avaliar_tendencia_reviews(d):
    datas=d.get("tendencia_reviews_datas") or []
    if len(datas)<3:return None
    return ResultadoCriterio("tendencia_reviews","Tendência de Avaliações","Avaliações",Nivel.BOM,100,f"Há histórico público suficiente ({len(datas)} datas coletadas) para acompanhar a tendência.")
def _avaliar_atividade_dono(d):
    p=d.get("posts_google")
    if p is None:return None
    return ResultadoCriterio("atividade_dono","Atividade Recente do Proprietário","Atividade",Nivel.BOM if p else Nivel.FRACO,100 if p else 0,f"{len(p)} postagem(ns) pública(s) do proprietário encontradas." if p else "Nenhuma postagem pública do proprietário encontrada na coleta.")
def _avaliar_qtd_midia(d):
    total=d.get("total_midia")
    if total is None:return None
    nivel=_nivel_por_faixa(total,3,8)
    return ResultadoCriterio("qtd_midia","Quantidade Total de Mídia","Mídia",nivel,min(100,int(total/8*100)) if total else 0,f"{total} mídia(s) coletada(s), separadas entre fotos e vídeos.")
def _avaliar_foto_capa(d): return _sim(bool(d.get("tem_foto_capa")),"foto_capa","Foto de Capa","Mídia","Foto de capa identificada.","Não foi identificada foto de capa.")
def _avaliar_logotipo(d):
    # A fonte pode ser o próprio perfil, o site oficial (og:image/favicon)
    # ou uma foto de perfil social confirmada — nessa ordem de prioridade.
    v=d.get("logo_url") or d.get("instagram",{}).get("foto_perfil")
    if not v:return None
    return ResultadoCriterio("logotipo","Logotipo / Imagem de Perfil","Mídia",Nivel.BOM,100,"Imagem de perfil/logo identificada e disponível.",Acesso.PARCIAL)
def _avaliar_videos(d):
    q=d.get("total_videos")
    if q is None:return None
    return ResultadoCriterio("videos","Vídeos no Perfil","Mídia",Nivel.BOM if q>=1 else Nivel.FRACO,100 if q else 0,f"{q} vídeo(s) encontrados no perfil.")
def _avaliar_midia_dono(d):
    q=d.get("midia_dono")
    if q is None:return None
    return ResultadoCriterio("midia_dono","Mídia Publicada pelo Proprietário","Mídia",Nivel.BOM if q else Nivel.FRACO,100 if q else 0,f"{len(q)} mídia(s) identificada(s) na categoria 'By owner'.")
def _avaliar_midia_clientes(d):
    q=d.get("midia_clientes")
    if q is None:return None
    return ResultadoCriterio("midia_clientes","Mídia Publicada por Clientes","Mídia",Nivel.BOM if q else Nivel.RAZOAVEL,100 if q else 50,f"{len(q)} mídia(s) fora da categoria do proprietário foram coletadas.")

CRITERIOS=[
Criterio("nome_negocio","Nome do Negócio","Identidade",Acesso.PUBLICO,"",_avaliar_nome),
Criterio("telefone","Número de Telefone","Identidade",Acesso.PUBLICO,"",_avaliar_telefone),
Criterio("website","Website","Identidade",Acesso.PUBLICO,"",_avaliar_website),
Criterio("categoria","Categoria Principal e Adicionais","Identidade",Acesso.PUBLICO,"",_avaliar_categoria),
Criterio("servicos","Serviços Cadastrados","Identidade",Acesso.PARCIAL,"",_avaliar_servicos),
Criterio("data_fundacao","Data de Fundação","Identidade",Acesso.ADMIN,"",_avaliar_data_fundacao),
Criterio("horario_funcionamento","Horário de Funcionamento","Horários",Acesso.PUBLICO,"",_avaliar_horario),
Criterio("horario_especial","Horário Especial (feriados)","Horários",Acesso.PARCIAL,"",_avaliar_horario_especial),
Criterio("descricao","Descrição da Empresa","Descrição",Acesso.PUBLICO,"",_avaliar_descricao),
Criterio("qtd_avaliacoes","Quantidade de Avaliações","Avaliações",Acesso.PUBLICO,"",_avaliar_qtd_reviews),
Criterio("media_avaliacoes","Média de Avaliações","Avaliações",Acesso.PUBLICO,"",_avaliar_media_reviews),
Criterio("reviews_sem_comentario","Avaliações Sem Comentário","Avaliações",Acesso.PUBLICO,"",_avaliar_reviews_sem_comentario),
Criterio("reviews_sem_resposta","Avaliações Sem Resposta","Avaliações",Acesso.PUBLICO,"",_avaliar_reviews_sem_resposta),
Criterio("tendencia_reviews","Tendência de Avaliações","Avaliações",Acesso.PUBLICO,"",_avaliar_tendencia_reviews),
Criterio("atividade_dono","Atividade Recente do Proprietário","Atividade",Acesso.PUBLICO,"",_avaliar_atividade_dono),
Criterio("qtd_midia","Quantidade Total de Mídia","Mídia",Acesso.PUBLICO,"",_avaliar_qtd_midia),
Criterio("foto_capa","Foto de Capa","Mídia",Acesso.PARCIAL,"",_avaliar_foto_capa),
Criterio("logotipo","Logotipo / Imagem de Perfil","Mídia",Acesso.PARCIAL,"",_avaliar_logotipo),
Criterio("videos","Vídeos no Perfil","Mídia",Acesso.PUBLICO,"",_avaliar_videos),
Criterio("midia_dono","Mídia Publicada pelo Proprietário","Mídia",Acesso.PUBLICO,"",_avaliar_midia_dono),
Criterio("midia_clientes","Mídia Publicada por Clientes","Mídia",Acesso.PUBLICO,"",_avaliar_midia_clientes),
]
