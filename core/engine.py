from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional
from core.criteria import CRITERIOS, Nivel, Acesso, ResultadoCriterio

@dataclass
class Concorrente:
    nome: str
    indice: int
    nota_media: float
    total_avaliacoes: int
    total_fotos: Optional[int] = None

@dataclass
class ComparativoConcorrencia:
    concorrentes: list
    posicao: Optional[int]
    media_mercado_indice: Optional[float] = None
    media_mercado_nota: Optional[float] = None
    media_mercado_avaliacoes: Optional[float] = None
    nota_negocio: Optional[float] = None
    avaliacoes_negocio: Optional[int] = None

@dataclass
class Relatorio:
    nome_negocio: str
    modo: str
    gerado_em: str
    indice: int
    cobertura_pct: int
    classificacao: str
    resultados: list
    resultados_admin: list
    resumo_por_categoria: dict
    pontos_melhorar: list = field(default_factory=list)
    concorrencia: Optional[ComparativoConcorrencia] = None

    def to_dict(self):
        d = asdict(self)
        for key in ("resultados", "resultados_admin", "pontos_melhorar"):
            d[key] = [{**asdict(r), "nivel": r.nivel.value, "acesso": r.acesso.value} for r in getattr(self, key)]
        return d

_PESO_NIVEL = {Nivel.BOM:100, Nivel.RAZOAVEL:50, Nivel.FRACO:0}

def _classificar(indice: int) -> str:
    if indice >= 80:return "Forte"
    if indice >= 60:return "Bom"
    if indice >= 40:return "Razoável"
    return "Fraco"

def gerar_relatorio(dados: dict, modo: str = "prospeccao") -> Relatorio:
    todos = [c.rodar(dados) for c in CRITERIOS]
    publicos = [r for r in todos if r.acesso != Acesso.ADMIN]
    admin = [r for r in todos if r.acesso == Acesso.ADMIN]
    verificados = [r for r in publicos if r.nivel != Nivel.NAO_VERIFICADO]
    cobertura = int(len(verificados)/len(publicos)*100) if publicos else 0
    indice = int(sum(_PESO_NIVEL[r.nivel] for r in verificados)/len(verificados)) if verificados else 0
    resumo = {}
    for r in publicos: resumo.setdefault(r.categoria, []).append(r)
    prioridade = {Nivel.FRACO:0, Nivel.RAZOAVEL:1}
    pontos = sorted((r for r in publicos if r.nivel in prioridade), key=lambda r:prioridade[r.nivel])
    return Relatorio(dados.get("nome") or "Perfil sem nome", modo, datetime.now().strftime("%d/%m/%Y %H:%M"), indice, cobertura, _classificar(indice), publicos, admin, resumo, pontos)

def calcular_indice_simples(dados: dict) -> int:
    rs=[c.rodar(dados) for c in CRITERIOS if c.acesso != Acesso.ADMIN]
    rs=[r for r in rs if r.nivel != Nivel.NAO_VERIFICADO]
    return int(sum(_PESO_NIVEL[r.nivel] for r in rs)/len(rs)) if rs else 0
