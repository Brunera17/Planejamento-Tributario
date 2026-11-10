"""Retenção das notas fiscais: na aprovação, as notas e os itens são apagados (são o grosso do banco).

Antes de apagar, o que a tela mostra a partir das notas (premissas automáticas, composição das compras, indício de
ST, resumo das saídas e crédito do estoque que saiu da ST) é gravado como retrato na simulação aprovada. Enquanto o
planejamento estiver aprovado, a tela lê o retrato. Reaberto, volta a calcular das notas, que precisam ser importadas
de novo.
"""
from __future__ import annotations

import json

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import NotaFiscal, NotaItem, Planejamento, Simulacao
from app.services import estoque_st, premissas_auto
from app.services.serializacao import para_json

CHAVE = "das_notas"  # chave do retrato dentro de simulacao.entrada_json


def _coleta(db: Session, p: Planejamento) -> dict:
    auto = premissas_auto.derivar(db, p)
    return {
        # valores tirados das notas: valem enquanto o contador não informar outro
        "premissas_auto": {k: {"valor": d.valor, "fonte": d.fonte} for k, d in auto.premissas.items()},
        "composicao_auto": auto.composicao and {
            "linhas": [{"aliquota": a, "percentual": v} for a, v in sorted(auto.composicao.items(), reverse=True)],
            "fonte": auto.fonte_composicao,
        },
        "indicio_st": auto.indicio_st,
        "saidas": [{"competencia": c, "notas": n, "itens": i, "valor": v} for c, n, i, v in db.execute(
            select(NotaFiscal.competencia, func.count(func.distinct(NotaFiscal.id)), func.count(NotaItem.id),
                   func.sum(NotaItem.vl_total))
            .join(NotaItem, NotaItem.nota_fiscal_id == NotaFiscal.id)
            .where(NotaFiscal.planejamento_id == p.id, NotaFiscal.tipo == "SAIDA")
            .group_by(NotaFiscal.competencia).order_by(NotaFiscal.competencia))],
    }


def _estoque_st(db: Session, p: Planejamento) -> dict | None:
    e = estoque_st.calcular(db, p)
    if e is None:
        return None
    return {
        "corte": e.corte, "norma": e.norma, "segmentos": e.segmentos, "ncms": e.ncms, "regime_rpa": e.regime_rpa,
        "estoque": e.estoque, "taxa": e.taxa, "credito": e.credito, "inicio_uso": e.inicio_uso, "sem_base": e.sem_base,
        "parcelas": [{"competencia": c, "valor": v} for c, v in e.parcelas()],
        "entradas": [vars(x) for x in sorted(e.entradas, key=lambda x: x.data, reverse=True)],
        "fundamento": estoque_st.FUNDAMENTO,
    }


PARTES = {"coleta": _coleta, "estoque_st": _estoque_st}


def _retrato(db: Session, p: Planejamento) -> dict | None:
    if p.status != "APROVADO":
        return None
    entrada = db.scalar(select(Simulacao.entrada_json).where(Simulacao.planejamento_id == p.id,
                                                             Simulacao.aprovada_em.is_not(None))
                        .order_by(Simulacao.versao.desc()).limit(1))
    # aprovado antes da retenção: as notas ainda existem e o cálculo ao vivo vale
    return json.loads(entrada).get(CHAVE) if entrada else None


def ler(db: Session, p: Planejamento, parte: str) -> dict | None:
    """O retrato gravado na aprovação, ou o cálculo a partir das notas."""
    retrato = _retrato(db, p)
    return retrato[parte] if retrato is not None else PARTES[parte](db, p)


def apagar_notas(db: Session, sim: Simulacao) -> tuple[int, int]:
    """Grava o retrato na simulação aprovada e apaga as notas e os itens do planejamento."""
    p = db.get(Planejamento, sim.planejamento_id)
    retrato = {parte: calcular(db, p) for parte, calcular in PARTES.items()}
    entrada = json.loads(sim.entrada_json)
    # para_json deixa os números como na resposta da API; as datas viram texto ISO, como no JSON da API
    entrada[CHAVE] = json.loads(json.dumps(para_json(retrato), default=str))
    sim.entrada_json = json.dumps(entrada, ensure_ascii=False)

    ids = select(NotaFiscal.id).where(NotaFiscal.planejamento_id == p.id).scalar_subquery()
    itens = db.execute(delete(NotaItem).where(NotaItem.nota_fiscal_id.in_(ids))).rowcount
    notas = db.execute(delete(NotaFiscal).where(NotaFiscal.planejamento_id == p.id)).rowcount
    return notas, itens
