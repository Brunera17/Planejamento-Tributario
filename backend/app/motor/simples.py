"""Simples Nacional — LC 123/2006, Anexos I (comércio) e II (indústria)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.utils.simples import ROMANOS

from .base import BaseCompetencia, ItemCalculado
from .icms import ResultadoIcms
from .tipos import (
    ZERO,
    EntradaSimulacao,
    FaixaSimples,
    Memoria,
    Regime,
    ResultadoRegime,
    TributoValor,
)

FUNDAMENTO = "LC 123/2006, art. 18 e Anexos I (comércio) e II (indústria)"


@dataclass(frozen=True)
class AliquotaSimples:
    rbt12: Decimal
    faixa: FaixaSimples
    efetiva: Decimal

    def parcela(self, percentual: Decimal) -> Decimal:
        return self.efetiva * percentual


def localizar_faixa(rbt12: Decimal, faixas: list[FaixaSimples]) -> FaixaSimples:
    """Maior faixa cujo limite inicial é ≤ RBT12 (equivale ao MATCH(...;1) da planilha)."""
    ordenadas = sorted(faixas, key=lambda f: f.rbt12_de)
    escolhida = ordenadas[0]
    for f in ordenadas:
        if f.rbt12_de <= rbt12:
            escolhida = f
    return escolhida


def aliquota_efetiva(rbt12: Decimal, faixas: list[FaixaSimples]) -> AliquotaSimples:
    if rbt12 <= 0:
        f = localizar_faixa(ZERO, faixas)
        return AliquotaSimples(rbt12, f, f.aliq_nominal)
    f = localizar_faixa(rbt12, faixas)
    efetiva = (rbt12 * f.aliq_nominal - f.parcela_deduzir) / rbt12
    return AliquotaSimples(rbt12, f, efetiva)


def calcular_rbt12(entrada: EntradaSimulacao, bases: dict[str, BaseCompetencia]) -> tuple[Decimal, bool]:
    """Retorna (RBT12, estimado?)."""
    if entrada.premissas.rbt12_informado:
        return entrada.premissas.rbt12_informado, False
    total = sum((b.receita_liquida for b in bases.values()), ZERO)
    return total / len(bases) * 12, True


def calcular_simples(
    entrada: EntradaSimulacao,
    bases: dict[str, BaseCompetencia],
    itens: list[ItemCalculado],
    icms_normal: ResultadoIcms,
    memoria: Memoria,
) -> tuple[ResultadoRegime, AliquotaSimples]:
    p = entrada.parametros
    rbt12, estimado = calcular_rbt12(entrada, bases)
    aliq = aliquota_efetiva(rbt12, entrada.faixas_simples)
    f = aliq.faixa
    memoria.registrar("Simples", "RBT12 " + ("estimado (média do período × 12)" if estimado else "informado (PGDAS-D)"),
                      "Σ receita líquida ÷ nº de meses × 12" if estimado else "premissa", rbt12, fundamento=FUNDAMENTO)
    memoria.registrar("Simples", f"Faixa {f.faixa} do Anexo {entrada.anexo_simples}", "maior faixa com RBT12 inicial ≤ RBT12", Decimal(f.faixa))
    memoria.registrar("Simples", "Alíquota efetiva do DAS", "(RBT12 × alíquota nominal − parcela a deduzir) ÷ RBT12",
                      aliq.efetiva, fundamento=FUNDAMENTO)

    acima_sublimite = rbt12 > p.sublimite_simples
    elegivel = rbt12 <= p.teto_simples

    icms = pis = cofins = ZERO
    for it in itens:
        rl = it.receita_liquida
        if not it.st_interna:
            icms += rl * aliq.parcela(f.p_icms)
        if not it.item.monofasico:
            pis += rl * aliq.parcela(f.p_pis)
            cofins += rl * aliq.parcela(f.p_cofins)

    receita = sum((b.receita_liquida for b in bases.values()), ZERO)
    irpj = receita * aliq.parcela(f.p_irpj)
    csll = receita * aliq.parcela(f.p_csll)
    cpp = receita * aliq.parcela(f.p_cpp)
    ipi = receita * aliq.parcela(f.p_ipi)  # Anexo II: o IPI da indústria vai no DAS

    icms_fora_das = ZERO
    if acima_sublimite:
        # acima do sublimite o ICMS é recolhido por fora do DAS, no regime normal
        # sem o DIFAL: o optante do Simples não o recolhe nas vendas a não contribuinte (ADI 5464)
        icms_fora_das = icms_normal.total_a_recolher - icms_normal.total_difal
        memoria.registrar("Simples", "ICMS fora do DAS (RBT12 acima do sublimite)", "ICMS a recolher no regime normal",
                          icms_fora_das, fundamento="LC 123/2006, art. 13-A")

    for nome, valor, formula in [
        ("ICMS no DAS", icms, "Σ receita × alíquota efetiva × %ICMS (zero nos itens com ST)"),
        ("PIS no DAS", pis, "Σ receita não monofásica × alíquota efetiva × %PIS"),
        ("COFINS no DAS", cofins, "Σ receita não monofásica × alíquota efetiva × %COFINS"),
        ("IRPJ no DAS", irpj, "receita × alíquota efetiva × %IRPJ"),
        ("CSLL no DAS", csll, "receita × alíquota efetiva × %CSLL"),
        ("CPP no DAS", cpp, "receita × alíquota efetiva × %CPP"),
        *([("IPI no DAS", ipi, "receita × alíquota efetiva × %IPI")] if ipi else []),
    ]:
        memoria.registrar("Simples", nome, formula, valor)

    estadual = icms + icms_fora_das
    federal = pis + cofins + irpj + csll + cpp + ipi
    tributos = [
        TributoValor("ICMS", estadual),
        TributoValor("PIS", pis),
        TributoValor("COFINS", cofins),
        TributoValor("IRPJ", irpj),
        TributoValor("CSLL", csll),
        TributoValor("CPP", cpp),
        *([TributoValor("IPI", ipi)] if ipi else []),
    ]
    detalhes = {
        "anexo": Decimal(ROMANOS[entrada.anexo_simples]),
        "rbt12": rbt12,
        "rbt12_estimado": Decimal(int(estimado)),
        "faixa": Decimal(f.faixa),
        "aliquota_nominal": f.aliq_nominal,
        "parcela_deduzir": f.parcela_deduzir,
        "aliquota_efetiva_das": aliq.efetiva,
        "acima_sublimite": Decimal(int(acima_sublimite)),
    }
    return ResultadoRegime(Regime.SIMPLES_NACIONAL, estadual, federal, tributos, detalhes, elegivel), aliq
