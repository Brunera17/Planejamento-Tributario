"""Progresso do planejamento (0–100%) e lista de pendências por bloco.

Progresso = Σ (peso do bloco × itens preenchidos ÷ itens esperados), arredondado para baixo:
só mostra 100% quando nada falta.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Bem,
    CompraMensal,
    Documento,
    FolhaMensal,
    GrupoDespesa,
    ItemDespesa,
    Levantamento,
    LevantamentoGrupo,
    LevantamentoItem,
    NcmRegra,
    NotaFiscal,
    NotaItem,
    PesoProgresso,
    Planejamento,
    TipoDocumento,
)

PESOS_PADRAO = {
    "SAIDAS": 20, "DESPESAS": 20, "COMPRAS": 15, "NCM": 10, "FOLHA": 10,
    "DOCUMENTOS": 10, "OUTRAS_DESPESAS": 5, "BENS": 5, "OBSERVACOES": 5,
}
NOMES = {
    "SAIDAS": "Saídas (faturamento)", "DESPESAS": "Despesas", "COMPRAS": "Compras", "NCM": "Classificação de NCM",
    "FOLHA": "Folha e pró-labore", "DOCUMENTOS": "Documentos", "OUTRAS_DESPESAS": "Outras despesas",
    "BENS": "Bens próprios", "OBSERVACOES": "Observações",
}


@dataclass
class Bloco:
    codigo: str
    peso: int
    esperados: int = 0
    preenchidos: int = 0
    pendencias: list[tuple[str | None, str]] = field(default_factory=list)  # (competência, descrição)

    def falta(self, competencia: str | None, descricao: str) -> None:
        self.esperados += 1
        self.pendencias.append((competencia, descricao))

    def ok(self) -> None:
        self.esperados += 1
        self.preenchidos += 1

    @property
    def fracao(self) -> float:
        return 1.0 if self.esperados == 0 else self.preenchidos / self.esperados


def pesos(db: Session) -> dict[str, int]:
    out = dict(PESOS_PADRAO)
    out.update({p.bloco: p.peso for p in db.scalars(select(PesoProgresso))})
    return out


def calcular(db: Session, p: Planejamento) -> tuple[int, list[Bloco]]:
    comps = p.competencias()
    w = pesos(db)
    b = {k: Bloco(k, w.get(k, 0)) for k in PESOS_PADRAO}

    comps_saida = set(db.scalars(select(NotaFiscal.competencia).where(
        NotaFiscal.planejamento_id == p.id, NotaFiscal.tipo == "SAIDA").distinct()))
    for c in comps:
        b["SAIDAS"].ok() if c in comps_saida else b["SAIDAS"].falta(c, "Notas fiscais de saída")

    levs = {lv.competencia: lv for lv in db.scalars(select(Levantamento).where(Levantamento.planejamento_id == p.id))}
    itens = db.scalars(select(ItemDespesa).where(ItemDespesa.ativo).order_by(ItemDespesa.grupo_id, ItemDespesa.ordem)).all()
    grupos = db.scalars(select(GrupoDespesa).order_by(GrupoDespesa.ordem)).all()
    tipos_doc = db.scalars(select(TipoDocumento).order_by(TipoDocumento.ordem)).all()
    for c in comps:
        lv = levs.get(c)
        preenchidos = set()
        grupos_resp = set()
        docs = set()
        if lv:
            preenchidos = set(db.scalars(select(LevantamentoItem.item_despesa_id).where(
                LevantamentoItem.levantamento_id == lv.id)))
            grupos_resp = set(db.scalars(select(LevantamentoGrupo.grupo_id).where(
                LevantamentoGrupo.levantamento_id == lv.id)))
            docs = set(db.scalars(select(Documento.tipo_documento_id).where(Documento.levantamento_id == lv.id)))
        for it in itens:
            b["DESPESAS"].ok() if it.id in preenchidos else b["DESPESAS"].falta(c, it.nome)
        for g in grupos:
            b["OUTRAS_DESPESAS"].ok() if g.id in grupos_resp else b["OUTRAS_DESPESAS"].falta(c, f"{g.nome}: possui outras despesas?")
        for t in tipos_doc:
            b["DOCUMENTOS"].ok() if t.id in docs else b["DOCUMENTOS"].falta(c, t.nome)

    compras = set(db.scalars(select(CompraMensal.competencia).where(CompraMensal.planejamento_id == p.id)))
    for c in comps:
        b["COMPRAS"].ok() if c in compras else b["COMPRAS"].falta(c, "Compras de mercadorias")

    folhas = {f.competencia: f for f in db.scalars(select(FolhaMensal).where(FolhaMensal.planejamento_id == p.id))}
    for c in comps:
        f = folhas.get(c)
        b["FOLHA"].ok() if f and f.folha is not None else b["FOLHA"].falta(c, "Folha de salários")
        b["FOLHA"].ok() if f and f.pro_labore is not None else b["FOLHA"].falta(c, "Pró-labore")

    ncms = set(db.scalars(select(NotaItem.ncm).join(NotaFiscal).where(
        NotaFiscal.planejamento_id == p.id, NotaFiscal.tipo == "SAIDA").distinct()))
    com_regra = set(db.scalars(select(NcmRegra.ncm).where(NcmRegra.ncm.in_(ncms)))) if ncms else set()
    for n in sorted(ncms):
        b["NCM"].ok() if n in com_regra else b["NCM"].falta(None, f"NCM {n} sem regra")

    tem_bem = db.scalar(select(Bem.id).where(Bem.empresa_id == p.empresa_id).limit(1)) is not None
    b["BENS"].ok() if tem_bem or p.sem_bens else b["BENS"].falta(None, "Cadastrar bens ou declarar que não possui")
    b["OBSERVACOES"].ok() if p.observacoes_aceitas_em else b["OBSERVACOES"].falta(None, "Aceite das observações")

    valor = sum(x.peso * x.fracao for x in b.values())
    tudo_ok = all(x.preenchidos == x.esperados for x in b.values())
    progresso = 100 if tudo_ok else min(99, math.floor(valor))
    return progresso, list(b.values())


def atualizar(db: Session, p: Planejamento) -> int:
    p.progresso, _ = calcular(db, p)
    return p.progresso
