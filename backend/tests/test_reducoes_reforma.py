"""Reduções de CBS e IBS dos anexos da LC 214/2025 na projeção da Reforma."""
from decimal import Decimal

import pytest

CNPJ = "62418951000132"


def _consulta(cliente, h, ncm):
    return cliente.get("/api/tabelas/reforma-reducoes/consulta", headers=h, params={"ncm": ncm}).json()["reducao"]


@pytest.mark.parametrize("ncm, anexo, reducao", [
    ("10063021", "Anexo I", "1"),  # arroz: cesta básica, alíquota zero
    ("02013000", "Anexo I", "1"),  # carne bovina
    ("04090000", "Anexo VII", "0.6"),  # mel
    ("34011190", "Anexo VIII", "0.6"),  # sabonete
    ("07020000", "Anexo XV", "1"),  # tomate: hortícola, alíquota zero (também está no capítulo 7 do Anexo VII)
    ("11010010", "Anexo I", "1"),  # farinha de trigo: Anexo I ganha do item 4 do Anexo VII
])
def test_consulta_por_ncm(cliente, analista, ncm, anexo, reducao):
    r = _consulta(cliente, analista, ncm)
    assert r["anexo"] == anexo and Decimal(str(r["reducao"])) == Decimal(reducao)


@pytest.mark.parametrize("ncm", ["87089990", "02074300", "03021400", "07095100", "40111000"])
def test_sem_reducao(cliente, analista, ncm):
    # autopeça, foie gras, salmão, cogumelo (fora do Anexo XV, mas no capítulo 7 do Anexo VII) e pneu
    r = _consulta(cliente, analista, ncm)
    assert r is None or (ncm == "07095100" and r["anexo"] == "Anexo VII")


def _venda(n: int, ncm: str, valor: str) -> bytes:
    return (f'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe35{n:042d}"><ide><nNF>{n}</nNF>'
            f"<dhEmi>2026-07-10T10:00:00-03:00</dhEmi><tpNF>1</tpNF><indFinal>1</indFinal></ide>"
            f"<emit><CNPJ>{CNPJ}</CNPJ><enderEmit><UF>SP</UF></enderEmit><CRT>3</CRT></emit>"
            "<dest><CPF>12345678909</CPF><enderDest><UF>SP</UF></enderDest></dest>"
            f'<det nItem="1"><prod><cProd>P{n}</cProd><xProd>ITEM</xProd><NCM>{ncm}</NCM><CFOP>5102</CFOP><qCom>1</qCom>'
            f"<vUnCom>{valor}</vUnCom><vProd>{valor}</vProd></prod><imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST></ICMS00></ICMS>"
            "</imposto></det></infNFe></NFe></nfeProc>").encode()


def test_projecao_aplica_a_reducao_na_receita(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "MERCADO REFORMA LTDA", "cnpj": CNPJ, "regime_tributario": "LUCRO_PRESUMIDO", "uf": "SP"}).json()
    assert "id" in emp, emp
    pid = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-07", "competencia_final": "2026-07"}).json()["id"]
    for n, ncm in enumerate(["10063021", "04090000", "87089990"], start=1):  # arroz (zero), mel (60%), autopeça (cheia)
        cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador, files={"arquivo": (f"{n}.xml", _venda(n, ncm, "1000.00"))})
    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    passos = cliente.get(f"/api/simulacoes/{sim['id']}/memoria", headers=contador).json()
    passos = passos if isinstance(passos, list) else passos.get("passos", [])
    receita = next(p for p in passos if p["descricao"].startswith("Receita com CBS e IBS após as reduções"))
    # 1.000 × 0 + 1.000 × 0,4 + 1.000 × 1 = 1.400
    assert Decimal(str(receita["valor"])) == Decimal("1400")
    ncms = {v["ncm"]: v for v in cliente.get(f"/api/simulacoes/{sim['id']}", headers=contador).json()["resultado"]["verificacao_ncm"]}
    assert ncms["10063021"]["cst_ibs_cbs"] == "200" and ncms["10063021"]["cclass_trib"] == "200003"
    assert "alíquota zero" in ncms["10063021"]["beneficio_reforma"] and ncms["87089990"]["cst_ibs_cbs"] == "000"


def test_contador_inclui_reducao(cliente, contador, analista):
    corpo = {"ncm": "9021.10", "anexo": "Anexo IV", "item": "1", "descricao": "Artigos ortopédicos (teste)", "reducao": 0.6}
    assert cliente.post("/api/tabelas/reforma-reducoes", headers=analista, json=corpo).status_code == 403
    assert cliente.post("/api/tabelas/reforma-reducoes", headers=contador, json={**corpo, "reducao": 1.6}).status_code == 422
    assert cliente.post("/api/tabelas/reforma-reducoes", headers=contador, json=corpo).status_code == 201
    assert _consulta(cliente, contador, "90211010")["anexo"] == "Anexo IV"
