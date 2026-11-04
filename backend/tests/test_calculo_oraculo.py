"""Cálculo conferido contra contas feitas à mão pela lei, não contra o que o motor faz.

Cada cenário tem números pequenos e redondos. O valor esperado está escrito no teste, com a conta e a base legal
no comentário, e nenhum valor esperado é obtido chamando uma função do sistema. Se o motor divergir da lei, o teste
falha e mostra a diferença.

Premissas de modelagem (não são da lei, são do planejamento, e ficam explícitas aqui):
- crédito de PIS/COFINS e de IBS/CBS sobre compras para revenda: proporcional à parte das vendas que é tributada
  (o comércio revende o que compra);
- CMV do Lucro Real = compras do período quando não há inventário.
"""
from decimal import Decimal

import pytest

from app.motor import simular
from app.motor.classificacao import ItemBruto, RegraCfop, RegraNcm, classificar
from app.motor.tipos import (
    Ambito,
    AnoReforma,
    DestinoDifal,
    EntradaSimulacao,
    FaixaSimples,
    ItemSaida,
    Parametros,
    Premissas,
    Regime,
)

D = Decimal
CENTAVO = D("0.01")

# LC 123/2006, Anexo I (comércio), com a redação da LC 155/2016: alíquota nominal, parcela a deduzir e repartição
# (IRPJ, CSLL, COFINS, PIS, CPP, ICMS). Nas faixas 3 a 5 a CPP sobe para 42% e o ICMS cai para 33,5%; na 6ª o ICMS
# sai do DAS (é recolhido por fora, acima do sublimite).
ANEXO_I = [
    FaixaSimples(1, D("0"), D("180000"), D("0.04"), D("0"), D("0.055"), D("0.035"), D("0.1274"), D("0.0276"), D("0.415"), D("0.34")),
    FaixaSimples(2, D("180000.01"), D("360000"), D("0.073"), D("5940"), D("0.055"), D("0.035"), D("0.1274"), D("0.0276"), D("0.415"), D("0.34")),
    FaixaSimples(3, D("360000.01"), D("720000"), D("0.095"), D("13860"), D("0.055"), D("0.035"), D("0.1274"), D("0.0276"), D("0.42"), D("0.335")),
    FaixaSimples(4, D("720000.01"), D("1800000"), D("0.107"), D("22500"), D("0.055"), D("0.035"), D("0.1274"), D("0.0276"), D("0.42"), D("0.335")),
    FaixaSimples(5, D("1800000.01"), D("3600000"), D("0.143"), D("87300"), D("0.055"), D("0.035"), D("0.1274"), D("0.0276"), D("0.42"), D("0.335")),
    FaixaSimples(6, D("3600000.01"), D("4800000"), D("0.19"), D("378000"), D("0.135"), D("0.10"), D("0.2827"), D("0.0613"), D("0.421"), D("0")),
]


def item(valor, *, comp="2026-07", ambito=Ambito.INTERNA, mono=False, st=False, aliq_inter=None, difal=None, reducao="0", ncm="87089990"):
    return ItemSaida(comp, ncm, 5102 if ambito == Ambito.INTERNA else 6102, ambito, True, mono, st, D(str(valor)),
                     aliq_interestadual=aliq_inter, difal=difal, reducao_ibs_cbs=D(reducao))


def entrada(itens, *, comps=("2026-07",), compras=None, regime=Regime.LUCRO_PRESUMIDO, reforma=(), devolucoes=None,
            despesas=(), folha=None, pro_labore=None, **premissas):
    def mes(v):
        return {c: D(str(x)) for c, x in (v or {}).items()}
    return EntradaSimulacao(
        competencias=list(comps), itens=itens, devolucoes=mes(devolucoes), compras=mes(compras), despesas=list(despesas),
        folha=mes(folha), pro_labore=mes(pro_labore), faixas_simples=ANEXO_I, reforma=list(reforma), parametros=Parametros(),
        premissas=Premissas(regime_atual=regime, **premissas), folha_informada=True)


def igual(valor, esperado, tol=CENTAVO):
    assert abs(D(valor) - D(esperado)) <= tol, f"calculado {D(valor):.4f}, esperado {esperado}"


def tributo(regime, nome):
    return sum((t.valor for t in regime.tributos if t.tributo == nome and t.competencia is None), D(0))


