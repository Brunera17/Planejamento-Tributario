"""Simples Nacional — LC 123/2006, Anexos I (comércio), II (indústria) e III, IV e V (serviços)."""
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


FATOR_R_MINIMO = Decimal("0.28")  # LC 123/2006, art. 18, §5º-J e §5º-M
TETO_ISS = Decimal("0.05")  # LC 123/2006, Anexos III e IV, nota da 5ª faixa


def fator_r(folha_12m: Decimal, receita_12m: Decimal) -> Decimal:
    """Folha dos 12 meses (salários, pró-labore, FGTS e CPP) ÷ receita bruta dos 12 meses (LC 123/2006, art. 18, §24)."""
    return ZERO if receita_12m <= 0 else folha_12m / receita_12m


def anexo_pelo_fator_r(fator: Decimal) -> str:
    """Atividades do §5º-J: Anexo III com Fator R de 28% ou mais; abaixo disso, Anexo V."""
    return "III" if fator >= FATOR_R_MINIMO else "V"


def reparticao(aliq: AliquotaSimples) -> dict[str, Decimal]:
    """Alíquota efetiva de cada tributo do DAS. O ISS fica limitado a 5% e o excesso passa aos tributos federais,
    na proporção dos percentuais deles na faixa."""
    f = aliq.faixa
    pcts = {"IRPJ": f.p_irpj, "CSLL": f.p_csll, "COFINS": f.p_cofins, "PIS": f.p_pis, "CPP": f.p_cpp,
            "ICMS": f.p_icms, "IPI": f.p_ipi, "ISS": f.p_iss}
    out = {k: aliq.efetiva * p for k, p in pcts.items() if p}
    excesso = out.get("ISS", ZERO) - TETO_ISS
    if excesso > 0:
        out["ISS"] = TETO_ISS
        federais = [k for k in ("IRPJ", "CSLL", "COFINS", "PIS", "CPP") if pcts[k]]
        soma = sum(pcts[k] for k in federais)
        for k in federais:
            out[k] += excesso * pcts[k] / soma
    return out


RAT_REFERENCIA = Decimal("0.02")


def aliq_iss(entrada: EntradaSimulacao) -> Decimal:
    """ISS do município; sem ele, o teto (5%), para não subestimar o LP e o LR."""
    return entrada.premissas.aliq_iss if entrada.premissas.aliq_iss is not None else entrada.parametros.aliq_iss_padrao


def anexo_do_servico(entrada: EntradaSimulacao, rbt12: Decimal) -> tuple[str, Decimal | None]:
    """(anexo, Fator R). Com "R", a folha dos 12 meses (salários + FGTS + pró-labore, anualizados) ÷ RBT12 decide o anexo."""
    if entrada.anexo_servico != "R":
        return entrada.anexo_servico, None
    p, n = entrada.parametros, len(entrada.competencias)
    folha = sum((entrada.folha.get(c, ZERO) * (1 + p.fgts) + entrada.pro_labore.get(c, ZERO) for c in entrada.competencias), ZERO)
    fr = fator_r(folha / n * 12, rbt12)
    return anexo_pelo_fator_r(fr), fr


