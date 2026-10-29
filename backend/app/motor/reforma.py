"""Transição da Reforma Tributária (EC 132/2023 e LC 214/2025) — carga por ano, mesma base do período."""
from __future__ import annotations

from decimal import Decimal

from .base import BaseCompetencia
from .comparativo import melhor_regime
from .icms import ResultadoIcms
from .simples import AliquotaSimples
from .tipos import ZERO, EntradaSimulacao, LinhaReforma, Memoria, Regime, ResultadoRegime


def base_credito_ibs_cbs(entrada: EntradaSimulacao, bases: dict[str, BaseCompetencia]) -> Decimal:
    compras = sum((b.compras for b in bases.values()), ZERO) * entrada.premissas.pct_compras_credito_ibs_cbs
    despesas = sum((d.valor for d in entrada.despesas if d.credito_ibs_cbs), ZERO)
    return compras + despesas


def calcular_reforma(
    entrada: EntradaSimulacao,
    bases: dict[str, BaseCompetencia],
    icms: ResultadoIcms,
    aliq_simples: AliquotaSimples,
    simples: ResultadoRegime,
    presumido: ResultadoRegime,
    real: ResultadoRegime,
    memoria: Memoria,
) -> list[LinhaReforma]:
    receita = sum((b.receita_liquida for b in bases.values()), ZERO)
    base_cred = base_credito_ibs_cbs(entrada, bases)
    valor_agregado = max(ZERO, receita - base_cred)
    memoria.registrar("Reforma", "Base de créditos de IBS/CBS", "compras × % creditável + despesas com crédito", base_cred,
                      fundamento="LC 214/2025 (não cumulatividade plena)")
    irpj_csll_lp = presumido.detalhes["irpj_normal"] + presumido.detalhes["irpj_adicional"] + _tributo(presumido, "CSLL")
    irpj_csll_lr = real.detalhes["irpj_normal"] + real.detalhes["irpj_adicional"] + _tributo(real, "CSLL")
    inss_lp = _tributo(presumido, "INSS patronal")
    inss_lr = _tributo(real, "INSS patronal")

    linhas: list[LinhaReforma] = []
    # 2026: regras atuais
    atual = {
        Regime.SIMPLES_NACIONAL: simples.total,
        Regime.LUCRO_PRESUMIDO: presumido.total,
        Regime.LUCRO_REAL: real.total,
    }
    linhas.append(_linha(2026, ZERO, ZERO, Decimal(1), atual, receita, simples.elegivel))

    for a in sorted(entrada.reforma, key=lambda x: x.ano):
        ibs_cbs = (a.cbs + a.ibs) * valor_agregado
        icms_mantido = icms.total_a_recolher * a.fator_icms
        cargas = {
            # premissa: DAS com a mesma alíquota efetiva total, sem segregação de monofásicos (extintos em 2027)
            Regime.SIMPLES_NACIONAL: receita * aliq_simples.efetiva,
            Regime.LUCRO_PRESUMIDO: icms_mantido + ibs_cbs + irpj_csll_lp + inss_lp,
            Regime.LUCRO_REAL: icms_mantido + ibs_cbs + irpj_csll_lr + inss_lr,
        }
        linhas.append(_linha(a.ano, a.cbs, a.ibs, a.fator_icms, cargas, receita, simples.elegivel))
        memoria.registrar("Reforma", f"Carga {a.ano} – Lucro Presumido",
                          "ICMS × fator mantido + (CBS + IBS) × (receita − base de créditos) + IRPJ + CSLL",
                          cargas[Regime.LUCRO_PRESUMIDO])
    return linhas


def _tributo(r: ResultadoRegime, nome: str) -> Decimal:
    return sum((t.valor for t in r.tributos if t.tributo == nome and t.competencia is None), ZERO)


def _linha(ano, cbs, ibs, fator, cargas, receita, simples_elegivel) -> LinhaReforma:
    aliquotas = {r: (ZERO if receita == 0 else v / receita) for r, v in cargas.items()}
    candidatos = dict(cargas)
    if not simples_elegivel:
        candidatos.pop(Regime.SIMPLES_NACIONAL)
    return LinhaReforma(ano, cbs, ibs, fator, cargas, aliquotas, melhor_regime(candidatos))