# ---------------------------------------------------------------- cenário base: comércio em SP, um mês
# Vendas internas de R$ 100.000: R$ 60.000 tributadas no PIS/COFINS e R$ 40.000 monofásicas (Lei 10.485/2002).
# Compras de R$ 50.000 de fornecedores de SP (ICMS de 18%).


@pytest.fixture(scope="module")
def base():
    return simular(entrada([item(60000), item(40000, mono=True)], compras={"2026-07": 50000}, rbt12_informado=D("1200000")))


def test_icms_regime_normal(base):
    # LC 87/1996, art. 20; RICMS/SP, art. 52, I: débito 100.000 × 18% = 18.000; crédito 50.000 × 18% = 9.000
    igual(base.base["TOTAL"]["icms_debito"], "18000")
    igual(base.base["TOTAL"]["icms_credito"], "9000")
    igual(base.base["TOTAL"]["icms_a_recolher"], "9000")


def test_lucro_presumido(base):
    lp = base.presumido
    # Lei 9.718/1998: só a receita não monofásica; PIS 60.000 × 0,65% = 390; COFINS 60.000 × 3% = 1.800
    igual(tributo(lp, "PIS"), "390")
    igual(tributo(lp, "COFINS"), "1800")
    # Lei 9.249/1995, arts. 15 e 20: IRPJ 100.000 × 8% × 15% = 1.200 (base de 8.000, abaixo dos R$ 20 mil do adicional)
    # CSLL 100.000 × 12% × 9% = 1.080
    igual(tributo(lp, "IRPJ"), "1200")
    igual(tributo(lp, "CSLL"), "1080")
    # total: 9.000 + 390 + 1.800 + 1.200 + 1.080
    igual(lp.total, "13470")


def test_lucro_real(base):
    lr = base.real
    # Leis 10.637/2002 e 10.833/2003: débito 60.000 × 9,25% = 5.550; crédito sobre a parte tributada das compras
    # 50.000 × 60% × 9,25% = 2.775; a recolher 2.775
    igual(lr.detalhes["pis_cofins_debito"], "5550")
    igual(lr.detalhes["pis_cofins_credito"], "2775")
    igual(tributo(lr, "PIS/COFINS"), "2775")
    # lucro = 100.000 − ICMS 9.000 − PIS/COFINS 2.775 − CMV 50.000 = 38.225
    igual(lr.detalhes["lucro_real"], "38225")
    # IRPJ 15% = 5.733,75 + adicional (38.225 − 20.000) × 10% = 1.822,50 → 7.556,25; CSLL 9% = 3.440,25
    igual(tributo(lr, "IRPJ"), "7556.25")
    igual(tributo(lr, "CSLL"), "3440.25")
    igual(lr.total, "22771.50")


def test_simples_nacional(base):
    # RBT12 de 1.200.000: 4ª faixa; efetiva = (1.200.000 × 10,7% − 22.500) ÷ 1.200.000 = 8,825%
    # DAS cheio 100.000 × 8,825% = 8.825; a receita monofásica não paga PIS (2,76%) e COFINS (12,74%) no DAS:
    # 40.000 × 8,825% × 15,5% = 547,15 → DAS = 8.277,85 (LC 123/2006, art. 18, § 4º-A)
    igual(base.simples.total, "8277.85")


def test_parametros_e_tabela_do_simples_da_carga_inicial_batem_com_a_lei():
    from app.seeds import tabelas
    p = tabelas.parametros()
    assert (p.pis_cumulativo, p.cofins_cumulativo, p.pis_nao_cumulativo, p.cofins_nao_cumulativo) == \
        (D("0.0065"), D("0.03"), D("0.0165"), D("0.076"))
    assert (p.irpj, p.irpj_adicional, p.irpj_limite_adicional_mensal, p.csll) == (D("0.15"), D("0.10"), D("20000"), D("0.09"))
    assert (p.presuncao_irpj, p.presuncao_csll, p.aliq_icms_interna) == (D("0.08"), D("0.12"), D("0.18"))
    carga = sorted(tabelas.faixas_simples(), key=lambda f: f.faixa)
    for f, lei in zip(carga, ANEXO_I):
        assert (f.aliq_nominal, f.parcela_deduzir) == (lei.aliq_nominal, lei.parcela_deduzir), f"faixa {f.faixa}"
        assert (f.p_irpj, f.p_csll, f.p_cofins, f.p_pis, f.p_cpp, f.p_icms) == \
            (lei.p_irpj, lei.p_csll, lei.p_cofins, lei.p_pis, lei.p_cpp, lei.p_icms), f"repartição da faixa {f.faixa}"


