"""Orquestra o cálculo completo de uma simulação."""
from __future__ import annotations

from decimal import Decimal

from .base import calcular_base
from .comparativo import margem_equilibrio, montar_comparativo, simular_crescimento
from .icms import calcular_icms_normal
from .oportunidades import avaliar_oportunidades, pontos_criticos
from .presumido import calcular_presumido
from .real import calcular_real
from .reforma import calcular_reforma
from .simples import calcular_simples
from .tipos import ZERO, EntradaSimulacao, LinhaCrescimento, Memoria, ResultadoSimulacao
from .verificacao import verificar_ncms


def simular(entrada: EntradaSimulacao) -> ResultadoSimulacao:
    if not entrada.competencias:
        raise ValueError("O planejamento não tem competências")
    memoria = Memoria()
    bases, itens = calcular_base(entrada, memoria)
    icms = calcular_icms_normal(entrada, bases, itens, memoria)
    simples, aliq = calcular_simples(entrada, bases, itens, icms, memoria)
    presumido = calcular_presumido(entrada, bases, itens, icms, memoria)
    real, pc_lr = calcular_real(entrada, bases, itens, icms, memoria)

    receita = sum((b.receita_liquida for b in bases.values()), ZERO)
    comparativo, melhor = montar_comparativo([simples, presumido, real], receita, entrada.premissas.regime_atual)
    reforma = calcular_reforma(entrada, bases, icms, aliq, simples, presumido, real, memoria)

    return ResultadoSimulacao(
        base=_resumo_base(bases, icms, pc_lr),
        simples=simples,
        presumido=presumido,
        real=real,
        comparativo=comparativo,
        melhor_regime=melhor,
        reforma=reforma,
        oportunidades=avaliar_oportunidades(entrada, bases, itens, icms, aliq, simples, pc_lr),
        pontos_criticos=pontos_criticos(entrada, simples),
        crescimento=simular_crescimento(entrada, bases, itens, icms, aliq.rbt12, presumido, real),
        margem_equilibrio_lr_lp=margem_equilibrio(entrada, receita, presumido, pc_lr.total_a_recolher),
        memoria=memoria,
        verificacao_ncm=verificar_ncms(entrada, itens),
    )


def _resumo_base(bases, icms, pc_lr) -> dict[str, dict[str, Decimal]]:
    out: dict[str, dict[str, Decimal]] = {}
    total: dict[str, Decimal] = {}
    for c, b in bases.items():
        linha = {
            "receita_bruta": b.receita_bruta,
            "devolucoes": b.devolucoes,
            "receita_liquida": b.receita_liquida,
            "receita_monofasica": b.receita_monofasica,
            "receita_nao_monofasica": b.receita_nao_monofasica,
            "receita_interna": b.receita_interna,
            "receita_interestadual": b.receita_interestadual,
            "remessas_sem_receita": b.remessas_sem_receita,
            "compras": b.compras,
            "despesas": b.despesas,
            "icms_debito": icms.debito[c],
            "icms_credito": icms.credito[c],
            "icms_a_recolher": icms.a_recolher[c],
            "pis_cofins_lr_debito": pc_lr.debito[c],
            "pis_cofins_lr_credito": pc_lr.credito[c],
            "pis_cofins_lr_a_recolher": pc_lr.a_recolher[c],
        }
        out[c] = linha
        for k, v in linha.items():
            total[k] = total.get(k, ZERO) + v
    out["TOTAL"] = total
    return out


def crescimento(entrada: EntradaSimulacao, valores: list[Decimal]) -> list[LinhaCrescimento]:
    """Simulação de crescimento para valores de RBT12 escolhidos pelo usuário."""
    memoria = Memoria()
    bases, itens = calcular_base(entrada, memoria)
    icms = calcular_icms_normal(entrada, bases, itens, memoria)
    simples, aliq = calcular_simples(entrada, bases, itens, icms, memoria)
    presumido = calcular_presumido(entrada, bases, itens, icms, memoria)
    real, _ = calcular_real(entrada, bases, itens, icms, memoria)
    return simular_crescimento(entrada, bases, itens, icms, aliq.rbt12, presumido, real, valores)
