import json
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import case, func, select

from app.api.deps import DB, UsuarioAtual
from app.models import Empresa, OportunidadeRegistro, Planejamento, Simulacao

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

RECUPERACOES = ("SEGREGACAO_MONOFASICO", "ICMS_ST_INTERNAS")

# total por regime de cada simulação, lido do resultado_json. Simulação é imutável: decodifica uma vez por processo.
# shortcut: cache sem LRU, zerado ao passar de _CACHE_MAX; trocar por colunas na Simulacao se o volume crescer muito
_TOTAIS: dict[int, dict[str, Decimal]] = {}
_CACHE_MAX = 5000


def _meses(inicio: str, fim: str) -> int:
    (a1, m1), (a2, m2) = (map(int, c.split("-")) for c in (inicio, fim))
    return (a2 - a1) * 12 + m2 - m1 + 1


def _totais(db, ids: list[int]) -> dict[int, dict[str, Decimal]]:
    faltam = [i for i in ids if i not in _TOTAIS]
    if faltam:
        if len(_TOTAIS) + len(faltam) > _CACHE_MAX:
            _TOTAIS.clear()
        for sid, resultado in db.execute(select(Simulacao.id, Simulacao.resultado_json).where(Simulacao.id.in_(faltam))):
            _TOTAIS[sid] = {c["regime"]: Decimal(str(c["total"])) for c in json.loads(resultado)["comparativo"]}
    return {i: _TOTAIS[i] for i in ids}


@router.get("")
def indicadores(db: DB, _: UsuarioAtual):
    p = Planejamento.progresso
    faixa = case((p == 0, "0%"), (p == 100, "100%"), (p < 50, "1–49%"), else_="50–99%")
    faixas = {"0%": 0, "1–49%": 0, "50–99%": 0, "100%": 0}
    faixas.update(dict(db.execute(select(faixa, func.count()).group_by(faixa)).all()))

    # última simulação de cada planejamento, só com as colunas que o indicador usa
    ultimas = db.execute(
        select(Simulacao.id, Simulacao.desatualizada, Simulacao.regime_recomendado, Empresa.regime_tributario,
               Planejamento.competencia_inicial, Planejamento.competencia_final)
        .join(Planejamento, Planejamento.id == Simulacao.planejamento_id).join(Empresa)
        .where(Simulacao.id.in_(select(func.max(Simulacao.id)).group_by(Simulacao.planejamento_id)))).all()
    ids = [u.id for u in ultimas]
    totais = _totais(db, ids)
    economia = Decimal(0)
    for u in ultimas:
        t = totais[u.id]
        if u.regime_tributario in t:  # anualiza a diferença entre o regime atual e o melhor
            economia += (t[u.regime_tributario] - t[u.regime_recomendado]) * 12 / _meses(u.competencia_inicial, u.competencia_final)

    def oportunidades(*codigos):
        return OportunidadeRegistro.codigo.in_(codigos), OportunidadeRegistro.simulacao_id.in_(ids)

    recuperacao = db.scalar(select(func.coalesce(func.sum(OportunidadeRegistro.impacto), 0)).where(
        *oportunidades(*RECUPERACOES))) or 0
    proximas_sublimite = db.scalar(select(func.count(func.distinct(OportunidadeRegistro.simulacao_id))).where(
        *oportunidades("SUBLIMITE")))

    return {
        "empresas_ativas": db.scalar(select(func.count(Empresa.id)).where(Empresa.ativo)),
        "planejamentos_por_status": dict(db.execute(
            select(Planejamento.status, func.count(Planejamento.id)).group_by(Planejamento.status)).all()),
        "planejamentos_por_progresso": faixas,
        "simulacoes_desatualizadas": sum(u.desatualizada for u in ultimas),
        "economia_anual_estimada": round(economia, 2),
        "recuperacoes_identificadas": round(Decimal(str(recuperacao)), 2),
        "empresas_proximas_sublimite": proximas_sublimite,
    }