# ---------------------------------------------------------------- substituição tributária


def test_st_nas_vendas_internas():
    # R$ 30.000 de venda com ST (o ICMS já foi retido na entrada) e R$ 70.000 tributados, sem compras
    r = simular(entrada([item(30000, st=True), item(70000)], aplicar_st_vendas_internas=True, rbt12_informado=D("1200000")))
    # regime normal: débito só nos 70.000 × 18% = 12.600
    igual(r.base["TOTAL"]["icms_debito"], "12600")
    # Simples: a parcela de ICMS (33,5% na 4ª faixa) sai do DAS na receita com ST:
    # 100.000 × 8,825% − 30.000 × 8,825% × 33,5% = 8.825 − 886,91 = 7.938,09
    igual(r.simples.total, "7938.09")


# ---------------------------------------------------------------- operações interestaduais


def test_aliquota_interestadual_por_item():
    brutos = [ItemBruto("2026-07", "87089990", 6102, "MG", D("10000"), origem="1"),  # importado: 4%
              ItemBruto("2026-07", "87089990", 6102, "BA", D("10000"), origem="0"),  # SP → BA: 7%
              ItemBruto("2026-07", "87089990", 6102, "RJ", D("10000"), origem="0")]  # SP → RJ: 12%
    cls = classificar(brutos, {6102: RegraCfop(6102, True)}, {"87089990": RegraNcm("87089990", False)}, "SP")
    r = simular(entrada(cls.itens))
    # Res. Senado 13/2012 e 22/1989: 400 + 700 + 1.200
    igual(r.base["TOTAL"]["icms_debito"], "2300")


def test_difal_base_dupla_e_fcp():
    # EC 87/2015; LC 87/1996, art. 13, § 1º, X (LC 190/2022). R$ 10.000 a pessoa física na BA (20,5%), a 7%:
    # base = (10.000 − 700) ÷ (1 − 0,205) = 11.698,11; DIFAL = 11.698,11 × 20,5% − 700 = 1.698,11
    # R$ 10.000 a pessoa física no RJ (20% + 2% de FCP), a 12%:
    # base = (10.000 − 1.200) ÷ (1 − 0,22) = 11.282,05; DIFAL + FCP = 11.282,05 × 22% − 1.200 = 1.282,05
    itens = [item(10000, ambito=Ambito.INTERESTADUAL, aliq_inter=D("0.07"), difal=DestinoDifal("BA", D("0.205"))),
             item(10000, ambito=Ambito.INTERESTADUAL, aliq_inter=D("0.12"), difal=DestinoDifal("RJ", D("0.20"), D("0.02")))]
    r = simular(entrada(itens, rbt12_informado=D("1200000")))
    igual(r.base["TOTAL"]["icms_difal"], "2980.16")
    # ICMS do LP = débito interestadual 1.900 + DIFAL 2.980,16 (sem compras, sem crédito)
    igual(tributo(r.presumido, "ICMS"), "4880.16")
    # o Simples não recolhe DIFAL (ADI 5464): DAS = 20.000 × 8,825% = 1.765
    igual(r.simples.total, "1765")


def test_saldo_credor_nao_abate_o_difal():
    # julho: débito 18.000 (100.000 interno), crédito 27.000 (150.000 de compras) → nada a recolher, saldo de 9.000
    # agosto: débito 18.000 − crédito 9.000 − saldo 9.000 = 0 de ICMS próprio; o DIFAL de 1.698,11 da venda à BA
    # é do estado de destino e é pago mesmo com saldo credor em SP
    itens = [item(100000, comp="2026-07"), item(100000, comp="2026-08"),
             item(10000, comp="2026-08", ambito=Ambito.INTERESTADUAL, aliq_inter=D("0.07"), difal=DestinoDifal("BA", D("0.205")))]
    r = simular(entrada(itens, comps=("2026-07", "2026-08"), compras={"2026-07": 150000, "2026-08": 50000}))
    igual(r.base["2026-07"]["icms_a_recolher"], "0")
    # agosto: débito 18.000 + 700 = 18.700; crédito 9.000; saldo 9.000 → próprio 700 + DIFAL 1.698,11
    igual(r.base["2026-08"]["icms_a_recolher"], "2398.11")


