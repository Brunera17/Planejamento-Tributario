"""Planejamento de empresa com comércio e serviço: cada receita no seu anexo do Simples, presunção por atividade no LP
e ISS no LP e no LR. Valores conferidos à mão.

Caso base: 3 meses com R$ 50 mil de mercadoria (sem ST nem monofásico) e R$ 30 mil de serviço por mês,
RBT12 R$ 960 mil, compras R$ 20 mil/mês, folha R$ 10 mil/mês e pró-labore R$ 3 mil/mês, ISS do município 3%.
"""
from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal as D

import pytest

from app.motor import engine
from app.motor.tipos import Ambito, EntradaSimulacao, ItemSaida, Premissas, Regime
from app.seeds import tabelas

COMPS = ["2026-01", "2026-02", "2026-03"]


def c(v: D) -> D:
    return v.quantize(D("0.01"), ROUND_HALF_UP)


def entrada(servico: str = "30000", **premissas) -> EntradaSimulacao:
    itens = [ItemSaida(m, "94036000", 5102, Ambito.INTERNA, True, False, False, D("50000")) for m in COMPS]
    p = {"rbt12_informado": D("960000"), "aliq_iss": D("0.03"), "anexo_servico": "III", **premissas}
    return EntradaSimulacao(
        competencias=COMPS,
        itens=itens,
        devolucoes={},
        compras={m: D("20000") for m in COMPS},
        despesas=[],
        folha={m: D("10000") for m in COMPS},
        pro_labore={m: D("3000") for m in COMPS},
        faixas_simples=list(tabelas.faixas_simples("I")),
        reforma=list(tabelas.reforma()),
        parametros=tabelas.parametros(),
        premissas=Premissas(regime_atual=Regime.SIMPLES_NACIONAL, **p),
        servicos={m: D(servico) for m in COMPS} if D(servico) else {},
        anexo_servico=p["anexo_servico"],
        faixas_servico={a: list(tabelas.faixas_simples(a)) for a in ("III", "IV", "V")},
    )


def tributo(r, nome: str) -> D:
    return sum((t.valor for t in r.tributos if t.tributo == nome and t.competencia is None), D(0))


def test_simples_mercadoria_no_anexo_i_e_servico_no_iii():
    r = engine.simular(entrada()).simples
    # Anexo I, 4ª faixa: (960.000 × 10,7% − 22.500) ÷ 960.000 = 8,35625%  → 150.000 × 8,35625% = 12.534,375
    # Anexo III, 4ª faixa: (960.000 × 16% − 35.640) ÷ 960.000 = 12,2875% → 90.000 × 12,2875% = 11.058,75
    assert r.detalhes["aliquota_efetiva_das"] == D("0.0835625")
    assert r.detalhes["aliquota_efetiva_servico"] == D("0.122875")
    assert c(r.total) == c(D("12534.375") + D("11058.75"))
    assert c(r.municipal) == c(D("11058.75") * D("0.325"))       # ISS no DAS: 32,5% da efetiva do serviço
    assert c(tributo(r, "ICMS")) == c(D("12534.375") * D("0.335"))  # ICMS só na mercadoria
    assert r.detalhes["anexo_servico"] == 3 and r.detalhes["receita_servico"] == D("90000")


def test_presumido_com_presuncao_por_atividade_e_iss():
    r = engine.simular(entrada()).presumido
    assert c(tributo(r, "PIS") + tributo(r, "COFINS")) == D("8760.00")  # (150.000 + 90.000) × 3,65%
    assert r.detalhes["base_irpj"] == D("40800")                     # 150.000 × 8% + 90.000 × 32%
    assert c(tributo(r, "IRPJ")) == D("6120.00")                     # sem adicional: base < R$ 60 mil
    assert r.detalhes["base_csll"] == D("46800")                     # 150.000 × 12% + 90.000 × 32%
    assert c(tributo(r, "CSLL")) == D("4212.00")
    assert r.municipal == D("2700") and tributo(r, "ISS") == D("2700")  # 90.000 × 3%


def test_presuncao_de_servico_de_16_por_cento_usa_csll_de_12():
    r = engine.simular(entrada(presuncao_servico=D("0.16"))).presumido
    assert r.detalhes["base_irpj"] == D("26400")   # 150.000 × 8% + 90.000 × 16%
    assert r.detalhes["base_csll"] == D("28800")   # 150.000 × 12% + 90.000 × 12% (Lei 9.249/1995, art. 20)


