"""ICMS no regime normal (Lucro Presumido e Lucro Real)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .base import BaseCompetencia, ItemCalculado
from .tipos import ZERO, Ambito, EntradaSimulacao, Memoria

FUNDAMENTO = "LC 87/1996, art. 20 (não cumulatividade)"


@dataclass
class ResultadoIcms:
    debito: dict[str, Decimal] = field(default_factory=dict)
    credito: dict[str, Decimal] = field(default_factory=dict)
    a_recolher: dict[str, Decimal] = field(default_factory=dict)
    saldo_credor_final: Decimal = ZERO
    debito_por_item: dict[int, Decimal] = field(default_factory=dict)  # índice do item -> débito

    @property
    def total_debito(self) -> Decimal:
        return sum(self.debito.values(), ZERO)

    @property
    def total_credito(self) -> Decimal:
        return sum(self.credito.values(), ZERO)

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
    return p.aliq_icms_interna if item.item.ambito == Ambito.INTERNA else p.aliq_icms_interestadual


def calcular_icms_normal(
    entrada: EntradaSimulacao,
    bases: dict[str, BaseCompetencia],
    itens: list[ItemCalculado],
    memoria: Memoria,
) -> ResultadoIcms:
    r = ResultadoIcms()
    aliq_credito = aliquota_media_compras(entrada)
    for c in entrada.competencias:
        r.debito[c] = ZERO
    for i, it in enumerate(itens):
        # CST 00 = tributado; CST 60 (ST) e 41 (remessa) não geram débito
        if not it.item.gera_receita or it.st_interna:
            continue
        deb = it.receita_liquida * aliquota_item(it, entrada)
        r.debito_por_item[i] = deb
        r.debito[it.item.competencia] += deb

    saldo = ZERO
    for c in entrada.competencias:
        if entrada.icms_entradas_real is not None:
            cred = entrada.icms_entradas_real.get(c, ZERO)
            formula = "Σ ICMS destacado nas NF-e de entrada"
        else:
            cred = bases[c].compras * aliq_credito
            formula = f"compras × alíquota média ponderada das origens ({aliq_credito * 100:.2f}%)".replace(".", ",")
        r.credito[c] = cred
        apurado = r.debito[c] - cred - saldo
        r.a_recolher[c] = max(ZERO, apurado)
        saldo = max(ZERO, -apurado)  # saldo credor transportado para o mês seguinte
        memoria.registrar("ICMS", "ICMS débito nas vendas", "Σ base × alíquota (interna / interestadual)", r.debito[c], c)
        memoria.registrar("ICMS", "Crédito de ICMS sobre as compras", formula, cred, c, FUNDAMENTO)
        memoria.registrar("ICMS", "ICMS a recolher", "max(0, débito − crédito − saldo credor anterior)", r.a_recolher[c], c)
    r.saldo_credor_final = saldo
    return r
