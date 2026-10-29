"""Executa o motor sobre um planejamento e grava a simulação (imutável e versionada)."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.erros import ErroNegocio
from app.models import (
    HistoricoStatus,
    MemoriaCalculo,
    OportunidadeRegistro,
    Planejamento,
    Simulacao,
    SimulacaoResultado,
)
from app.motor import simular
from app.services import progresso
from app.services.entrada import montar_entrada
from app.services.serializacao import hash_entrada, para_json


def executar(db: Session, p: Planejamento, usuario_id: int) -> Simulacao:
    montada = montar_entrada(db, p)
    entrada = montada.entrada
    if not entrada.itens:
        raise ErroNegocio("Importe as notas fiscais de saída antes de simular")
    try:
        r = simular(entrada)
    except ValueError as e:
        raise ErroNegocio(str(e)) from e

    pct = progresso.atualizar(db, p)
    pendencias = list(montada.pendencias)
    if pct < 100:
        pendencias.append(f"Progresso do levantamento em {pct}%")
    versao = (db.scalar(select(func.max(Simulacao.versao)).where(Simulacao.planejamento_id == p.id)) or 0) + 1

    db.execute(update(Simulacao).where(Simulacao.planejamento_id == p.id).values(desatualizada=True))
    sim = Simulacao(
        planejamento_id=p.id,
        versao=versao,
        tipo="PRELIMINAR" if pendencias else "FINAL",
        hash_entrada=hash_entrada(entrada),
        entrada_json=json.dumps({"premissas": para_json(entrada.premissas),
                                 "parametros": para_json(entrada.parametros),
                                 "faixas_simples": para_json(entrada.faixas_simples),
                                 "reforma": para_json(entrada.reforma)}, ensure_ascii=False),
        resultado_json=json.dumps(para_json(r), ensure_ascii=False),
        regime_recomendado=r.melhor_regime.value,
        pendencias="\n".join(pendencias) or None,
        executada_por=usuario_id,
    )
    db.add(sim)
    db.flush()

    linhas = []
    for reg in (r.simples, r.presumido, r.real):
        for t in reg.tributos:
            linhas.append(SimulacaoResultado(simulacao_id=sim.id, regime=reg.regime.value, ano=2026,
                                             competencia=t.competencia, tributo=t.tributo, valor=round(t.valor, 2)))
    for lr in r.reforma:
        for regime, carga in lr.cargas.items():
            linhas.append(SimulacaoResultado(simulacao_id=sim.id, regime=regime.value, ano=lr.ano,
                                             tributo="TOTAL", valor=round(carga, 2)))
    db.add_all(linhas)
    db.add_all(MemoriaCalculo(simulacao_id=sim.id, ordem=i, secao=m.secao, competencia=m.competencia,
                              descricao=m.descricao, formula=m.formula, resultado=m.valor, fundamento=m.fundamento)
               for i, m in enumerate(r.memoria.passos))
    db.add_all(OportunidadeRegistro(simulacao_id=sim.id, codigo=o.codigo, titulo=o.titulo,
                                    impacto=None if o.impacto is None else round(o.impacto, 2),
                                    prioridade=o.prioridade, acao=o.acao)
               for o in r.oportunidades)

    if p.status != "SIMULADO":
        db.add(HistoricoStatus(planejamento_id=p.id, status_de=p.status, status_para="SIMULADO",
                               usuario_id=usuario_id, motivo=f"Simulação v{versao}"))
        p.status = "SIMULADO"
    db.commit()
    return sim


def aprovar(db: Session, sim: Simulacao, usuario_id: int) -> Simulacao:
    if sim.desatualizada:
        raise ErroNegocio("Simulação desatualizada: execute uma nova simulação antes de aprovar")
    if sim.tipo != "FINAL":
        raise ErroNegocio("Somente simulações sem pendências podem ser aprovadas", campos={"pendencias": sim.pendencias or ""})
    p = db.get(Planejamento, sim.planejamento_id)
    sim.aprovada_por = usuario_id
    sim.aprovada_em = datetime.now(UTC)
    db.add(HistoricoStatus(planejamento_id=p.id, status_de=p.status, status_para="APROVADO", usuario_id=usuario_id,
                           motivo=f"Simulação v{sim.versao} aprovada"))
    p.status = "APROVADO"
    db.commit()
    return sim


def marcar_desatualizada(db: Session, planejamento_id: int) -> None:
    """Chamado sempre que um dado de entrada do planejamento muda."""
    db.execute(update(Simulacao).where(Simulacao.planejamento_id == planejamento_id).values(desatualizada=True))