# ---------------------------------------------------------------- Lucro Presumido acima de R$ 5 milhões (LC 224/2025)


def test_presuncao_acrescida_acima_do_limite():
    # três meses de R$ 600.000: receita 1.800.000; limite proporcional 5.000.000 ÷ 12 × 3 = 1.250.000; excedente 550.000
    # base IRPJ = 1.250.000 × 8% + 550.000 × 8,8% = 148.400 → IRPJ 22.260 + adicional (148.400 − 60.000) × 10% = 8.840
    # base CSLL = 1.250.000 × 12% + 550.000 × 13,2% = 222.600 → CSLL 20.034
    comps = ("2026-07", "2026-08", "2026-09")
    r = simular(entrada([item(600000, comp=c) for c in comps], comps=comps))
    igual(tributo(r.presumido, "IRPJ"), "31100")
    igual(tributo(r.presumido, "CSLL"), "20034")


def test_tema_69_tira_o_icms_da_base_do_pis_cofins():
    # RE 574.706: base = 60.000 − ICMS do item 10.800 = 49.200; PIS 319,80; COFINS 1.476
    r = simular(entrada([item(60000)], excluir_icms_base_pis_cofins=True))
    igual(tributo(r.presumido, "PIS"), "319.80")
    igual(tributo(r.presumido, "COFINS"), "1476")


def test_compensacao_de_prejuizo_limitada_a_30():
    # Lei 9.065/1995, art. 15: lucro antes da compensação = 100.000 − 18.000 de ICMS − 9.250 de PIS/COFINS = 72.750;
    # compensa no máximo 30% = 21.825 (saldo de prejuízo 50.000) → lucro real 50.925
    r = simular(entrada([item(100000)], prejuizo_fiscal_compensar=D("50000")))
    igual(r.real.detalhes["lucro_real"], "50925")


# ---------------------------------------------------------------- Reforma: reduções dos anexos da LC 214/2025


def test_reforma_com_reducoes():
    # 2033 (modelo definitivo): CBS 11,3% + IBS 17,7% = 29%; ICMS extinto
    # vendas de 1.000 de arroz (Anexo I, zero), 1.000 de mel (Anexo VII, 60%) e 1.000 de autopeça (cheia)
    # receita tributada = 0 + 400 + 1.000 = 1.400 (46,67% da receita)
    # crédito das compras de 1.500 na mesma proporção = 700 → valor agregado 700 → CBS + IBS = 203
    itens = [item(1000, reducao="1", ncm="10063021"), item(1000, reducao="0.6", ncm="04090000"), item(1000)]
    ano = AnoReforma(2033, D("0.113"), D("0.177"), D("0"))
    r = simular(entrada(itens, compras={"2026-07": 1500}, reforma=[ano]))
    linha = next(x for x in r.reforma if x.ano == 2033)
    # LP em 2033 = CBS/IBS 203 + IRPJ (3.000 × 8% × 15% = 36) + CSLL (3.000 × 12% × 9% = 32,40)
    igual(linha.cargas[Regime.LUCRO_PRESUMIDO], "271.40")


# ---------------------------------------------------------------- devoluções, compras de outros estados, folha e frete


def test_devolucao_reduz_a_receita_de_todos_os_tributos():
    # vendas de 100.000 com 10.000 devolvidos: receita líquida 90.000; ICMS 90.000 × 18% = 16.200;
    # PIS 90.000 × 0,65% = 585; COFINS 90.000 × 3% = 2.700; IRPJ 90.000 × 8% × 15% = 1.080; CSLL 90.000 × 12% × 9% = 972
    r = simular(entrada([item(100000)], devolucoes={"2026-07": 10000}))
    igual(r.base["TOTAL"]["receita_liquida"], "90000")
    igual(r.base["TOTAL"]["icms_debito"], "16200")
    igual(tributo(r.presumido, "PIS"), "585")
    igual(tributo(r.presumido, "COFINS"), "2700")
    igual(tributo(r.presumido, "IRPJ"), "1080")
    igual(tributo(r.presumido, "CSLL"), "972")


