"""Empresa com comércio (Anexo I) e serviço (Anexo III ou V) no mesmo mês, conferida à mão pela fórmula do PGDAS-D.

Alíquota efetiva = (RBT12 × alíquota nominal − parcela a deduzir) ÷ RBT12, a mesma para todas as receitas do anexo,
com o RBT12 da empresa inteira. Cada receita paga a efetiva do seu anexo, repartida pelos percentuais da faixa.
Os valores esperados abaixo foram calculados à mão, com as tabelas da LC 123/2006 (LC 155/2016), sem usar o motor.
"""
from decimal import ROUND_HALF_UP, Decimal as D

from app.motor.calculadora_simples import LinhaNota, calcular
from app.seeds.tabelas import faixas_simples

FAIXAS = {a: list(faixas_simples(a)) for a in ("I", "II", "III", "IV", "V")}


def c(v: D) -> D:
    return v.quantize(D("0.01"), ROUND_HALF_UP)


def test_comercio_e_servico_juntos_rbt12_900_mil():
    # Anexo I, 4ª faixa: (900.000 × 10,7% − 22.500) ÷ 900.000 = 8,20%
    # Anexo III, 4ª faixa: (900.000 × 16% − 35.640) ÷ 900.000 = 12,04%
    r = calcular([
        LinhaNota("revenda sem ST", D("40000"), "I"),
        LinhaNota("revenda com ST", D("20000"), "I", st=True),
        LinhaNota("serviço", D("30000"), "III"),
        LinhaNota("serviço com ISS retido", D("10000"), "III", iss_fora_do_das="RETIDO"),
    ], D("900000"), FAIXAS)

    assert r.faixas["I"]["aliquota_efetiva"] == D("0.082")
    assert r.faixas["III"]["aliquota_efetiva"] == D("0.1204")
    # por nota: 40.000 × 8,20%; 20.000 × 8,20% × (1 − 33,5% de ICMS); 30.000 × 12,04%; 10.000 × 12,04% × (1 − 32,5% de ISS)
    assert [c(l.das) for l in r.linhas] == [D("3280.00"), D("1090.60"), D("3612.00"), D("812.70")]
    assert c(r.das) == D("8795.30")
    esperado = {
        "ICMS": D("1098.80"),   # 40.000 × 8,20% × 33,5%
        "ISS": D("1173.90"),    # 30.000 × 12,04% × 32,5%
        "IRPJ": D("463.24"),    # 4.920 × 5,5% + 4.816 × 4%
        "CSLL": D("340.76"),    # 4.920 × 3,5% + 4.816 × 3,5%
        "COFINS": D("1283.71"), # 4.920 × 12,74% + 4.816 × 13,64%
        "PIS": D("278.35"),     # 4.920 × 2,76% + 4.816 × 2,96%
        "CPP": D("4156.54"),    # 4.920 × 42% + 4.816 × 43,4%
    }
    assert {k: c(v) for k, v in r.tributos.items()} == esperado
    assert c(r.aliquota_media) == c(D("8795.30") / D("100000"))


def test_fator_r_muda_o_anexo_do_servico_e_nao_o_do_comercio():
    linhas = [LinhaNota("revenda", D("10000"), "I"), LinhaNota("consultoria", D("10000"), fator_r=True)]
    # folha 252.000 ÷ 900.000 = 28%: Anexo III, 12,04%
    com = calcular(linhas, D("900000"), FAIXAS, folha_12m=D("252000"))
    assert com.linhas[1].anexo == "III" and c(com.linhas[1].das) == D("1204.00")
    # folha 180.000 ÷ 900.000 = 20%: Anexo V, 4ª faixa: (900.000 × 20,5% − 17.100) ÷ 900.000 = 18,60%
    sem = calcular(linhas, D("900000"), FAIXAS, folha_12m=D("180000"))
    assert sem.linhas[1].anexo == "V" and c(sem.linhas[1].das) == D("1860.00")
    assert c(com.linhas[0].das) == c(sem.linhas[0].das) == D("820.00")


def test_teto_de_5_por_cento_do_iss_na_5a_faixa():
    # Anexo III, 5ª faixa: (3.000.000 × 21% − 125.640) ÷ 3.000.000 = 16,812%; ISS bruto 16,812% × 33,5% = 5,632%
    # O ISS fica em 5% e a sobra (0,632%) vai aos federais na proporção deles (IRPJ 4 de 66,5)
    r = calcular([LinhaNota("serviço", D("10000"), "III"), LinhaNota("revenda", D("10000"), "I")], D("3000000"), FAIXAS)
    servico, revenda = r.linhas
    assert c(servico.das) == D("1681.20")           # o teto não muda o total, só a repartição
    assert c(servico.tributos["ISS"]) == D("500.00")
    assert c(servico.tributos["IRPJ"]) == D("71.05")  # 10.000 × (16,812% × 4% + 0,63202% × 4 ÷ 66,5)
    # Anexo I, 5ª faixa: (3.000.000 × 14,3% − 87.300) ÷ 3.000.000 = 11,39%
    assert c(revenda.das) == D("1139.00")
