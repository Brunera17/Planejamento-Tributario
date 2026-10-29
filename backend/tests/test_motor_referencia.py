"""Caso de referência: o motor deve reproduzir a planilha final de planejamento (jun–ago/2026).

Valores esperados retirados da planilha final de planejamento do cliente de referência (seção 9 da especificação).
"""
import json
from decimal import Decimal

import pytest

from app.motor import simular
from app.motor.classificacao import ItemBruto, classificar
from app.motor.tipos import Despesa, EntradaSimulacao, InfoNcm, Premissas, Regime
from app.seeds import tabelas

FIXTURE = tabelas.DADOS / "caso_referencia.json"
CENTAVO = Decimal("0.01")


def montar_entrada(**premissas) -> EntradaSimulacao:
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    brutos = [ItemBruto(i["competencia"], i["ncm"], i["cfop"], None, Decimal(i["valor"])) for i in fx["itens"]]
    cls = classificar(brutos, tabelas.regras_cfop(), tabelas.regras_ncm())
    assert not cls.tem_pendencias
    comps = fx["competencias"]
    despesas = [
        Despesa(c, d["descricao"], Decimal(v), d["dedutivel"], d["credito_pis_cofins"], d["credito_ibs_cbs"])
        for d in fx["despesas"] for c, v in zip(comps, d["valores"])
    ]
    ncm = tabelas.ler("ncm_regras.json")
    return EntradaSimulacao(
        competencias=comps,
        itens=cls.itens,
        devolucoes={k: Decimal(v) for k, v in fx["devolucoes"].items()},
        compras={k: Decimal(v) for k, v in fx["compras"].items()},
        despesas=despesas,
        folha={}, pro_labore={},
        faixas_simples=list(tabelas.faixas_simples()),
        reforma=list(tabelas.reforma()),
        parametros=tabelas.parametros(),
        premissas=Premissas(regime_atual=Regime.SIMPLES_NACIONAL, **premissas),
        ncms_indicio_incorreto={n["ncm"] for n in ncm if n["indicio_ncm_incorreto"]},
        ncms_confianca_media={n["ncm"] for n in ncm if n["confianca"] == "MEDIA"},
        ncm_info={n["ncm"]: InfoNcm(n["produto_exemplo"], n["confianca"], n["indicio_ncm_incorreto"], n["requer_revisao"],
                                    n["acao_recomendada"], n["cst_ibs_cbs"], n["cclass_trib"], n["beneficio_reforma"]) for n in ncm},
    )


@pytest.fixture(scope="module")
def r():
    return simular(montar_entrada())


def igual(valor: Decimal, esperado: str, tol: Decimal = CENTAVO):
    assert abs(valor - Decimal(esperado)) <= tol, f"{valor:.4f} ≠ {esperado}"


def tributo(regime, nome):
    return sum(t.valor for t in regime.tributos if t.tributo == nome and t.competencia is None)


def test_base_da_operacao(r):
    t = r.base["TOTAL"]
    igual(t["receita_bruta"], "683668.40")
    igual(t["receita_liquida"], "650585.64")
    igual(t["receita_monofasica"], "443287.43")
    igual(t["receita_nao_monofasica"], "207298.21")
    igual(t["receita_interna"], "190443.14")
    igual(t["remessas_sem_receita"], "1343821.39")
    igual(r.base["2026-06"]["receita_liquida"], "192856.71")
    igual(r.base["2026-07"]["receita_liquida"], "237692.61")
    igual(r.base["2026-08"]["receita_liquida"], "220036.32")


def test_simples(r):
    d = r.simples.detalhes
    igual(d["rbt12"], "2602342.56")
    assert d["faixa"] == 5
    igual(d["aliquota_efetiva_das"], "0.109453301981888", Decimal("1e-12"))
    igual(tributo(r.simples, "ICMS"), "23854.93")
    igual(tributo(r.simples, "PIS") + tributo(r.simples, "COFINS"), "3516.87")
    igual(tributo(r.simples, "IRPJ") + tributo(r.simples, "CSLL"), "6408.79")
    igual(tributo(r.simples, "CPP"), "29907.67")
    igual(r.simples.total, "63688.26")


def test_icms_regime_normal(r):
    t = r.base["TOTAL"]
    igual(t["icms_debito"], "89496.87")
    igual(t["icms_credito"], "52130.76")
    igual(t["icms_a_recolher"], "37366.11")


def test_lucro_presumido(r):
    igual(tributo(r.presumido, "PIS") + tributo(r.presumido, "COFINS"), "7566.38")
    igual(tributo(r.presumido, "IRPJ"), "7807.03")
    igual(tributo(r.presumido, "CSLL"), "7026.32")
    igual(r.presumido.total, "59765.84")


