"""Simular despesas: referência de mercado da atividade, só nos itens não informados e nos meses abertos."""
from decimal import Decimal

import pytest

from tests.test_relatorio_contabil import gerar

CNPJ = "77888999000262"


@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "PIZZARIA LTDA", "cnpj": CNPJ, "regime_tributario": "SIMPLES_NACIONAL", "anexo_simples": "I",
        "cnae": "5611201"}).json()
    pid = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-07", "competencia_final": "2026-08"}).json()["id"]
    itens = [(1, 2, "P1 - PIZZA", 5102, "19023000", 1, 10000.0, 10000.0, 0.0)]
    assert cliente.post(f"/api/planejamentos/{pid}/relatorio-contabil", headers=contador,
                        files={"arquivo": ("SAIDAS.xls", gerar("Saídas", "07", itens), "application/vnd.ms-excel")}).status_code == 200
    return pid


def _item(cliente, h, nome):
    return next(i["id"] for g in cliente.get("/api/tabelas/catalogo-despesas", headers=h).json() for i in g["itens"] if i["nome"] == nome)


def test_previa_calcula_pelo_faturamento_e_so_o_contador_usa(cliente, contador, analista, pid):
    assert cliente.get(f"/api/planejamentos/{pid}/despesas-simuladas", headers=analista).status_code == 403
    d = cliente.get(f"/api/planejamentos/{pid}/despesas-simuladas?competencia=2026-07", headers=contador).json()
    assert d["perfil"]["codigo"] == "RESTAURANTE"
    [mes] = d["meses"]
    assert Decimal(str(mes["faturamento"])) == Decimal("10000")
    aluguel = next(x for x in mes["itens"] if x["item"] == "Aluguel de Imóveis")
    assert Decimal(str(aluguel["valor"])) == Decimal("530.00")
    contabil = next(x for x in mes["itens"] if x["item"] == "Honorários Contábeis")
    assert Decimal(str(contabil["valor"])) == Decimal("3500.00")


def test_preenche_so_o_vazio_marca_estimado_e_digitar_tira_a_marca(cliente, contador, pid):
    energia, aluguel = _item(cliente, contador, "Energia Elétrica"), _item(cliente, contador, "Aluguel de Imóveis")
    url = f"/api/planejamentos/{pid}/levantamentos/2026-07"
    cliente.put(url, headers=contador, json={"itens": [{"item_despesa_id": energia, "valor": "123.45"}]})
    r = cliente.post(f"/api/planejamentos/{pid}/despesas-simuladas?competencia=2026-07", headers=contador)
    assert r.status_code == 200 and r.json()["itens"] == 13  # 14 itens de referência, menos a energia já informada
    lv = cliente.get(url, headers=contador).json()
    assert Decimal(str(lv["itens"][str(energia)])) == Decimal("123.45") and energia not in lv["estimados"]
    assert aluguel in lv["estimados"]
    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    res = cliente.get(f"/api/simulacoes/{sim['id']}", headers=contador).json()["resultado"]
    assert any(p["codigo"] == "DESPESAS_ESTIMADAS" for p in res["pontos_criticos"])
    cliente.put(url, headers=contador, json={"itens": [{"item_despesa_id": aluguel, "valor": "600.00"}]})
    assert aluguel not in cliente.get(url, headers=contador).json()["estimados"]
    # simular de novo não repete: tudo já está informado
    assert cliente.post(f"/api/planejamentos/{pid}/despesas-simuladas?competencia=2026-07", headers=contador).json()["itens"] == 0


def test_mes_enviado_para_conferencia_fica_de_fora(cliente, contador, pid):
    from app.db.session import SessionLocal
    from app.models import Levantamento
    from sqlalchemy import select
    with SessionLocal() as db:
        lv = db.scalar(select(Levantamento).where(Levantamento.planejamento_id == pid, Levantamento.competencia == "2026-07"))
        lv.status = "ENVIADO"
        db.commit()
    d = cliente.get(f"/api/planejamentos/{pid}/despesas-simuladas", headers=contador).json()
    assert [m["competencia"] for m in d["meses"]] == ["2026-08"]
    with SessionLocal() as db:
        db.scalar(select(Levantamento).where(Levantamento.planejamento_id == pid, Levantamento.competencia == "2026-07")).status = "EM_PREENCHIMENTO"
        db.commit()


def test_atividade_sem_perfil_nao_simula(cliente, contador):
    pid = next(p["id"] for p in cliente.get("/api/planejamentos", headers=contador).json() if p["cnpj"] == "11222333000181")
    assert cliente.get(f"/api/planejamentos/{pid}/despesas-simuladas", headers=contador).json()["perfil"] is None


def test_zerados_so_entram_com_a_opcao_e_valor_real_nunca_muda(cliente, contador, pid):
    url = f"/api/planejamentos/{pid}/levantamentos/2026-08"
    aluguel, seguros = _item(cliente, contador, "Aluguel de Imóveis"), _item(cliente, contador, "Seguros")
    cliente.put(url, headers=contador, json={"itens": [{"item_despesa_id": aluguel, "valor": "0"}, {"item_despesa_id": seguros, "valor": "50.00"}]})
    base = f"/api/planejamentos/{pid}/despesas-simuladas?competencia=2026-08"
    sem = cliente.get(base, headers=contador).json()["meses"][0]["itens"]
    assert next(x for x in sem if x["item"] == "Aluguel de Imóveis")["ja_informado"] is True
    r = cliente.post(base + "&zerados=true", headers=contador).json()
    lv = cliente.get(url, headers=contador).json()
    assert aluguel in lv["estimados"] and seguros not in lv["estimados"]
    assert Decimal(str(lv["itens"][str(seguros)])) == Decimal("50.00")
    assert r["itens"] == 13
