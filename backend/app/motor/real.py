"""Lucro Real — PIS/COFINS não cumulativos (Leis 10.637/2002 e 10.833/2003) e DRE fiscal."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .base import BaseCompetencia, ItemCalculado
from .icms import ResultadoIcms
from .presumido import base_pis_cofins, inss_patronal, irpj_devido
from .tipos import ZERO, EntradaSimulacao, Memoria, Parametros, Regime, ResultadoRegime, TributoValor


@dataclass
class PisCofinsNaoCumulativo:
    debito: dict[str, Decimal]
    credito: dict[str, Decimal]
    a_recolher: dict[str, Decimal]
    saldo_credor_final: Decimal
    despesas_com_credito: dict[str, Decimal]

    @property
    def total_debito(self) -> Decimal:
        return sum(self.debito.values(), ZERO)

    @property
    def total_credito(self) -> Decimal:
        return sum(self.credito.values(), ZERO)

    @property
    def total_a_recolher(self) -> Decimal:
        return sum(self.a_recolher.values(), ZERO)


def calcular_pis_cofins_nc(
    entrada: EntradaSimulacao,
    bases: dict[str, BaseCompetencia],
    itens: list[ItemCalculado],
    icms: ResultadoIcms,
    memoria: Memoria,
) -> PisCofinsNaoCumulativo:
    p = entrada.parametros
    aliq = p.pis_nao_cumulativo + p.cofins_nao_cumulativo
    base_deb = base_pis_cofins(entrada, itens, icms)
    debito, credito, recolher, desp_cred = {}, {}, {}, {}
    saldo = ZERO
    for c in entrada.competencias:
        b = bases[c]
        part = b.participacao_nao_monofasica
        compras_cred = b.compras * part  # compras de monofásicos (CST 70) não geram crédito
        desp = sum((d.valor for d in entrada.despesas if d.competencia == c and d.credito_pis_cofins), ZERO)
        desp_cred[c] = desp
        fretes_cred = desp * (1 if entrada.premissas.credito_frete_integral else part)
        debito[c] = base_deb[c] * aliq
        credito[c] = (compras_cred + fretes_cred) * aliq
        apurado = debito[c] - credito[c] - saldo
        recolher[c] = max(ZERO, apurado)
        saldo = max(ZERO, -apurado)
        memoria.registrar("Lucro Real", "Débitos de PIS + COFINS", "base CST 01 × 9,25%", debito[c], c)
        memoria.registrar("Lucro Real", "Créditos de PIS + COFINS",
                          "(compras × participação não monofásica + fretes/armazenagem) × 9,25%", credito[c], c,
                          "Lei 10.833/2003, art. 3º, I e IX")
        memoria.registrar("Lucro Real", "PIS + COFINS a recolher", "max(0, débitos − créditos − saldo anterior)",
                          recolher[c], c)
    return PisCofinsNaoCumulativo(debito, credito, recolher, saldo, desp_cred)


def irpj_csll_lucro_real(lucro: Decimal, n_meses: int, p: Parametros) -> tuple[Decimal, Decimal, Decimal]:
    base = max(ZERO, lucro)
    irpj, adicional = irpj_devido(base, n_meses, p)
    return irpj, adicional, base * p.csll


def calcular_real(
    entrada: EntradaSimulacao,
    bases: dict[str, BaseCompetencia],
    itens: list[ItemCalculado],
    icms: ResultadoIcms,
    memoria: Memoria,
) -> tuple[ResultadoRegime, PisCofinsNaoCumulativo]:
    p = entrada.parametros
    pr = entrada.premissas
    n = len(entrada.competencias)
    pc = calcular_pis_cofins_nc(entrada, bases, itens, icms, memoria)

    receita = sum((b.receita_liquida for b in bases.values()), ZERO)
    compras = sum((b.compras for b in bases.values()), ZERO)
    if pr.estoque_inicial is not None and pr.estoque_final is not None:
        cmv = pr.estoque_inicial + compras - pr.estoque_final
        formula_cmv = "estoque inicial + compras − estoque final"
    else:
        cmv = compras
        formula_cmv = "compras do período (estoque inicial = final)"
    despesas = sum((d.valor for d in entrada.despesas if d.dedutivel), ZERO)
    pessoal = sum(
        (entrada.folha.get(c, ZERO) * (1 + p.encargos_folha) + entrada.pro_labore.get(c, ZERO) * (1 + p.inss_pro_labore)
         for c in entrada.competencias),
        ZERO,
    )
    lair = receita - icms.total_a_recolher - pc.total_a_recolher - cmv - despesas - pessoal
    ajustado = lair + pr.adicoes_lr - pr.exclusoes_lr
    compensacao = ZERO
    if ajustado > 0 and pr.prejuizo_fiscal_compensar > 0:
        compensacao = min(pr.prejuizo_fiscal_compensar, ajustado * p.compensacao_prejuizo_limite)
    lucro_real = max(ZERO, ajustado - compensacao)
    irpj, adicional, csll = irpj_csll_lucro_real(lucro_real, n, p)

    S = "Lucro Real"
    memoria.registrar(S, "Receita líquida de vendas", "faturamento − devoluções", receita)
    memoria.registrar(S, "(−) ICMS a recolher", "seção ICMS", icms.total_a_recolher)
    memoria.registrar(S, "(−) PIS/COFINS a recolher", "débitos − créditos", pc.total_a_recolher)
    memoria.registrar(S, "(−) CMV", formula_cmv, cmv)
    memoria.registrar(S, "(−) Despesas operacionais dedutíveis", "Σ despesas marcadas como dedutíveis", despesas,
                      fundamento="RIR/2018, art. 311")
    memoria.registrar(S, "(−) Despesas com pessoal", "folha × (1 + encargos) + pró-labore × (1 + INSS)", pessoal)
    memoria.registrar(S, "(=) LAIR", "receita − tributos − CMV − despesas − pessoal", lair)
    memoria.registrar(S, "(−) Compensação de prejuízo fiscal", "min(saldo, 30% do lucro ajustado)", compensacao,
                      fundamento="Lei 9.065/1995, art. 15")
    memoria.registrar(S, "(=) Lucro real", "max(0, LAIR + adições − exclusões − compensação)", lucro_real)
    memoria.registrar(S, "IRPJ 15% + adicional", "lucro × 15% + max(0, lucro − R$ 20 mil × meses) × 10%",
                      irpj + adicional, fundamento="Lei 9.430/1996, art. 3º")
    memoria.registrar(S, "CSLL 9%", "lucro × 9%", csll)

    inss = inss_patronal(entrada)
    federal = pc.total_a_recolher + irpj + adicional + csll + inss
    tributos = [
        TributoValor("ICMS", icms.total_a_recolher),
        TributoValor("PIS/COFINS", pc.total_a_recolher),
        TributoValor("IRPJ", irpj + adicional),
        TributoValor("CSLL", csll),
        TributoValor("INSS patronal", inss),
    ]
    for c in entrada.competencias:
        tributos.append(TributoValor("ICMS", icms.a_recolher[c], c))
        tributos.append(TributoValor("PIS/COFINS", pc.a_recolher[c], c))
    detalhes = {
        "pis_cofins_debito": pc.total_debito,
        "pis_cofins_credito": pc.total_credito,
        "pis_cofins_saldo_credor": pc.saldo_credor_final,
        "cmv": cmv,
        "despesas_dedutiveis": despesas,
        "despesas_pessoal": pessoal,
        "lair": lair,
        "lucro_real": lucro_real,
        "irpj_normal": irpj,
        "irpj_adicional": adicional,
        "margem_lair": ZERO if receita == 0 else lair / receita,
    }
    return ResultadoRegime(Regime.LUCRO_REAL, icms.total_a_recolher, federal, tributos, detalhes), pc