def test_lucro_real(r):
    d = r.real.detalhes
    igual(d["pis_cofins_debito"], "19175.08")
    igual(d["pis_cofins_credito"], "12288.64")
    igual(tributo(r.real, "PIS/COFINS"), "6886.45")
    igual(d["lair"], "67469.96")
    igual(tributo(r.real, "IRPJ"), "10867.49")
    igual(tributo(r.real, "CSLL"), "6072.30")
    igual(r.real.total, "61192.34")


def test_comparativo(r):
    assert r.melhor_regime == Regime.LUCRO_PRESUMIDO
    linhas = {l.regime: l for l in r.comparativo}
    assert [linhas[x].posicao for x in Regime] == [3, 1, 2]
    igual(linhas[Regime.SIMPLES_NACIONAL].diferenca_melhor, "3922.42")
    igual(linhas[Regime.LUCRO_REAL].diferenca_melhor, "1426.50")
    igual(linhas[Regime.LUCRO_PRESUMIDO].aliquota_efetiva, "0.0918646820199963", Decimal("1e-10"))


@pytest.mark.parametrize("ano,sn,lp,lr", [
    (2027, "71208.75", "62031.04", "64137.47"),
    (2029, "71208.75", "60271.92", "62378.35"),
    (2033, "71208.75", "44439.82", "46546.25"),
])
def test_reforma(r, ano, sn, lp, lr):
    linha = next(l for l in r.reforma if l.ano == ano)
    igual(linha.cargas[Regime.SIMPLES_NACIONAL], sn)
    igual(linha.cargas[Regime.LUCRO_PRESUMIDO], lp)
    igual(linha.cargas[Regime.LUCRO_REAL], lr)
    assert linha.melhor == Regime.LUCRO_PRESUMIDO


def test_oportunidades(r):
    ops = {o.codigo: o for o in r.oportunidades}
    igual(ops["CPP_DAS"].impacto, "29907.67")
    igual(ops["SEGREGACAO_MONOFASICO"].impacto, "7520.49")
    igual(ops["ICMS_ST_INTERNAS"].impacto, "6982.95")
    igual(ops["CREDITO_ICMS_INTERNAS"].impacto, "17376.92")
    # a planilha usa a participação média do trimestre; o motor aplica a de cada mês
    igual(ops["CREDITO_FRETE_INTEGRAL"].impacto, "8066.84", Decimal("0.50"))
    assert {"SUBLIMITE", "DEVOLUCOES", "REMESSAS_FULFILLMENT", "REFORMA_POR_FORA", "REVISAO_NCM"} <= ops.keys()


def test_crescimento_e_equilibrio(r):
    atual = r.crescimento[0]
    igual(atual.aliquota_simples, "0.097893736494952", Decimal("1e-10"))
    assert r.crescimento[-1].melhor == Regime.LUCRO_PRESUMIDO
    # margem atual (10,37%) acima do equilíbrio → Lucro Presumido
    assert r.margem_equilibrio_lr_lp < r.real.detalhes["margem_lair"]


def test_tema_69_reduz_pis_cofins():
    com_tema = simular(montar_entrada(excluir_icms_base_pis_cofins=True))
    sem_tema = simular(montar_entrada())
    assert com_tema.presumido.total < sem_tema.presumido.total
    assert com_tema.real.detalhes["pis_cofins_debito"] < sem_tema.real.detalhes["pis_cofins_debito"]


def test_memoria_registrada(r):
    secoes = {p.secao for p in r.memoria.passos}
    assert {"Base", "ICMS", "Simples", "Lucro Presumido", "Lucro Real", "Reforma"} <= secoes


def test_verificacao_por_ncm(r):
    v = r.verificacao_ncm
    assert len(v) == 18
    assert v == sorted(v, key=lambda x: x.receita, reverse=True)
    igual(sum(x.receita for x in v), "650585.64")
    igual(sum(x.receita for x in v if x.monofasico), "443287.43")
    igual(sum(x.participacao for x in v), "1", Decimal("1e-12"))
    revisar = {x.ncm for x in v if x.requer_revisao}
    assert revisar == {"40093100", "40169990", "73181500", "84818021", "84818099", "84842000", "85365090", "90328929"}
    parafuso = next(x for x in v if x.ncm == "73181500")
    assert parafuso.indicio_ncm_incorreto and "8708.80.00" in parafuso.acao_recomendada
    assert {(x.cst_ibs_cbs, x.cclass_trib) for x in v} == {("000", "000001")}
    # % do faturamento da junta 4016.93.00, conferido com a aba Verificação por NCM (D8)
    igual(next(x.participacao for x in v if x.ncm == "40169300"), "0.19664810167322", Decimal("1e-10"))


def test_ncm_sem_regra_vira_pendencia():
    from dataclasses import replace
    e = montar_entrada()
    e = replace(e, ncm_info={k: v for k, v in e.ncm_info.items() if k != "85113020"})
    linha = next(x for x in simular(e).verificacao_ncm if x.ncm == "85113020")
    assert linha.sem_regra and linha.requer_revisao
