"""ICMS no regime normal (Lucro Presumido e Lucro Real)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .base import BaseCompetencia, ItemCalculado
from .tipos import ZERO, Ambito, DestinoDifal, EntradaSimulacao, Memoria

FUNDAMENTO = "LC 87/1996, art. 20 (não cumulatividade)"
FUNDAMENTO_DIFAL = "EC 87/2015 e LC 87/1996, art. 13, § 1º, X, com a redação da LC 190/2022"
FUNDAMENTO_REFEICAO = "RICMS/SP: regime especial de fornecimento de refeições (Decreto 51.597/2007)"
FUNDAMENTO_INTERESTADUAL = "Resoluções do Senado 22/1989 (12% e 7%) e 13/2012 (4% para importados)"

# origem da mercadoria na NF-e (tabela A do CST): 1 e 2 estrangeiras; 3 e 8 nacionais com conteúdo de importação acima
# de 40%. As origens 6 e 7 (sem similar nacional, lista da Camex) ficam fora dos 4% (Res. Senado 13/2012, art. 1º, § 4º).
ORIGENS_4 = {"1", "2", "3", "8"}
SUL_SUDESTE_SEM_ES = {"SP", "RJ", "MG", "PR", "SC", "RS"}


def aliquota_interestadual(uf_origem: str | None, uf_destino: str | None, origem: str | None) -> Decimal | None:
    """Alíquota da venda para outro estado; None quando falta a UF (o motor usa o parâmetro)."""
    if origem in ORIGENS_4:
        return Decimal("0.04")
    if not uf_origem or not uf_destino:
        return None
    # do Sul e do Sudeste (sem o ES) para o Norte, o Nordeste, o Centro-Oeste e o ES: 7%; nos demais casos, 12%
    return Decimal("0.07") if uf_origem in SUL_SUDESTE_SEM_ES and uf_destino not in SUL_SUDESTE_SEM_ES else Decimal("0.12")


@dataclass
class ResultadoIcms:
    debito: dict[str, Decimal] = field(default_factory=dict)
    credito: dict[str, Decimal] = field(default_factory=dict)
    a_recolher: dict[str, Decimal] = field(default_factory=dict)  # ICMS próprio + DIFAL e FCP devidos aos destinos
    difal: dict[str, Decimal] = field(default_factory=dict)  # DIFAL + FCP do destino (não abatido pelos créditos)
    saldo_credor_final: Decimal = ZERO
    debito_por_item: dict[int, Decimal] = field(default_factory=dict)  # índice do item -> débito

    @property
    def total_debito(self) -> Decimal:
        return sum(self.debito.values(), ZERO)

    @property
    def total_credito(self) -> Decimal:
        return sum(self.credito.values(), ZERO)

    @property
    def total_difal(self) -> Decimal:
        return sum(self.difal.values(), ZERO)

    @property
    def total_a_recolher(self) -> Decimal:
        return sum(self.a_recolher.values(), ZERO)


def aliquota_media_compras(entrada: EntradaSimulacao) -> Decimal:
    comp = entrada.premissas.composicao_compras
    soma = sum(comp.values(), ZERO)
    if abs(soma - 1) > Decimal("0.0001"):
        raise ValueError("A composição das compras por origem deve somar 100%")
    return sum((aliq * pct for aliq, pct in comp.items()), ZERO)


def aliquota_item(item: ItemCalculado, entrada: EntradaSimulacao) -> Decimal:
    p = entrada.parametros
    if item.item.ambito == Ambito.INTERNA:
        return p.aliq_icms_interna
    return item.item.aliq_interestadual if item.item.aliq_interestadual is not None else p.aliq_icms_interestadual


def difal_item(valor: Decimal, aliq_inter: Decimal, d: DestinoDifal) -> Decimal:
    """DIFAL + FCP do destino de uma venda a não contribuinte.

    Base dupla: base = (valor − ICMS interestadual) ÷ (1 − alíquota do destino com FCP); devido = base × (alíquota + FCP)
    − ICMS interestadual. Base única: valor × (alíquota + FCP − alíquota interestadual).
    """
    total = d.aliquota + d.fcp
    if d.base_dupla:
        base = (valor - valor * aliq_inter) / (1 - total)
        return max(ZERO, base * total - valor * aliq_inter)
    return max(ZERO, valor * (total - aliq_inter))


def calcular_icms_normal(
    entrada: EntradaSimulacao,
    bases: dict[str, BaseCompetencia],
    itens: list[ItemCalculado],
    memoria: Memoria,
) -> ResultadoIcms:
    r = ResultadoIcms()
    refeicao = entrada.premissas.aliq_icms_refeicao
    aliq_credito = aliquota_media_compras(entrada)
    for c in entrada.competencias:
        r.debito[c] = ZERO
        r.difal[c] = ZERO
    for i, it in enumerate(itens):
        # CST 00 = tributado; CST 60 (ST) e 41 (remessa) não geram débito
        if not it.item.gera_receita or it.st_interna:
            continue
        deb = it.receita_liquida * (refeicao if refeicao is not None else aliquota_item(it, entrada))
        r.debito_por_item[i] = deb
        r.debito[it.item.competencia] += deb
        if it.item.difal is not None:
            r.difal[it.item.competencia] += difal_item(it.receita_liquida, aliquota_item(it, entrada), it.item.difal)

    saldo = ZERO
    for c in entrada.competencias:
        if refeicao is not None:
            cred = ZERO
            formula = "regime de refeições: créditos das compras vedados"
        elif entrada.icms_entradas_real is not None:
            cred = entrada.icms_entradas_real.get(c, ZERO)
            formula = "Σ ICMS destacado nas NF-e de entrada"
        else:
            cred = bases[c].compras * aliq_credito
            formula = f"compras × alíquota média ponderada das origens ({aliq_credito * 100:.2f}%)".replace(".", ",")
        r.credito[c] = cred
        apurado = r.debito[c] - cred - saldo
        r.a_recolher[c] = max(ZERO, apurado) + r.difal[c]  # o DIFAL é do destino: o saldo credor daqui não o abate
        saldo = max(ZERO, -apurado)  # saldo credor transportado para o mês seguinte
        if refeicao is not None:
            memoria.registrar("ICMS", "ICMS débito nas vendas", f"Σ receita sem ST × {refeicao * 100:.2f}% (regime de refeições)".replace(".", ","),
                              r.debito[c], c, FUNDAMENTO_REFEICAO)
        else:
            memoria.registrar("ICMS", "ICMS débito nas vendas", "Σ base × alíquota (interna; interestadual de 4%, 7% ou 12% por item)",
                              r.debito[c], c, FUNDAMENTO_INTERESTADUAL)
        memoria.registrar("ICMS", "Crédito de ICMS sobre as compras", formula, cred, c, FUNDAMENTO)
        if r.difal[c]:
            memoria.registrar("ICMS", "DIFAL e FCP das vendas a não contribuinte de outro estado",
                              "Σ base dupla × alíquota do destino − ICMS interestadual", r.difal[c], c, FUNDAMENTO_DIFAL)
        memoria.registrar("ICMS", "ICMS a recolher", "max(0, débito − crédito − saldo credor anterior) + DIFAL", r.a_recolher[c], c)
    r.saldo_credor_final = saldo
    return r
