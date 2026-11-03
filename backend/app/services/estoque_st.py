"""Crédito do ICMS-ST do estoque quando a mercadoria sai da substituição tributária (Portaria CAT 28/2020, SP).

O crédito exato é o relatório da portaria: item a item do estoque na véspera da exclusão, com as notas de entrada
mais recentes. No planejamento ele é estimado assim: as notas de entrada com ST importadas dão o crédito por real
de custo (fórmulas dos Anexos IV e V) e o contador informa o valor do estoque das mercadorias excluídas.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NotaFiscal, NotaItem, ParametroTributario, Planejamento, PremissaPlanejamento
from app.services import substituicao

ZERO = Decimal("0")
CHAVE = "estoque_st_valor"
FUNDAMENTO = "Portaria CAT 28/2020, arts. 2º a 4º e Anexos IV e V"
REGIMES_RPA = {"LUCRO_PRESUMIDO", "LUCRO_REAL"}
CRT_SIMPLES = {"1", "4"}
ST_RETIDA_ANTES = {"60", "500"}  # o fornecedor recebeu com ST e repassou (substituído)
CST_COM_ST = {"10", "30", "60", "70", "201", "202", "203", "500"}
PARCELAS_RPA = 12  # art. 3º, § 2º, 2 (redação da Portaria SRE 07/2026)


@dataclass
class Entrada:
    numero: str
    data: date
    ncm: str
    custo: Decimal  # valor da operação + ICMS-ST pago: o custo do estoque
    bc_st: Decimal
    credito: Decimal
    formula: str


@dataclass
class EstoqueSt:
    corte: date  # véspera da exclusão: o estoque é levantado no fim deste dia
    norma: str | None
    segmentos: list[str]
    ncms: list[str]  # NCMs da empresa que saíram da ST
    regime_rpa: bool
    entradas: list[Entrada] = field(default_factory=list)
    sem_base: int = 0  # itens com CST de ST sem a base retida na nota: crédito zero (art. 4º, I)
    estoque: Decimal | None = None

    @property
    def taxa(self) -> Decimal | None:
        custo = sum((e.custo for e in self.entradas), ZERO)
        return sum((e.credito for e in self.entradas), ZERO) / custo if custo else None

    @property
    def credito(self) -> Decimal | None:
        if self.estoque is None or self.taxa is None:
            return None
        return (self.estoque * self.taxa).quantize(Decimal("0.01"), ROUND_HALF_UP)

    @property
    def inicio_uso(self) -> str:
        """RPA: 1ª parcela no primeiro mês da exclusão. Simples: no PGDAS-D do mês seguinte ao da exclusão."""
        mes = self.corte + timedelta(days=1)
        if not self.regime_rpa:
            mes = (mes.replace(day=28) + timedelta(days=4)).replace(day=1)
        return f"{mes:%Y-%m}"

    def parcelas(self) -> list[tuple[str, Decimal]]:
        if self.credito is None:
            return []
        if not self.regime_rpa:
            return [(self.inicio_uso, self.credito)]
        parcela = (self.credito / PARCELAS_RPA).quantize(Decimal("0.01"), ROUND_HALF_UP)
        ano, mes = map(int, self.inicio_uso.split("-"))
        saida = []
        for i in range(PARCELAS_RPA):
            m = mes - 1 + i
            valor = parcela if i < PARCELAS_RPA - 1 else self.credito - parcela * (PARCELAS_RPA - 1)
            saida.append((f"{ano + m // 12}-{m % 12 + 1:02d}", valor))
        return saida


def credito_item(rpa: bool, cst: str | None, crt_fornecedor: str | None, interestadual: bool,
                 bc_st: Decimal, vl_merc: Decimal, aliq_interna: Decimal, aliq_inter: Decimal) -> tuple[Decimal, str]:
    """Crédito de um item de nota de entrada, sem redução de base de cálculo (Anexos IV e V)."""
    if not rpa:
        return max(ZERO, (bc_st - vl_merc) * aliq_interna), "Anexo V: (BC ST − valor da mercadoria) × alíquota interna"
    if (cst or "") in ST_RETIDA_ANTES or (crt_fornecedor or "") not in CRT_SIMPLES:
        return bc_st * aliq_interna, "Anexo IV: BC ST × alíquota interna"
    if not interestadual:
        return max(ZERO, (bc_st - vl_merc) * aliq_interna), "Anexo IV, fornecedor do Simples: (BC ST − valor da mercadoria) × alíquota interna"
    return (max(ZERO, bc_st * aliq_interna - vl_merc * aliq_inter),
            "Anexo IV, fornecedor do Simples de outro estado: BC ST × alíquota interna − valor da mercadoria × alíquota interestadual")


def _parametro(db: Session, chave: str, padrao: str) -> Decimal:
    v = db.scalar(select(ParametroTributario.valor).where(ParametroTributario.chave == chave)
                  .order_by(ParametroTributario.vigencia_inicio.desc()).limit(1))
    return Decimal(str(v)) if v is not None else Decimal(padrao)


def estoque_informado(db: Session, p: Planejamento) -> Decimal | None:
    pr = db.scalar(select(PremissaPlanejamento).where(PremissaPlanejamento.planejamento_id == p.id, PremissaPlanejamento.chave == CHAVE))
    bruto = json.loads(pr.valor) if pr else None
    return Decimal(str(bruto)) if bruto is not None else None


def calcular(db: Session, p: Planejamento, hoje: date | None = None) -> EstoqueSt | None:
    """None quando nenhuma mercadoria da empresa saiu da ST perto do período do planejamento."""
    uf = p.empresa.uf
    tabela = substituicao.carregar(db, uf)
    if tabela.vazia:
        return None
    linhas = db.execute(
        select(NotaItem, NotaFiscal).join(NotaFiscal, NotaItem.nota_fiscal_id == NotaFiscal.id)
        .where(NotaFiscal.planejamento_id == p.id)).all()
    ncms = {i.ncm for i, _ in linhas}

    # exclusão relevante: a mais recente que já aconteceu e não é anterior a um ano antes do período
    hoje = hoje or date.today()
    ano, mes = map(int, p.competencia_inicial.split("-"))
    limite = date(ano - 1, mes, 1)
    fins = {}
    for n in ncms:
        for r in tabela.regras:
            if r.abrange(n) and r.fim and limite <= r.fim < hoje:
                fins.setdefault(r.fim, []).append((n, r))
    if not fins:
        return None
    corte = max(fins)
    depois = f"{corte + timedelta(days=1):%Y-%m}"
    # o NCM saiu de fato: estava na ST no corte e não está no mês seguinte (uma regra mais específica pode mantê-lo)
    saiu = sorted({n for n, _ in fins[corte] if tabela.vigente(n, f"{corte:%Y-%m}") and not tabela.vigente(n, depois)})
    if not saiu:
        return None
    regras = [r for n, r in fins[corte] if n in saiu]
    est = EstoqueSt(corte=corte, norma=next((r.revogada_por for r in regras if r.revogada_por), None),
                    segmentos=sorted({r.segmento for r in regras}), ncms=saiu,
                    regime_rpa=p.empresa.regime_tributario in REGIMES_RPA, estoque=estoque_informado(db, p))

    aliq_interna = _parametro(db, "aliq_icms_interna", "0.18")
    aliq_inter_padrao = _parametro(db, "aliq_icms_interestadual", "0.12")
    for item, nf in linhas:
        if nf.tipo != "ENTRADA" or item.ncm not in saiu or nf.data_emissao > corte:
            continue
        com_st = (item.cst_icms or "") in CST_COM_ST
        if not item.bc_st:
            est.sem_base += com_st
            continue
        interestadual = bool(nf.uf_emitente and nf.uf_emitente != uf)
        credito, formula = credito_item(est.regime_rpa, item.cst_icms, nf.crt_emitente, interestadual, Decimal(str(item.bc_st)),
                                        Decimal(str(item.vl_total)), aliq_interna, Decimal(str(item.aliq_icms or aliq_inter_padrao)))
        est.entradas.append(Entrada(nf.numero, nf.data_emissao, item.ncm, Decimal(str(item.vl_total)) + Decimal(str(item.vl_icms_st or 0)),
                                    Decimal(str(item.bc_st)), credito.quantize(Decimal("0.01"), ROUND_HALF_UP), formula))
    return est
