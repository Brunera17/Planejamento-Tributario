"""Comparativo entre regimes, margem de equilíbrio LR × LP e simulação de crescimento."""
from __future__ import annotations

from decimal import Decimal

from .base import BaseCompetencia, ItemCalculado
from .icms import ResultadoIcms
from .real import irpj_csll_lucro_real
from .simples import (
    aliq_iss,
    aliquota_efetiva,
    anexo_do_item,
    anexo_do_servico,
    cpp_fora_do_das,
)
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
            municipal=r.municipal,
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
    mercadoria = sum((b.receita_mercadoria for b in bases.values()), ZERO)
    servico = receita - mercadoria
    # monofásico e ST como parte das vendas de mercadoria; o serviço entra no seu anexo
    mono = sum((b.receita_monofasica for b in bases.values()), ZERO) / mercadoria if mercadoria else ZERO
    st = sum((i.receita_liquida for i in itens if i.st_interna), ZERO) / mercadoria if mercadoria else ZERO
    icms_normal = (icms.total_a_recolher - icms.total_difal) / receita  # o Simples acima do sublimite não recolhe DIFAL
    cpp_fora_iv = cpp_fora_do_das(entrada, servico / receita) / receita if servico else ZERO
    por_anexo: dict[str, Decimal] = {}  # revenda no Anexo I e produção própria no II, pelo CFOP
    for i in itens:
        anexo = anexo_do_item(i.item.cfop, entrada)
        por_anexo[anexo] = por_anexo.get(anexo, ZERO) + i.receita_liquida
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
            aliq_sn = ZERO
            for anexo, valor in por_anexo.items():
                am = aliquota_efetiva(rbt12, entrada.faixas_mercadoria.get(anexo, entrada.faixas_simples))
                fm = am.faixa
                parcela = fm.p_irpj + fm.p_csll + fm.p_cpp + fm.p_ipi + fm.p_icms * (1 - st) + (fm.p_pis + fm.p_cofins) * (1 - mono)
                aliq_sn += am.efetiva * parcela * valor / receita
            # com Fator R, a mesma folha sobre outra RBT12 pode trocar o anexo do serviço
            anexo_s = anexo_do_servico(entrada, rbt12)[0] if servico else None
            cpp_fora = cpp_fora_iv if anexo_s == "IV" else ZERO
            if anexo_s:
                aliq_sn += aliquota_efetiva(rbt12, entrada.faixas_servico[anexo_s]).efetiva * servico / receita + cpp_fora
            obs = f"Faixa {f.faixa}"
            if rbt12 > p.sublimite_simples:
                aliq_sn += icms_normal + (aliq_iss(entrada) * servico / receita if anexo_s else ZERO)
                obs += " – ICMS e ISS fora do DAS (regime normal)" if anexo_s else " – ICMS fora do DAS (regime normal)"
            if rbt12 == rbt12_atual:
                obs = "Situação atual – " + obs
        cargas = {Regime.LUCRO_PRESUMIDO: aliq_lp, Regime.LUCRO_REAL: aliq_lr}
        if aliq_sn is not None:
            cargas[Regime.SIMPLES_NACIONAL] = aliq_sn
        linhas.append(LinhaCrescimento(rbt12, a.efetiva, aliq_sn, aliq_lp, aliq_lr,
                                       melhor_regime(cargas, entrada.premissas.regime_atual), obs))
    return linhas