def test_credito_de_icms_pela_origem_das_compras():
    # compras de 50.000: metade de SP (18%) e metade de outro estado do Sudeste (12%) → crédito 4.500 + 3.000 = 7.500
    r = simular(entrada([item(100000)], compras={"2026-07": 50000}, composicao_compras={D("0.18"): D("0.5"), D("0.12"): D("0.5")}))
    igual(r.base["TOTAL"]["icms_credito"], "7500")
    igual(r.base["TOTAL"]["icms_a_recolher"], "10500")


def test_folha_e_pro_labore():
    # folha de 10.000 com encargos de 27,8% (CPP 20% + RAT 2% + terceiros 5,8%) = 2.780; pró-labore de 5.000 × 20% = 1.000
    # (Lei 8.212/1991, art. 22) → INSS patronal de 3.780 no LP e no LR
    r = simular(entrada([item(100000)], folha={"2026-07": 10000}, pro_labore={"2026-07": 5000}))
    igual(tributo(r.presumido, "INSS patronal"), "3780")
    igual(tributo(r.real, "INSS patronal"), "3780")
    # no LR o custo de pessoal sai do lucro: 10.000 × 1,278 + 5.000 × 1,2 = 18.780
    igual(r.real.detalhes["despesas_pessoal"], "18780")


def test_frete_credita_pis_cofins_na_parte_tributada():
    from app.motor.tipos import Despesa
    frete = [Despesa("2026-07", "Fretes", D("1000"), True, True, True)]
    # vendas 60% tributadas: crédito do frete 1.000 × 60% × 9,25% = 55,50 (premissa padrão)
    r = simular(entrada([item(60000), item(40000, mono=True)], despesas=frete))
    igual(r.real.detalhes["pis_cofins_credito"], "55.50")
    # com a premissa de crédito integral: 1.000 × 9,25% = 92,50
    r = simular(entrada([item(60000), item(40000, mono=True)], despesas=frete, credito_frete_integral=True))
    igual(r.real.detalhes["pis_cofins_credito"], "92.50")


def test_cmv_com_inventario():
    # CMV = estoque inicial 20.000 + compras 50.000 − estoque final 30.000 = 40.000
    # lucro = 100.000 − ICMS 9.000 − PIS/COFINS 2.775 − CMV 40.000 = 48.225
    r = simular(entrada([item(60000), item(40000, mono=True)], compras={"2026-07": 50000},
                        estoque_inicial=D("20000"), estoque_final=D("30000")))
    igual(r.real.detalhes["cmv"], "40000")
    igual(r.real.detalhes["lucro_real"], "48225")


# ---------------------------------------------------------------- Simples: RBT12 estimado e acima do sublimite


def test_rbt12_estimado_pela_media_do_periodo():
    # sem RBT12 informado: 100.000 por mês × 12 = 1.200.000 → mesma alíquota efetiva de 8,825%
    r = simular(entrada([item(100000)]))
    igual(r.simples.total, "8825")


@pytest.mark.parametrize("rbt12, efetiva", [
    ("150000", "0.04"),  # 1ª faixa: 4%, sem parcela a deduzir
    ("300000", "0.0532"),  # (300.000 × 7,3% − 5.940) ÷ 300.000
    ("600000", "0.0719"),  # (600.000 × 9,5% − 13.860) ÷ 600.000
    ("2400000", "0.106625"),  # (2.400.000 × 14,3% − 87.300) ÷ 2.400.000
])
def test_aliquota_efetiva_por_faixa(rbt12, efetiva):
    r = simular(entrada([item(100000)], rbt12_informado=D(rbt12)))
    igual(r.simples.total, str(D("100000") * D(efetiva)))


def test_simples_acima_do_sublimite_paga_icms_por_fora():
    # RBT12 4.000.000 (6ª faixa): efetiva = (4.000.000 × 19% − 378.000) ÷ 4.000.000 = 9,55%; o DAS não tem ICMS
    # (LC 123/2006, art. 13-A): DAS 9.550 + ICMS do regime normal 9.000 = 18.550
    r = simular(entrada([item(100000)], compras={"2026-07": 50000}, rbt12_informado=D("4000000")))
    igual(r.simples.total, "18550")


