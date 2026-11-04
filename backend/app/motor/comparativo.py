"""Comparativo entre regimes, margem de equilíbrio LR × LP e simulação de crescimento."""
from __future__ import annotations

from decimal import Decimal

from .base import BaseCompetencia, ItemCalculado
from .icms import ResultadoIcms
from .real import irpj_csll_lucro_real
from .simples import aliquota_efetiva
from .tipos import (
    ZERO,
    EntradaSimulacao,
    LinhaComparativo,
    LinhaCrescimento,
    Regime,
    ResultadoRegime,
)


def melhor_regime(cargas: dict[Regime, Decimal], atual: Regime | None = None) -> Regime:
    """Menor carga; em empate, mantém o regime atual."""
    menor = min(cargas.values())
    empatados = [r for r, v in cargas.items() if v == menor]
    if atual in empatados:
        return atual
    return empatados[0]


def montar_comparativo(
    regimes: list[ResultadoRegime], receita: Decimal, atual: Regime
) -> tuple[list[LinhaComparativo], Regime]:
    elegiveis = {r.regime: r.total for r in regimes if r.elegivel}
    melhor = melhor_regime(elegiveis, atual)
    menor = elegiveis[melhor]
    ordem = sorted(regimes, key=lambda r: (not r.elegivel, r.total))
    posicao = {r.regime: i + 1 for i, r in enumerate(ordem)}
    linhas = [
        LinhaComparativo(
            regime=r.regime,
            estadual=r.estadual,
            federal=r.federal,
            total=r.total,
            aliquota_efetiva=ZERO if receita == 0 else r.total / receita,
            diferenca_melhor=r.total - menor,
            posicao=posicao[r.regime],
        )
        for r in regimes
    ]
    return linhas, melhor


def margem_equilibrio(
    entrada: EntradaSimulacao,
    receita: Decimal,
    presumido: ResultadoRegime,
    pis_cofins_lr: Decimal,
) -> Decimal | None:
    """Margem de LAIR (LAIR ÷ receita) em que os tributos federais do LR igualam os do LP.

    Abaixo dela o Lucro Real é mais barato. O ICMS é igual nos dois regimes e fica de fora.
    """
    if receita <= 0:
        return None
    n = len(entrada.competencias)
    p = entrada.parametros
    d = presumido.detalhes
    federal_lp = d["base_pis_cofins"] * (p.pis_cumulativo + p.cofins_cumulativo) + d["irpj_normal"] + d["irpj_adicional"] + \
        d["base_csll"] * p.csll

    def diferenca(lair: Decimal) -> Decimal:
        irpj, adicional, csll = irpj_csll_lucro_real(lair, n, p)
        return pis_cofins_lr + irpj + adicional + csll - federal_lp

    if diferenca(ZERO) >= 0:
        return ZERO
    if diferenca(receita) < 0:
        return Decimal(1)
    baixo, alto = ZERO, receita
    for _ in range(100):
        meio = (baixo + alto) / 2
        if diferenca(meio) < 0:
            baixo = meio
        else:
            alto = meio
        if alto - baixo < Decimal("0.001"):
            break
    return (baixo + alto) / 2 / receita


def simular_crescimento(
    entrada: EntradaSimulacao,
    bases: dict[str, BaseCompetencia],
    itens: list[ItemCalculado],
    icms: ResultadoIcms,
    rbt12_atual: Decimal,
    presumido: ResultadoRegime,
    real: ResultadoRegime,
    valores: list[Decimal] | None = None,
) -> list[LinhaCrescimento]:
    """Alíquota do Simples por faixa de RBT12, com o mix atual, contra LP e LR (lineares)."""
    p = entrada.parametros
    receita = sum((b.receita_liquida for b in bases.values()), ZERO)
    if receita == 0:
        return []
    mono = sum((b.receita_monofasica for b in bases.values()), ZERO) / receita
    st = sum((i.receita_liquida for i in itens if i.st_interna), ZERO) / receita
    icms_normal = (icms.total_a_recolher - icms.total_difal) / receita  # o Simples acima do sublimite não recolhe DIFAL
    aliq_lp = presumido.total / receita
    aliq_lr = real.total / receita
    if valores is None:
        valores = [rbt12_atual, p.sublimite_simples, p.sublimite_simples + Decimal("0.01"),
                   Decimal("4200000"), p.teto_simples]

    linhas = []
    for rbt12 in valores:
        a = aliquota_efetiva(rbt12, entrada.faixas_simples)
        f = a.faixa
        if rbt12 > p.teto_simples:
            aliq_sn, obs = None, "Acima do teto: Simples inelegível"
        else:
            parcela = f.p_irpj + f.p_csll + f.p_cpp + f.p_ipi + f.p_icms * (1 - st) + (f.p_pis + f.p_cofins) * (1 - mono)
            aliq_sn = a.efetiva * parcela
            obs = f"Faixa {f.faixa}"
            if rbt12 > p.sublimite_simples:
                aliq_sn += icms_normal
                obs += " – ICMS fora do DAS (regime normal)"
            if rbt12 == rbt12_atual:
                obs = "Situação atual – " + obs
        cargas = {Regime.LUCRO_PRESUMIDO: aliq_lp, Regime.LUCRO_REAL: aliq_lr}
        if aliq_sn is not None:
            cargas[Regime.SIMPLES_NACIONAL] = aliq_sn
        linhas.append(LinhaCrescimento(rbt12, a.efetiva, aliq_sn, aliq_lp, aliq_lr,
                                       melhor_regime(cargas, entrada.premissas.regime_atual), obs))
    return linhas
