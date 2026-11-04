"""Lucro Presumido — Lei 9.249/1995, Lei 9.718/1998 e LC 224/2025."""
from __future__ import annotations

from decimal import Decimal

from .base import BaseCompetencia, ItemCalculado
from .icms import ResultadoIcms
from .tipos import ZERO, EntradaSimulacao, Memoria, Parametros, Regime, ResultadoRegime, TributoValor


def base_pis_cofins(
    entrada: EntradaSimulacao, itens: list[ItemCalculado], icms: ResultadoIcms
) -> dict[str, Decimal]:
    """Base de PIS/COFINS por competência: receita dos itens CST 01 (não monofásicos).

    Com a premissa do Tema 69/STF, o ICMS destacado do item sai da base.
    """
    base = {c: ZERO for c in entrada.competencias}
    excluir = entrada.premissas.excluir_icms_base_pis_cofins
    for i, it in enumerate(itens):
        if not it.tributado_pis_cofins:
            continue
        valor = it.receita_liquida
        if excluir:
            valor -= icms.debito_por_item.get(i, ZERO)
        base[it.item.competencia] += valor
    return base


def irpj_devido(base: Decimal, n_meses: int, p: Parametros) -> tuple[Decimal, Decimal]:
    """(IRPJ 15%, adicional de 10% sobre o que exceder R$ 20 mil × meses)."""
    normal = base * p.irpj
    adicional = max(ZERO, base - p.irpj_limite_adicional_mensal * n_meses) * p.irpj_adicional
    return normal, adicional


RAT_REFERENCIA = Decimal("0.02")
TERCEIROS_REFERENCIA = Decimal("0.058")


def encargos_folha(entrada: EntradaSimulacao) -> Decimal:
    """CPP 20% + RAT × FAP + terceiros (Lei 8.212/1991, art. 22; Lei 10.666/2003, art. 10).

    Sem RAT, FAP e terceiros informados, vale a referência dos parâmetros (27,8%); com algum informado, os que faltam
    seguem a referência (RAT 2%, FAP 1, terceiros 5,8%).
    """
    pr, p = entrada.premissas, entrada.parametros
    if pr.rat is None and pr.fap is None and pr.terceiros is None:
        return p.encargos_folha
    rat = RAT_REFERENCIA if pr.rat is None else pr.rat
    fap = Decimal(1) if pr.fap is None else pr.fap
    terceiros = TERCEIROS_REFERENCIA if pr.terceiros is None else pr.terceiros
    return p.cpp_patronal + rat * fap + terceiros


def inss_patronal(entrada: EntradaSimulacao) -> Decimal:
    p = entrada.parametros
    encargos = encargos_folha(entrada)
    return sum(
        (entrada.folha.get(c, ZERO) * encargos + entrada.pro_labore.get(c, ZERO) * p.inss_pro_labore
         for c in entrada.competencias),
        ZERO,
    )


def calcular_presumido(
    entrada: EntradaSimulacao,
    bases: dict[str, BaseCompetencia],
    itens: list[ItemCalculado],
    icms: ResultadoIcms,
    memoria: Memoria,
) -> ResultadoRegime:
    p = entrada.parametros
    n = len(entrada.competencias)
    base_pc = base_pis_cofins(entrada, itens, icms)
    total_base_pc = sum(base_pc.values(), ZERO)
    pis = total_base_pc * p.pis_cumulativo
    cofins = total_base_pc * p.cofins_cumulativo
    memoria.registrar("Lucro Presumido", "PIS cumulativo", "base CST 01 × 0,65%", pis, fundamento="Lei 9.718/1998")
    memoria.registrar("Lucro Presumido", "COFINS cumulativa", "base CST 01 × 3%", cofins, fundamento="Lei 9.718/1998")

    receita = sum((b.receita_liquida for b in bases.values()), ZERO)
    limite = p.limite_receita_anual_presuncao / 12 * n
    ate_limite = min(receita, limite)
    excedente = max(ZERO, receita - limite)
    fator = 1 + p.acrescimo_presuncao
    base_ir = ate_limite * p.presuncao_irpj + excedente * p.presuncao_irpj * fator
    base_cs = ate_limite * p.presuncao_csll + excedente * p.presuncao_csll * fator
    irpj, adicional = irpj_devido(base_ir, n, p)
    csll = base_cs * p.csll

    memoria.registrar("Lucro Presumido", "Limite sem acréscimo de presunção", "R$ 5 mi ÷ 12 × meses", limite,
                      fundamento="LC 224/2025")
    memoria.registrar("Lucro Presumido", "Base do IRPJ", "até o limite × 8% + excedente × 8,8%", base_ir,
                      fundamento="Lei 9.249/1995, art. 15")
    memoria.registrar("Lucro Presumido", "IRPJ 15%", "base × 15%", irpj)
    memoria.registrar("Lucro Presumido", "Adicional de IRPJ", "max(0, base − R$ 20 mil × meses) × 10%", adicional,
                      fundamento="Lei 9.430/1996, art. 3º")
    memoria.registrar("Lucro Presumido", "Base da CSLL", "até o limite × 12% + excedente × 13,2%", base_cs,
                      fundamento="Lei 9.249/1995, art. 20")
    memoria.registrar("Lucro Presumido", "CSLL 9%", "base × 9%", csll)

    inss = inss_patronal(entrada)
    pr = entrada.premissas
    memoria.registrar("Lucro Presumido", "Encargos patronais sobre a folha",
                      "CPP 20% + RAT × FAP + terceiros" if (pr.rat, pr.fap, pr.terceiros) != (None, None, None)
                      else "referência: CPP 20% + RAT 2% + terceiros 5,8%", encargos_folha(entrada),
                      fundamento="Lei 8.212/1991, art. 22; Lei 10.666/2003, art. 10")
    federal = pis + cofins + irpj + adicional + csll + inss
    tributos = [
        TributoValor("ICMS", icms.total_a_recolher),
        TributoValor("PIS", pis),
        TributoValor("COFINS", cofins),
        TributoValor("IRPJ", irpj + adicional),
        TributoValor("CSLL", csll),
        TributoValor("INSS patronal", inss),
    ]
    for c in entrada.competencias:
        tributos.append(TributoValor("ICMS", icms.a_recolher[c], c))
        tributos.append(TributoValor("PIS", base_pc[c] * p.pis_cumulativo, c))
        tributos.append(TributoValor("COFINS", base_pc[c] * p.cofins_cumulativo, c))
    detalhes = {
        "base_pis_cofins": total_base_pc,
        "base_irpj": base_ir,
        "base_csll": base_cs,
        "irpj_normal": irpj,
        "irpj_adicional": adicional,
        "receita_excedente_limite": excedente,
    }
    return ResultadoRegime(Regime.LUCRO_PRESUMIDO, icms.total_a_recolher, federal, tributos, detalhes)