def test_real_com_pis_cofins_do_servico_e_iss_no_lucro():
    s = engine.simular(entrada())
    r = s.real
    assert c(r.detalhes["pis_cofins_debito"]) == D("22200.00")   # 240.000 × 9,25%
    assert c(r.detalhes["pis_cofins_credito"]) == D("5550.00")   # compras 60.000 × 9,25% (o serviço não muda o crédito)
    assert r.municipal == D("2700")
    sem_iss = engine.simular(entrada(aliq_iss=D("0"))).real
    assert c(sem_iss.detalhes["lair"] - r.detalhes["lair"]) == D("2700.00")  # o ISS sai do lucro


def test_fator_r_decide_entre_iii_e_v():
    # folha do Fator R: (10.000 × 1,08 + 3.000) × 12 = 165.600; ÷ 960.000 = 17,25% → Anexo V
    v = engine.simular(entrada(anexo_servico="R")).simples
    assert v.detalhes["fator_r"] == D("0.1725") and v.detalhes["anexo_servico"] == 5
    # Anexo V, 4ª faixa: (960.000 × 20,5% − 17.100) ÷ 960.000 = 18,71875%
    assert v.detalhes["aliquota_efetiva_servico"] == D("0.1871875")
    # folha de R$ 20 mil: (21.600 + 3.000) × 12 = 295.200 → 30,75% → Anexo III
    e = entrada(anexo_servico="R")
    e = replace(e, folha={m: D("20000") for m in COMPS})
    assert engine.simular(e).simples.detalhes["anexo_servico"] == 3


def test_anexo_iv_paga_cpp_fora_do_das():
    r = engine.simular(entrada(anexo_servico="IV")).simples
    # (3 × 10.000 × (20% + RAT 2%) + 3 × 3.000 × 20%) × (90.000 ÷ 240.000) = 8.400 × 37,5% = 3.150
    assert c(tributo(r, "INSS patronal")) == D("3150.00")
    # Anexo IV, 4ª faixa: (960.000 × 14% − 39.780) ÷ 960.000 = 9,85625%, sem CPP no DAS
    assert r.detalhes["aliquota_efetiva_servico"] == D("0.0985625")


def test_acima_do_sublimite_o_iss_sai_do_das():
    r = engine.simular(entrada(rbt12_informado=D("4000000"))).simples
    assert r.municipal == D("2700")   # 6ª faixa: sem ISS no DAS; o ISS vai ao município, 90.000 × 3%


def test_sem_aliquota_de_iss_usa_o_teto():
    assert engine.simular(entrada(aliq_iss=None)).presumido.municipal == D("4500")  # 90.000 × 5%


def test_reforma_reduz_o_iss_junto_com_o_icms():
    com = engine.simular(entrada()).reforma
    sem = engine.simular(entrada(aliq_iss=D("0"))).reforma
    for a, b in zip(com, sem):
        if a.ano == 2026:
            continue
        diferenca = a.cargas[Regime.LUCRO_PRESUMIDO] - b.cargas[Regime.LUCRO_PRESUMIDO]
        assert c(diferenca) == c(D("2700") * a.fator_icms), a.ano


CNPJ = "11223344000186"


def test_rota_empresa_de_servico_do_lancamento_ao_resultado(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "CONSULTORIA SERVICOS LTDA", "cnpj": CNPJ, "regime_tributario": "SIMPLES_NACIONAL", "uf": "SP",
        "anexo_simples": "III", "atividade": "SERVICO"})
    assert emp.status_code in (200, 201), emp.text
    pid = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp.json()["id"], "competencia_inicial": "2026-01", "competencia_final": "2026-03"}).json()["id"]

    corpo = [{"competencia": m, "valor": 30000} for m in COMPS]
    assert cliente.put(f"/api/planejamentos/{pid}/servicos", headers=contador, json=corpo).status_code == 204
    servicos = cliente.get(f"/api/planejamentos/{pid}/coleta", headers=contador).json()["servicos"]
    assert {m: float(v) for m, v in servicos.items()} == {m: 30000.0 for m in COMPS}
    r = cliente.put(f"/api/planejamentos/{pid}/premissas", headers=contador,
                    json={"aliq_iss": 0.02, "rbt12_informado": 360000, "anexo_servico": "III"})
    assert r.status_code == 204, r.text

    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador)
    assert sim.status_code in (200, 201), sim.text
    res = cliente.get(f"/api/simulacoes/{sim.json()['id']}", headers=contador).json()["resultado"]
    # Anexo III, 2ª faixa: (360.000 × 11,2% − 9.360) ÷ 360.000 = 8,6%; 90.000 × 8,6% = 7.740
    assert round(res["simples"]["total"], 2) == 7740.00
    assert res["simples"]["detalhes"]["anexo_servico"] == 3
    assert res["presumido"]["municipal"] == 1800.0   # 90.000 × 2%
    assert res["base"]["TOTAL"]["receita_servico"] == 90000.0
    assert any(c["municipal"] == 1800.0 for c in res["comparativo"])


