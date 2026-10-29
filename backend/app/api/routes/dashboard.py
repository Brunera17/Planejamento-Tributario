import json
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import DB, UsuarioAtual
from app.models import Empresa, OportunidadeRegistro, Planejamento, Simulacao

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

RECUPERACOES = ("SEGREGACAO_MONOFASICO", "ICMS_ST_INTERNAS")


@router.get("")
def indicadores(db: DB, _: UsuarioAtual):
    planejamentos = db.scalars(select(Planejamento)).unique().all()
    faixas = {"0%": 0, "1–49%": 0, "50–99%": 0, "100%": 0}
    for p in planejamentos:
        faixa = "0%" if p.progresso == 0 else "100%" if p.progresso == 100 else "1–49%" if p.progresso < 50 else "50–99%"
        faixas[faixa] += 1

    # última simulação de cada planejamento
    ultimas = db.scalars(select(Simulacao).where(Simulacao.id.in_(
        select(func.max(Simulacao.id)).group_by(Simulacao.planejamento_id)))).all()
    economia = Decimal(0)
    desatualizadas = 0
    proximas_sublimite = 0
    for s in ultimas:
        r = json.loads(s.resultado_json)
        totais = {c["regime"]: Decimal(str(c["total"])) for c in r["comparativo"]}
        p = db.get(Planejamento, s.planejamento_id)
        atual = p.empresa.regime_tributario
        if atual in totais:  # anualiza a diferença entre o regime atual e o melhor
            economia += (totais[atual] - totais[r["melhor_regime"]]) * 12 / len(p.competencias())
        if s.desatualizada:
            desatualizadas += 1
        if any(o["codigo"] == "SUBLIMITE" for o in r["oportunidades"]):
            proximas_sublimite += 1
    recuperacao = db.scalar(select(func.coalesce(func.sum(OportunidadeRegistro.impacto), 0)).where(
        OportunidadeRegistro.codigo.in_(RECUPERACOES),
        OportunidadeRegistro.simulacao_id.in_([s.id for s in ultimas]))) or 0

    return {
        "empresas_ativas": db.scalar(select(func.count(Empresa.id)).where(Empresa.ativo)),
        "planejamentos_por_status": dict(db.execute(
            select(Planejamento.status, func.count(Planejamento.id)).group_by(Planejamento.status)).all()),
        "planejamentos_por_progresso": faixas,
        "simulacoes_desatualizadas": desatualizadas,
        "economia_anual_estimada": round(economia, 2),
        "recuperacoes_identificadas": round(Decimal(str(recuperacao)), 2),
        "empresas_proximas_sublimite": proximas_sublimite,
    }
