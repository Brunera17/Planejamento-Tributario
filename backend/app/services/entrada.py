"""Monta a EntradaSimulacao do motor a partir dos dados de um planejamento no banco."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    CfopRegra,
    CompraMensal,
    CompraOrigem,
    DevolucaoMensal,
    FolhaMensal,
    ItemDespesa,
    Levantamento,
    LevantamentoItem,
    NcmRegra,
    NotaFiscal,
    NotaItem,
    OutraDespesa,
    ParametroTributario,
    Planejamento,
    PremissaPlanejamento,
    ReformaCronograma,
    SimplesFaixa,
)
from app.motor.classificacao import ItemBruto, RegraCfop, RegraNcm, classificar
from app.motor.tipos import (
    AnoReforma,
    Despesa,
    EntradaSimulacao,
    FaixaSimples,
    InfoNcm,
    Premissas,
    Regime,
)
from app.seeds import tabelas

ZERO = Decimal("0")

# premissas aceitas em premissa_planejamento -> tipo
PREMISSAS = {
    "rbt12_informado": Decimal,
    "aplicar_st_vendas_internas": bool,
    "excluir_icms_base_pis_cofins": bool,
    "credito_frete_integral": bool,
    "pct_compras_credito_ibs_cbs": Decimal,
    "estoque_inicial": Decimal,
    "estoque_final": Decimal,
    "adicoes_lr": Decimal,
    "exclusoes_lr": Decimal,
    "prejuizo_fiscal_compensar": Decimal,
    "vendas_b2c": bool,
}


@dataclass
class EntradaMontada:
    entrada: EntradaSimulacao
    pendencias: list[str] = field(default_factory=list)


def _vigentes(db: Session, modelo, referencia: date):
    return db.scalars(select(modelo).where(
        modelo.vigencia_inicio <= referencia,
        or_(modelo.vigencia_fim.is_(None), modelo.vigencia_fim >= referencia),
    )).all()


def premissas_do_planejamento(db: Session, p: Planejamento) -> Premissas:
    valores = {}
    for pr in db.scalars(select(PremissaPlanejamento).where(PremissaPlanejamento.planejamento_id == p.id)):
        tipo = PREMISSAS.get(pr.chave)
        if tipo is None:
            continue
        bruto = json.loads(pr.valor)
        if bruto is None:
            continue
        valores[pr.chave] = Decimal(str(bruto)) if tipo is Decimal else bool(bruto)
    origens = db.scalars(select(CompraOrigem).where(CompraOrigem.planejamento_id == p.id)).all()
    if origens:
        valores["composicao_compras"] = {o.aliquota: o.percentual for o in origens}
    return Premissas(regime_atual=Regime(p.empresa.regime_tributario), **valores)


def montar_entrada(db: Session, p: Planejamento) -> EntradaMontada:
    comps = p.competencias()
    referencia = date.fromisoformat(p.competencia_inicial + "-01")
    pendencias: list[str] = []

    # saídas agregadas por competência / NCM / CFOP / UF de destino (o motor é linear por item)
    linhas = db.execute(
        select(NotaFiscal.competencia, NotaItem.ncm, NotaItem.cfop, NotaFiscal.uf_destinatario,
               func.sum(NotaItem.vl_total))
        .join(NotaItem, NotaItem.nota_fiscal_id == NotaFiscal.id)
        .where(NotaFiscal.planejamento_id == p.id, NotaFiscal.tipo == "SAIDA",
               NotaFiscal.competencia.in_(comps))
        .group_by(NotaFiscal.competencia, NotaItem.ncm, NotaItem.cfop, NotaFiscal.uf_destinatario)
    ).all()
    brutos = [ItemBruto(c, ncm, cfop, uf, Decimal(str(v))) for c, ncm, cfop, uf, v in linhas]
    regras_cfop = {r.cfop: RegraCfop(r.cfop, r.gera_receita) for r in db.scalars(select(CfopRegra))}
    ncms = {r.ncm: r for r in db.scalars(select(NcmRegra))}
    regras_ncm = {n: RegraNcm(n, r.monofasico, r.sujeito_st) for n, r in ncms.items()}
    cls = classificar(brutos, regras_cfop, regras_ncm, p.empresa.uf)
    if cls.cfops_sem_regra:
        pendencias.append("CFOP sem regra: " + ", ".join(map(str, sorted(cls.cfops_sem_regra))))
    if cls.ncms_sem_regra:
        pendencias.append("NCM sem regra: " + ", ".join(sorted(cls.ncms_sem_regra)))
    sem_saidas = [c for c in comps if not any(i.competencia == c for i in cls.itens)]
    if sem_saidas:
        pendencias.append("Competências sem notas de saída: " + ", ".join(sem_saidas))

    ncms_usados = {i.ncm for i in cls.itens}

    def mensal(modelo) -> dict[str, Decimal]:
        return {m.competencia: m.valor for m in db.scalars(select(modelo).where(modelo.planejamento_id == p.id))}

    compras = mensal(CompraMensal)
    faltam_compras = [c for c in comps if c not in compras]
    if faltam_compras:
        pendencias.append("Compras não informadas: " + ", ".join(faltam_compras))

    icms_entradas = None
    entradas_xml = db.execute(
        select(NotaFiscal.competencia, func.sum(NotaItem.vl_icms))
        .join(NotaItem, NotaItem.nota_fiscal_id == NotaFiscal.id)
        .where(NotaFiscal.planejamento_id == p.id, NotaFiscal.tipo == "ENTRADA")
        .group_by(NotaFiscal.competencia)
    ).all()
    if entradas_xml and {c for c, _ in entradas_xml} >= set(comps):
        icms_entradas = {c: Decimal(str(v or 0)) for c, v in entradas_xml}

    folhas = db.scalars(select(FolhaMensal).where(FolhaMensal.planejamento_id == p.id)).all()
    folha = {f.competencia: f.folha or ZERO for f in folhas}
    pro_labore = {f.competencia: f.pro_labore or ZERO for f in folhas}
    folha_informada = any(f.folha is not None or f.pro_labore is not None for f in folhas)

    # despesas: itens do catálogo + outras despesas descritas
    despesas: list[Despesa] = []
    informados: set[int] = set()
    for comp, item, valor in db.execute(
        select(Levantamento.competencia, ItemDespesa, LevantamentoItem.valor)
        .join(LevantamentoItem, LevantamentoItem.levantamento_id == Levantamento.id)
        .join(ItemDespesa, ItemDespesa.id == LevantamentoItem.item_despesa_id)
        .where(Levantamento.planejamento_id == p.id)
    ):
        informados.add(item.id)
        if valor:
            despesas.append(Despesa(comp, item.nome, valor, item.dedutivel_irpj_csll, item.credito_pis_cofins,
                                    item.credito_ibs_cbs))
    for comp, outra in db.execute(
        select(Levantamento.competencia, OutraDespesa)
        .join(OutraDespesa, OutraDespesa.levantamento_id == Levantamento.id)
        .where(Levantamento.planejamento_id == p.id)
    ):
        despesas.append(Despesa(comp, outra.descricao, outra.valor, True, False, True))
    nao_informadas = [i.nome for i in db.scalars(select(ItemDespesa).where(ItemDespesa.ativo).order_by(ItemDespesa.ordem))
                      if i.id not in informados]

    faixas = [FaixaSimples(f.faixa, f.rbt12_de, f.rbt12_ate, f.aliq_nominal, f.parcela_deduzir, f.p_irpj, f.p_csll,
                           f.p_cofins, f.p_pis, f.p_cpp, f.p_icms)
              for f in _vigentes(db, SimplesFaixa, referencia) if f.anexo == (p.empresa.anexo_simples or "I")]
    if not faixas:
        raise ValueError("Tabela do Simples Nacional vigente não cadastrada")
    parametros = tabelas.parametros({x.chave: x.valor for x in _vigentes(db, ParametroTributario, referencia)})
    reforma = [AnoReforma(r.ano, r.cbs, r.ibs, r.fator_icms) for r in db.scalars(select(ReformaCronograma))]

    entrada = EntradaSimulacao(
        competencias=comps,
        itens=cls.itens,
        devolucoes=mensal(DevolucaoMensal),
        compras=compras,
        despesas=despesas,
        folha=folha,
        pro_labore=pro_labore,
        faixas_simples=faixas,
        reforma=reforma,
        parametros=parametros,
        premissas=premissas_do_planejamento(db, p),
        folha_informada=folha_informada,
        despesas_nao_informadas=nao_informadas,
        ncms_indicio_incorreto={n for n in ncms_usados if n in ncms and ncms[n].indicio_ncm_incorreto},
        ncms_confianca_media={n for n in ncms_usados if n in ncms and ncms[n].confianca == "MEDIA"},
        icms_entradas_real=icms_entradas,
        ncm_info={n: InfoNcm(r.produto_exemplo, r.confianca, r.indicio_ncm_incorreto, r.requer_revisao, r.acao_recomendada,
                             r.cst_ibs_cbs, r.cclass_trib, r.beneficio_reforma)
                  for n, r in ncms.items() if n in ncms_usados},
    )
    return EntradaMontada(entrada, pendencias)
