"""Restaurante: ICMS de refeições, bebidas frias monofásicas e produção própria fora da ST."""
from dataclasses import replace
from decimal import Decimal

from app.motor import simular
from app.motor.lei_monofasico import Enquadramento, avaliar
from app.seeds import tabelas
from tests.test_motor_referencia import montar_entrada


def _icms(r):
    return r.presumido.estadual


def test_icms_de_refeicoes_e_aliquota_sobre_a_receita_sem_credito():
    e = montar_entrada()
    normal = simular(e)
    refeicao = simular(replace(e, premissas=replace(e.premissas, aliq_icms_refeicao=Decimal("0.04"))))
    assert not e.premissas.aplicar_st_vendas_internas  # no caso de referência toda a receita entra no débito
    difal = refeicao.base["TOTAL"].get("icms_difal", Decimal(0))
    assert abs(_icms(refeicao) - refeicao.base["TOTAL"]["receita_liquida"] * Decimal("0.04") - difal) < Decimal("0.05")
    assert _icms(refeicao) != _icms(normal)
    assert all(o.codigo != "CREDITO_ICMS_INTERNAS" for o in refeicao.oportunidades)  # crédito vedado no regime


def test_bebidas_frias_sao_monofasicas():
    for ncm in ("22011000", "22021000", "22029900", "22030000"):
        a = avaliar(ncm, tabelas.lei_monofasico())
        assert a.enquadramento == Enquadramento.MONOFASICO and a.fundamento.startswith("Lei 13.097/2015")
    assert avaliar("21069090", tabelas.lei_monofasico()).enquadramento == Enquadramento.NAO_LISTADO  # lanche


def test_aliquota_de_refeicao_acima_de_20_por_cento_e_recusada(cliente, contador):
    pid = cliente.get("/api/planejamentos", headers=contador).json()[0]["id"]
    r = cliente.put(f"/api/planejamentos/{pid}/premissas", headers=contador, json={"aliq_icms_refeicao": "0.5"})
    assert r.status_code in (409, 422) and (r.status_code == 409 or "aliq_icms_refeicao" in r.json()["campos"])


def test_producao_propria_marcada_na_revisao_sai_da_st(cliente, contador):
    from app.db.session import SessionLocal
    from app.models import Planejamento
    from app.services.entrada import montar_entrada
    from tests.test_relatorio_contabil import gerar

    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "LANCHONETE LTDA", "cnpj": "66777888000181", "regime_tributario": "SIMPLES_NACIONAL", "anexo_simples": "I"}).json()
    pid = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-07", "competencia_final": "2026-07"}).json()["id"]
    itens = [(1, 2, "L1 - X-SALADA", 5102, "21069090", 1, 30.0, 30.0, 0.0)]
    assert cliente.post(f"/api/planejamentos/{pid}/relatorio-contabil", headers=contador,
                        files={"arquivo": ("SAIDAS.xls", gerar("Saídas", "07", itens), "application/vnd.ms-excel")}).status_code == 200

    def st():
        with SessionLocal() as db:
            return {i.sujeito_st for i in montar_entrada(db, db.get(Planejamento, pid)).entrada.itens}

    assert st() == {True}  # a tabela de ST de SP lista o NCM 2106.90
    r = cliente.put(f"/api/planejamentos/{pid}/revisao", headers=contador, json={
        "cod_produto": "L1", "ncm_nota": "21069090", "sem_st": True, "motivo": "Lanche preparado na casa"})
    assert r.status_code == 204
    assert st() == {False}
    prod = cliente.get(f"/api/planejamentos/{pid}/revisao", headers=contador).json()["produtos"][0]
    assert prod["sem_st"] is True