def cpp_fora_do_das(entrada: EntradaSimulacao, participacao: Decimal) -> Decimal:
    """Anexo IV: a CPP não está no DAS e é paga sobre a folha (20% + RAT × FAP; 20% do pró-labore), sem terceiros
    (LC 123/2006, art. 13, § 3º, e art. 18, § 5º-C). Com mais de uma atividade, na proporção da receita do Anexo IV."""
    pr, p = entrada.premissas, entrada.parametros
    rat = RAT_REFERENCIA if pr.rat is None else pr.rat
    fap = Decimal(1) if pr.fap is None else pr.fap
    folha = sum((entrada.folha.get(c, ZERO) * (p.cpp_patronal + rat * fap) + entrada.pro_labore.get(c, ZERO) * p.inss_pro_labore
                 for c in entrada.competencias), ZERO)
    return folha * participacao


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
    mercadoria = sum((b.receita_mercadoria for b in bases.values()), ZERO)
    irpj = mercadoria * aliq.parcela(f.p_irpj)
    csll = mercadoria * aliq.parcela(f.p_csll)
    cpp = mercadoria * aliq.parcela(f.p_cpp)
    ipi = mercadoria * aliq.parcela(f.p_ipi)  # Anexo II: o IPI da indústria vai no DAS

    # serviço: no anexo dele, com a mesma RBT12 da empresa inteira
    servico = sum((b.receita_servico for b in bases.values()), ZERO)
    iss = iss_fora_das = cpp_fora = ZERO
    detalhes_servico: dict[str, Decimal] = {}
    das_sem_segregacao = mercadoria * aliq.efetiva
    if servico:
        anexo_s, fr = anexo_do_servico(entrada, rbt12)
        aliq_s = aliquota_efetiva(rbt12, entrada.faixas_servico[anexo_s])
        partes = {k: servico * v for k, v in reparticao(aliq_s).items()}
        pis += partes.get("PIS", ZERO)
        cofins += partes.get("COFINS", ZERO)
        irpj += partes.get("IRPJ", ZERO)
        csll += partes.get("CSLL", ZERO)
        cpp += partes.get("CPP", ZERO)
        iss = partes.get("ISS", ZERO)
        if fr is not None:
            memoria.registrar("Simples", "Fator R", "(folha + FGTS + pró-labore, anualizados) ÷ RBT12", fr,
                              fundamento="LC 123/2006, art. 18, §§ 5º-J e 24")
        memoria.registrar("Simples", f"Serviços: faixa {aliq_s.faixa.faixa} do Anexo {anexo_s}", "maior faixa com RBT12 inicial ≤ RBT12",
                          Decimal(aliq_s.faixa.faixa))
        memoria.registrar("Simples", "Serviços: alíquota efetiva", "(RBT12 × alíquota nominal − parcela a deduzir) ÷ RBT12",
                          aliq_s.efetiva, fundamento="LC 123/2006, art. 18 e Anexos III, IV e V")
        memoria.registrar("Simples", "ISS no DAS", "receita de serviços × alíquota efetiva × %ISS (até 5%)", iss)
        if acima_sublimite:
            iss_fora_das = servico * aliq_iss(entrada)
            memoria.registrar("Simples", "ISS fora do DAS (RBT12 acima do sublimite)", "receita de serviços × ISS do município",
                              iss_fora_das, fundamento="LC 123/2006, art. 13-A")
        if anexo_s == "IV":
            cpp_fora = cpp_fora_do_das(entrada, servico / receita)
            memoria.registrar("Simples", "CPP fora do DAS (Anexo IV)", "folha × (20% + RAT × FAP) + pró-labore × 20%, "
                              "na proporção da receita do Anexo IV", cpp_fora, fundamento="LC 123/2006, art. 13, § 3º")
        das_sem_segregacao += servico * aliq_s.efetiva
        detalhes_servico = {
            "receita_servico": servico,
            "anexo_servico": Decimal(ROMANOS[anexo_s]),
            "faixa_servico": Decimal(aliq_s.faixa.faixa),
            "aliquota_efetiva_servico": aliq_s.efetiva,
            **({"fator_r": fr} if fr is not None else {}),
        }
    das_sem_segregacao += iss_fora_das + cpp_fora

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
        ("IRPJ no DAS", irpj, "receita de cada anexo × alíquota efetiva × %IRPJ"),
        ("CSLL no DAS", csll, "receita de cada anexo × alíquota efetiva × %CSLL"),
        ("CPP no DAS", cpp, "receita de cada anexo × alíquota efetiva × %CPP"),
        *([("IPI no DAS", ipi, "receita × alíquota efetiva × %IPI")] if ipi else []),
    ]:
        memoria.registrar("Simples", nome, formula, valor)

    estadual = icms + icms_fora_das
    federal = pis + cofins + irpj + csll + cpp + ipi + cpp_fora
    municipal = iss + iss_fora_das
    tributos = [
        TributoValor("ICMS", estadual),
        TributoValor("PIS", pis),
        TributoValor("COFINS", cofins),
        TributoValor("IRPJ", irpj),
        TributoValor("CSLL", csll),
        TributoValor("CPP", cpp),
        *([TributoValor("IPI", ipi)] if ipi else []),
        *([TributoValor("ISS", municipal)] if municipal else []),
        *([TributoValor("INSS patronal", cpp_fora)] if cpp_fora else []),
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
        # o DAS sem separar monofásico e ST, cada receita na efetiva do seu anexo (base da projeção da Reforma)
        "das_sem_segregacao": das_sem_segregacao,
        **detalhes_servico,
    }
    return ResultadoRegime(Regime.SIMPLES_NACIONAL, estadual, federal, tributos, detalhes, elegivel, municipal), aliq
