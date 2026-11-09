"""A memória de cálculo das simulações novas vive só em memoria_calculo; o resultado_json não a carrega.

A API devolve o mesmo formato de sempre, e as simulações antigas (memória dentro do JSON) continuam legíveis."""
import io
import json
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from sqlalchemy import delete, select

from app.models import MemoriaCalculo, Planejamento, Simulacao
from app.services import exportacao_excel, memoria_calculo

CHAVES = {"secao", "descricao", "formula", "valor", "competencia", "fundamento"}


@pytest.fixture
def db(fabrica_sessao):
    """Sessão desfeita no fim: o que o teste altera não vaza para os outros."""
    with fabrica_sessao() as s:
        yield s
        s.rollback()


def _linhas(db, sid):
    return db.scalars(select(MemoriaCalculo).where(MemoriaCalculo.simulacao_id == sid).order_by(MemoriaCalculo.ordem)).all()


def _passos_da_tabela(db, sid) -> list[dict]:
    """Os passos como o formato antigo os gravava no JSON, montados aqui sem usar o código testado."""
    return [{"secao": m.secao, "descricao": m.descricao, "formula": m.formula, "valor": float(m.resultado),
             "competencia": m.competencia, "fundamento": m.fundamento} for m in _linhas(db, sid)]


@pytest.fixture(scope="module")
def sim_id(cliente, contador):
    """Uma simulação gerada pela API sobre o planejamento de demonstração."""
    lista = cliente.get("/api/planejamentos", headers=contador).json()
    pid = next(p["id"] for p in lista if p["cnpj"] == "11222333000181")
    r = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _simulacao(db, sim_id) -> Simulacao:
    sim = db.get(Simulacao, sim_id)
    assert sim is not None and _linhas(db, sim.id)
    return sim


def _no_formato_antigo(db, sim) -> dict:
    """Põe a simulação no formato antigo (memória também dentro do JSON) e devolve o resultado sem a memória."""
    r = json.loads(sim.resultado_json)
    assert "memoria" not in r
    sim.resultado_json = json.dumps({**r, "memoria": {"passos": _passos_da_tabela(db, sim.id)}}, ensure_ascii=False)
    db.flush()
    return r


def test_simulacao_nova_nao_grava_a_memoria_no_json(fabrica_sessao, sim_id):
    with fabrica_sessao() as db:
        sim = _simulacao(db, sim_id)
        assert "memoria" not in json.loads(sim.resultado_json)


def test_api_devolve_a_memoria_no_formato_de_sempre(cliente, contador, fabrica_sessao, sim_id):
    with fabrica_sessao() as db:
        sim = _simulacao(db, sim_id)
        esperados = _passos_da_tabela(db, sim.id)

    r = cliente.get(f"/api/simulacoes/{sim.id}/memoria", headers=contador)
    assert r.status_code == 200
    passos = r.json()
    assert passos == esperados  # mesmos passos, na mesma ordem, com os mesmos campos e valores
    assert all(set(p) == CHAVES for p in passos)

    secao = passos[0]["secao"]
    filtrados = cliente.get(f"/api/simulacoes/{sim.id}/memoria", params={"secao": secao}, headers=contador).json()
    assert filtrados == [p for p in esperados if p["secao"] == secao] and filtrados

    completo = cliente.get(f"/api/simulacoes/{sim.id}", headers=contador).json()
    assert "memoria" not in completo["resultado"]  # a rota do resultado nunca a devolveu


def test_excel_traz_a_memoria_lida_da_tabela(fabrica_sessao, sim_id):
    with fabrica_sessao() as db:
        sim = _simulacao(db, sim_id)
        n = len(_linhas(db, sim.id))
        p = db.get(Planejamento, sim.planejamento_id)
        planilha = load_workbook(io.BytesIO(exportacao_excel.gerar(sim, p)))["Memória de Cálculo"]
    descricoes = {c.value for linha in planilha.iter_rows() for c in linha}
    assert "(=) LAIR" in descricoes
    assert planilha.max_row >= n  # um passo por linha, mais o cabeçalho


def test_simulacao_antiga_com_memoria_no_json_continua_legivel(db, sim_id):
    sim = _simulacao(db, sim_id)
    _no_formato_antigo(db, sim)
    db.execute(delete(MemoriaCalculo).where(MemoriaCalculo.simulacao_id == sim.id))  # só o JSON a tem
    db.flush()
    assert memoria_calculo.passos(db, sim)  # lê do JSON


def test_simulacao_antiga_preserva_os_decimais_do_json(db, sim_id):
    """O motor gera 10 casas e a coluna guarda 8: a antiga lê do JSON e não perde o 9º e o 10º decimais."""
    sim = _simulacao(db, sim_id)
    _no_formato_antigo(db, sim)
    passos = json.loads(sim.resultado_json)["memoria"]["passos"]
    passos[0]["valor"] = 132618.7493054108
    sim.resultado_json = json.dumps({**json.loads(sim.resultado_json), "memoria": {"passos": passos}}, ensure_ascii=False)
    db.flush()
    assert memoria_calculo.passos(db, sim)[0]["valor"] == 132618.7493054108


def test_simulacao_nova_le_da_tabela_com_8_casas(db, sim_id):
    sim = _simulacao(db, sim_id)
    linha = _linhas(db, sim.id)[0]
    linha.resultado = Decimal("132618.7493054108")  # o que o motor produz
    db.flush()
    db.expire_all()
    assert memoria_calculo.passos(db, db.get(Simulacao, sim.id))[0]["valor"] == 132618.74930541