@pytest.mark.parametrize("corpo,campo", [
    ({"anexo_servico": "VI"}, "anexo_servico"),
    ({"aliq_iss": 0.06}, "aliq_iss"),
    ({"presuncao_servico": 0.4}, "presuncao_servico"),
    ({"presuncao_servico": 0.2}, "presuncao_servico"),  # só 8%, 16% ou 32%
])
def test_rota_recusa_premissa_de_servico_invalida(cliente, contador, corpo, campo):
    r = cliente.put(f"/api/planejamentos/{_pid_servico(cliente, contador)}/premissas", headers=contador, json=corpo)
    assert r.status_code == 422 and campo in r.json()["campos"]


def _pid_servico(cliente, contador) -> int:
    emp = cliente.get("/api/empresas", headers=contador, params={"busca": CNPJ}).json()
    return next(p["id"] for p in cliente.get("/api/planejamentos", headers=contador).json() if p["empresa_id"] == emp[0]["id"])


def test_rota_competencia_repetida_no_envio_vale_a_ultima(cliente, contador):
    pid = _pid_servico(cliente, contador)
    corpo = [{"competencia": "2026-02", "valor": 1}, {"competencia": "2026-02", "valor": 2}]
    assert cliente.put(f"/api/planejamentos/{pid}/servicos", headers=contador, json=corpo).status_code == 204
    servicos = cliente.get(f"/api/planejamentos/{pid}/coleta", headers=contador).json()["servicos"]
    assert float(servicos["2026-02"]) == 2


def test_crescimento_recalcula_o_fator_r_em_cada_faixa():
    # folha de R$ 20 mil: (21.600 + 3.000) × 12 = 295.200 → 30,75% com RBT12 de 960 mil (Anexo III),
    # mas só 7,0% com RBT12 de 4,2 milhões: aí o serviço vai para o Anexo V
    e = replace(entrada(anexo_servico="R"), folha={m: D("20000") for m in COMPS})
    linhas = {l.rbt12: l for l in engine.crescimento(e, [D("960000"), D("1800000")])}
    receita = D("240000")
    efetiva_i = lambda rbt12, f: (rbt12 * f[0] - f[1]) / rbt12  # noqa: E731
    # 960 mil: Anexo I 4ª faixa e Anexo III 4ª faixa
    esperado_960 = efetiva_i(D("960000"), (D("0.107"), D("22500"))) * D("150000") / receita \
        + efetiva_i(D("960000"), (D("0.16"), D("35640"))) * D("90000") / receita
    assert c(linhas[D("960000")].aliquota_simples * 10000) == c(esperado_960 * 10000)
    # 1,8 milhão: Fator R = 295.200 ÷ 1.800.000 = 16,4% → Anexo V, 4ª faixa (20,5%; 17.100)
    esperado_18 = efetiva_i(D("1800000"), (D("0.107"), D("22500"))) * D("150000") / receita \
        + efetiva_i(D("1800000"), (D("0.205"), D("17100"))) * D("90000") / receita
    assert c(linhas[D("1800000")].aliquota_simples * 10000) == c(esperado_18 * 10000)


def test_oportunidade_de_cpp_inclui_a_cpp_fora_do_das_no_anexo_iv():
    s = engine.simular(entrada(anexo_servico="IV"))
    cpp_das = tributo(s.simples, "CPP")
    op = next(o for o in s.oportunidades if o.codigo == "CPP_DAS")
    inss_lp = tributo(s.presumido, "INSS patronal")
    assert c(op.impacto) == c(cpp_das + D("3150") - inss_lp)  # 3.150 = CPP do Anexo IV paga fora do DAS


def test_relatorios_mostram_o_servico_e_o_iss():
    from app.services.relatorio_pdf import enquadramento_simples
    from app.services.serializacao import para_json
    s = para_json(engine.simular(entrada()))
    texto = enquadramento_simples(s["simples"], 240000)
    assert "os serviços vão para o Anexo III" in texto and "12,29%" in texto
    so = para_json(engine.simular(replace(entrada(), itens=[], compras={})))
    assert enquadramento_simples(so["simples"], 90000).startswith("No Simples: Anexo III, 4ª faixa")


def test_so_servico_sem_nota_de_mercadoria():
    e = replace(entrada(), itens=[], compras={})
    s = engine.simular(e)
    assert c(s.simples.total) == c(D("90000") * D("0.122875"))
    assert s.presumido.detalhes["base_irpj"] == D("28800")   # 90.000 × 32%
