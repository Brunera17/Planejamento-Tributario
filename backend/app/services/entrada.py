"""Monta a EntradaSimulacao do motor a partir dos dados de um planejamento no banco."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AliquotaUf,
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
from app.motor.lei_monofasico import Enquadramento, avaliar
from app.motor.tipos import (
    AnoReforma,
    CreditoEstoqueSt,
    DestinoDifal,
    Despesa,
    EntradaSimulacao,
    FaixaSimples,
    InfoNcm,
    Premissas,
    Regime,
)
from app.seeds import tabelas
from app.services import estoque_st, premissas_auto, revisao_produtos, substituicao
from app.services.relatorio_contabil import CFOP_COMPRA_REVENDA

ZERO = Decimal("0")
ITEM_FOLHA = "Folha de Pagamento"
COBERTURA_MINIMA = Decimal("0.95")  # notas de compra ÷ compras informadas para usar o ICMS destacado

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


def premissas_do_planejamento(db: Session, p: Planejamento, auto: premissas_auto.Automaticas | None = None) -> Premissas:
    """Informado pelo contador > tirado das notas > padrão do motor."""
    auto = auto or premissas_auto.derivar(db, p)
    valores: dict = {k: d.valor for k, d in auto.premissas.items()}
    if auto.composicao:
        valores["composicao_compras"] = auto.composicao
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


def _info_ncm(produtos: list[revisao_produtos.Produto]) -> dict[str, InfoNcm]:
    """Verificação por NCM do planejamento: vem da lei e da revisão, nunca de anotações de outro cliente."""
    grupos: dict[str, list[revisao_produtos.Produto]] = {}
    for x in produtos:
        grupos.setdefault(x.ncm, []).append(x)
    info = {}
    for ncm, lista in grupos.items():
        pendentes = [x for x in lista if x.pendente]
        a = lista[0].avaliacao
        if pendentes:
            acao = f"{len(pendentes)} produto(s) aguardando revisão: {a.motivo}"
        elif any(x.revisado for x in lista):
            acao = "Revisado pelo contador."
        else:
            acao = "Sem ressalva na lei." if a.enquadramento != Enquadramento.NAO_LISTADO else "Fora dos anexos: tributação normal."
        info[ncm] = InfoNcm(lista[0].descricao, "MEDIA" if a.enquadramento == Enquadramento.CONDICIONAL else "ALTA", False, bool(pendentes),
                            acao, "000", "000001", "Não – alíquota padrão")
    return info


def montar_entrada(db: Session, p: Planejamento) -> EntradaMontada:
    comps = p.competencias()
    referencia = date.fromisoformat(p.competencia_inicial + "-01")
    pendencias: list[str] = []

    # saídas agregadas por competência / produto / NCM / CFOP / UF de destino (o motor é linear por item)
    linhas = db.execute(
        select(NotaFiscal.competencia, NotaItem.cod_produto, NotaItem.ncm, NotaItem.cfop, NotaFiscal.uf_destinatario,
               NotaItem.orig_icms, NotaFiscal.consumidor_final, NotaFiscal.dest_contribuinte, func.sum(NotaItem.vl_total))
        .join(NotaItem, NotaItem.nota_fiscal_id == NotaFiscal.id)
        .where(NotaFiscal.planejamento_id == p.id, NotaFiscal.tipo == "SAIDA",
               NotaFiscal.competencia.in_(comps))
        .group_by(NotaFiscal.competencia, NotaItem.cod_produto, NotaItem.ncm, NotaItem.cfop, NotaFiscal.uf_destinatario,
                  NotaItem.orig_icms, NotaFiscal.consumidor_final, NotaFiscal.dest_contribuinte)
    ).all()

    # o monofásico vem da lei; a revisão do contador decide Ex, destinação e correção de NCM
    produtos = revisao_produtos.analisar(db, p)
    por_produto = {(x.cod_produto, x.ncm_nota): x for x in produtos}
    # a ST vem da tabela da Base legal, com vigência: a mesma mercadoria pode sair da ST no meio do período
    st_vigente = substituicao.carregar(db, p.empresa.uf)
    brutos = []
    destinos = aliquotas_destino(db)
    for c, cod, ncm, cfop, uf, origem, final, contribuinte, v in linhas:
        pr = por_produto.get((cod or "", ncm))
        decidido = pr.monofasico if pr and pr.revisao else None
        ncm_final = pr.ncm if pr else ncm
        st = None if st_vigente.vazia else st_vigente.vigente(ncm_final, c) is not None
        brutos.append(ItemBruto(c, ncm_final, cfop, uf, Decimal(str(v)), monofasico=decidido, sujeito_st=st,
                                origem=origem, difal=_difal(destinos, p.empresa.uf, uf, c, final, contribuinte)))

    regras_cfop = {r.cfop: RegraCfop(r.cfop, r.gera_receita) for r in db.scalars(select(CfopRegra))}
    st = {r.ncm: r.sujeito_st for r in db.scalars(select(NcmRegra))}
    regras_ncm = {b.ncm: RegraNcm(b.ncm, avaliar(b.ncm, tabelas.lei_monofasico()).monofasico_presumido, st.get(b.ncm, False)) for b in brutos}
    cls = classificar(brutos, regras_cfop, regras_ncm, p.empresa.uf)
    if cls.cfops_sem_regra:
        pendencias.append("CFOP sem regra: " + ", ".join(map(str, sorted(cls.cfops_sem_regra))))
    pendentes = [x for x in produtos if x.pendente]
    if pendentes:
        pendencias.append(f"{len(pendentes)} produto(s) aguardando revisão do contador")
    sem_saidas = [c for c in comps if not any(i.competencia == c for i in cls.itens)]
    if sem_saidas:
        pendencias.append("Competências sem notas de saída: " + ", ".join(sem_saidas))

    def mensal(modelo) -> dict[str, Decimal]:
        return {m.competencia: m.valor for m in db.scalars(select(modelo).where(modelo.planejamento_id == p.id))}

    compras = mensal(CompraMensal)
    faltam_compras = [c for c in comps if c not in compras]
    if faltam_compras:
        pendencias.append("Compras não informadas: " + ", ".join(faltam_compras))

    # Crédito de ICMS real: só quando as notas de compra para revenda cobrem as compras informadas em todos os
    # meses. Relatórios e XMLs parciais (comuns na escrituração) zerariam o crédito do LP/LR.
    icms_entradas = None
    entradas = {c: (Decimal(str(v or 0)), Decimal(str(i or 0))) for c, v, i in db.execute(
        select(NotaFiscal.competencia, func.sum(NotaItem.vl_total), func.sum(NotaItem.vl_icms))
        .join(NotaItem, NotaItem.nota_fiscal_id == NotaFiscal.id)
        .where(NotaFiscal.planejamento_id == p.id, NotaFiscal.tipo == "ENTRADA", NotaItem.cfop.in_(CFOP_COMPRA_REVENDA))
        .group_by(NotaFiscal.competencia))}
    if entradas and all(c in entradas and compras.get(c) and entradas[c][0] >= compras[c] * COBERTURA_MINIMA for c in comps):
        icms_entradas = {c: entradas[c][1] for c in comps}

    folhas = db.scalars(select(FolhaMensal).where(FolhaMensal.planejamento_id == p.id)).all()
    folha = {f.competencia: f.folha or ZERO for f in folhas}
    pro_labore = {f.competencia: f.pro_labore or ZERO for f in folhas}
    folha_informada = any(f.folha is not None or f.pro_labore is not None for f in folhas)
    folha_do_mes = {f.competencia for f in folhas if f.folha is not None}

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
        # A folha é apurada no bloco próprio, com encargos: o item antigo do catálogo não pode deduzir de novo.
        if item.nome == ITEM_FOLHA and comp in folha_do_mes:
            continue
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

    auto = premissas_auto.derivar(db, p)
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
        premissas=premissas_do_planejamento(db, p, auto),
        folha_informada=folha_informada,
        despesas_nao_informadas=nao_informadas,
        ncms_confianca_media={x.ncm for x in produtos if x.avaliacao.enquadramento == Enquadramento.CONDICIONAL and not x.revisado},
        icms_entradas_real=icms_entradas,
        composicao_informada=db.scalar(select(CompraOrigem.id).where(CompraOrigem.planejamento_id == p.id).limit(1)) is not None
        or auto.composicao is not None,
        ncm_info=_info_ncm(produtos),
        estoque_st=_credito_estoque_st(db, p),
    )
    return EntradaMontada(entrada, pendencias)


def aliquotas_destino(db: Session) -> dict[str, list[AliquotaUf]]:
    por_uf: dict[str, list[AliquotaUf]] = {}
    for a in db.scalars(select(AliquotaUf)):
        por_uf.setdefault(a.uf, []).append(a)
    return por_uf


def _difal(destinos: dict[str, list[AliquotaUf]], uf_empresa: str | None, uf: str | None, competencia: str,
           consumidor_final: bool | None, contribuinte: bool | None) -> DestinoDifal | None:
    """Venda a consumidor final não contribuinte de outro estado. Sem o indIEDest na nota, consumidor final conta como
    não contribuinte (a venda a pessoa física é o caso comum)."""
    if not uf or not uf_empresa or uf == uf_empresa or not consumidor_final or contribuinte:
        return None
    dia = date.fromisoformat(competencia + "-01")
    a = next((x for x in destinos.get(uf, []) if x.vigencia_inicio <= dia and (x.vigencia_fim is None or dia <= x.vigencia_fim)), None)
    return DestinoDifal(uf, a.aliquota, a.fcp, a.base_dupla) if a else None


def _credito_estoque_st(db: Session, p: Planejamento) -> CreditoEstoqueSt | None:
    e = estoque_st.calcular(db, p)
    if e is None or not e.credito:
        return None
    return CreditoEstoqueSt(e.credito, f"{e.corte:%d/%m/%Y}", e.inicio_uso, e.regime_rpa, e.norma)
