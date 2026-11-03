"""Cronograma da Reforma mantido pelo contador: alteração com fonte, histórico, simulações desatualizadas e carga que não desfaz."""
from decimal import Decimal

import pytest


@pytest.fixture(scope="module")
def pid(cliente, contador):
    return next(p["id"] for p in cliente.get("/api/planejamentos", headers=contador).json() if p["cnpj"] == "11222333000181")


def _ano(cliente, h, ano):
    return next(a for a in cliente.get("/api/tabelas/reforma", headers=h).json() if a["ano"] == ano)


def test_cbs_do_tcu_na_carga(cliente, analista):
    anos = {a["ano"]: a for a in cliente.get("/api/tabelas/reforma", headers=analista).json()}
    # 11,3% do TCU; em 2027 e 2028, menos 0,1 ponto (LC 214/2025, art. 347)
    assert Decimal(str(anos[2027]["cbs"])) == Decimal("0.112") and Decimal(str(anos[2033]["cbs"])) == Decimal("0.113")
    assert "TCU" in anos[2027]["fonte"]


def test_analista_nao_altera(cliente, analista):
    corpo = {"cbs": 0.12, "ibs": 0.001, "fator_icms": 1, "fonte": "Resolução do Senado"}
    assert cliente.put("/api/tabelas/reforma/2027", headers=analista, json=corpo).status_code == 403


@pytest.mark.parametrize("corpo", [
    {"cbs": 0.12, "ibs": 0.001, "fator_icms": 1},  # sem fonte
    {"cbs": 1.2, "ibs": 0.001, "fator_icms": 1, "fonte": "Resolução do Senado"},  # 120%: digitado como inteiro
    {"cbs": 0.12, "ibs": 0.001, "fator_icms": 1.5, "fonte": "Resolução do Senado"},
])
def test_valores_invalidos(cliente, contador, corpo):
    assert cliente.put("/api/tabelas/reforma/2027", headers=contador, json=corpo).status_code == 422


def test_alteracao_vai_para_o_calculo_e_para_o_historico(cliente, contador, pid):
    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    antes = _ano(cliente, contador, 2030)
    corpo = {"cbs": 0.105, "ibs": antes["ibs"], "fator_icms": antes["fator_icms"], "fonte": "Resolução do Senado nº 99/2026 (teste)"}
    r = cliente.put("/api/tabelas/reforma/2030", headers=contador, json=corpo)
    assert r.status_code == 200, r.text
    depois = _ano(cliente, contador, 2030)
    assert Decimal(str(depois["cbs"])) == Decimal("0.105") and depois["alterado_por_nome"]

    hist = cliente.get("/api/tabelas/reforma/historico", headers=contador).json()
    assert hist[0]["ano"] == 2030 and Decimal(str(hist[0]["cbs"])) == Decimal(str(antes["cbs"]))
    assert hist[0]["substituido_por_fonte"].startswith("Resolução do Senado nº 99/2026")

    # a simulação feita antes fica desatualizada; a nova usa a alíquota nova
    lista = cliente.get(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    assert next(s for s in lista if s["id"] == sim["id"])["desatualizada"] is True
    nova = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    r2030 = next(a for a in cliente.get(f"/api/simulacoes/{nova['id']}", headers=contador).json()["resultado"]["reforma"] if a["ano"] == 2030)
    assert Decimal(str(r2030["cbs"])) == Decimal("0.105")


def test_carga_inicial_nao_desfaz_o_ajuste(cliente, contador):
    from app.db.session import SessionLocal  # substituída pela sessão de teste no conftest
    from app.seeds.carga import carregar_tabelas

    with SessionLocal() as db:
        carregar_tabelas(db)
        db.commit()
    assert Decimal(str(_ano(cliente, contador, 2030)["cbs"])) == Decimal("0.105")