@pytest.mark.parametrize("premissas, inss", [
    # RAT 3% com FAP 1,5 e terceiros de 4,5%: 20% + 3% × 1,5 + 4,5% = 29% → 10.000 × 29% + 5.000 × 20% = 3.900
    ({"rat": D("0.03"), "fap": D("1.5"), "terceiros": D("0.045")}, "3900"),
    # só o RAT de 1% informado; FAP 1 e terceiros de 5,8% de referência: 26,8% → 2.680 + 1.000 = 3.680
    ({"rat": D("0.01")}, "3680"),
    # FAP mínimo 0,5 sobre RAT de 2%: 20% + 1% + 5,8% = 26,8% → 3.680
    ({"fap": D("0.5")}, "3680"),
])
def test_encargos_da_empresa(premissas, inss):
    r = simular(entrada([item(100000)], folha={"2026-07": 10000}, pro_labore={"2026-07": 5000}, **premissas))
    igual(tributo(r.presumido, "INSS patronal"), inss)
    igual(tributo(r.real, "INSS patronal"), inss)


# ---------------------------------------------------------------- Simples: Anexo II (indústria)
# LC 123/2006, Anexo II: repartição das faixas 1 a 5 — IRPJ 5,5%, CSLL 3,5%, COFINS 11,51%, PIS 2,49%, CPP 37,5%,
# IPI 7,5% e ICMS 32%; na 6ª faixa o ICMS sai do DAS e o IPI fica com 35%.
_R2 = (D("0.055"), D("0.035"), D("0.1151"), D("0.0249"), D("0.375"), D("0.32"), D("0.075"))
ANEXO_II = [
    FaixaSimples(1, D("0"), D("180000"), D("0.045"), D("0"), *_R2),
    FaixaSimples(2, D("180000.01"), D("360000"), D("0.078"), D("5940"), *_R2),
    FaixaSimples(3, D("360000.01"), D("720000"), D("0.10"), D("13860"), *_R2),
    FaixaSimples(4, D("720000.01"), D("1800000"), D("0.112"), D("22500"), *_R2),
    FaixaSimples(5, D("1800000.01"), D("3600000"), D("0.147"), D("85500"), *_R2),
    FaixaSimples(6, D("3600000.01"), D("4800000"), D("0.30"), D("720000"), D("0.085"), D("0.075"), D("0.2096"), D("0.0454"), D("0.235"), D("0"), D("0.35")),
]


def test_tabela_do_anexo_ii_da_carga_inicial_bate_com_a_lei():
    from app.seeds import tabelas
    for f, lei in zip(sorted(tabelas.faixas_simples("II"), key=lambda x: x.faixa), ANEXO_II):
        assert f == lei, f"faixa {f.faixa}"


def test_simples_anexo_ii_industria():
    from dataclasses import replace
    e = replace(entrada([item(60000), item(40000, mono=True)], rbt12_informado=D("1200000")), faixas_simples=ANEXO_II, anexo_simples="II")
    r = simular(e)
    # 4ª faixa: efetiva = (1.200.000 × 11,2% − 22.500) ÷ 1.200.000 = 9,325%; DAS cheio 9.325
    # o monofásico tira PIS (2,49%) e COFINS (11,51%): 40.000 × 9,325% × 14% = 522,20 → DAS 8.802,80
    igual(r.simples.total, "8802.80")
    # o IPI está no DAS: 100.000 × 9,325% × 7,5% = 699,375
    igual(tributo(r.simples, "IPI"), "699.38")
    assert r.simples.detalhes["anexo"] == 2
    assert any(p.codigo == "IPI" for p in r.pontos_criticos)


@pytest.mark.parametrize("cadastro, cnae, atividade, esperado", [
    ("II", "4530703", "COMERCIO", ("II", "cadastro")),  # o cadastro manda, mesmo com CNAE de comércio
    (None, "4530703", None, ("I", "CNAE")),  # comércio de autopeças
    (None, "2949299", None, ("II", "CNAE")),  # fabricação de peças para veículos
    (None, "6201501", "SERVICO", ("III", "atividade")),  # serviço: III, IV ou V, a confirmar no cadastro
    (None, None, None, ("I", "padrão")),
    (None, None, "INDUSTRIA", ("II", "atividade")),
])
def test_anexo_da_empresa(cadastro, cnae, atividade, esperado):
    from app.utils.simples import anexo_da_empresa
    assert anexo_da_empresa(cadastro, cnae, atividade) == esperado
