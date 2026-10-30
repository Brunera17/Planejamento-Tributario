"""Fluxo completo pela API, sobre o planejamento de demonstração carregado no banco."""
import io

import pytest
from openpyxl import load_workbook


@pytest.fixture(scope="module")
def pid(cliente, contador):
    lista = cliente.get("/api/planejamentos", headers=contador).json()
    return next(p["id"] for p in lista if p["cnpj"] == "11222333000181")


def test_login_invalido(cliente):
    r = cliente.post("/api/auth/login", json={"usuario": "contador", "senha": "errada"})
    assert r.status_code == 401
    assert r.json()["erro"] == "Usuário ou senha inválidos"


def test_rota_exige_autenticacao(cliente):
    assert cliente.get("/api/empresas").status_code == 401


def test_analista_nao_cadastra_empresa(cliente, analista):
    r = cliente.post("/api/empresas", headers=analista, json={
        "razao_social": "X", "cnpj": "11444777000161", "regime_tributario": "LUCRO_REAL"})
    assert r.status_code == 403


def test_validacao_padronizada(cliente, contador):
    r = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "Empresa Teste", "cnpj": "11.444.777/0001-62", "regime_tributario": "LUCRO_REAL"})
    assert r.status_code == 422
    assert "cnpj" in r.json()["campos"]


def test_cadastra_empresa_cnpj_com_mascara(cliente, contador):
    r = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "Empresa Teste", "cnpj": "11.444.777/0001-61", "regime_tributario": "Lucro_Real".upper(),
        "telefone": "(11) 3333-4444"})
    assert r.status_code == 201, r.text
    assert r.json()["cnpj"] == "11444777000161"
    assert r.json()["telefone"] == "1133334444"


def test_progresso_tem_pendencias(cliente, contador, pid):
    r = cliente.get(f"/api/planejamentos/{pid}/progresso", headers=contador).json()
    assert 0 < r["progresso"] < 100
    blocos = {b["codigo"]: b for b in r["blocos"]}
    assert blocos["SAIDAS"]["preenchidos"] == 3
    assert (blocos["NCM"]["preenchidos"], blocos["NCM"]["esperados"]) == (0, 5)  # condicionais da lei aguardam o contador
    assert blocos["FOLHA"]["preenchidos"] == 0


def test_simulacao_reproduz_planilha(cliente, analista, pid):
    r = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=analista)
    assert r.status_code == 201, r.text
    sim = r.json()
    assert sim["tipo"] == "PRELIMINAR"  # progresso < 100%
    assert sim["regime_recomendado"] == "LUCRO_PRESUMIDO"

    res = cliente.get(f"/api/simulacoes/{sim['id']}", headers=analista).json()["resultado"]
    totais = {c["regime"]: c["total"] for c in res["comparativo"]}
    assert totais["SIMPLES_NACIONAL"] == pytest.approx(63688.26, abs=0.01)
    assert totais["LUCRO_PRESUMIDO"] == pytest.approx(59765.84, abs=0.01)
    assert totais["LUCRO_REAL"] == pytest.approx(61192.34, abs=0.01)
    ncms = {n["ncm"]: n for n in res["verificacao_ncm"]}
    assert len(ncms) == 18 and sum(n["requer_revisao"] for n in ncms.values()) == 5
    assert "confirme o Ex" in ncms["40169990"]["acao_recomendada"]
    assert ncms["73181500"]["acao_recomendada"] == "Fora dos anexos: tributação normal."
    ops = {o["codigo"]: o for o in res["oportunidades"]}
    assert ops["CPP_DAS"]["impacto"] == pytest.approx(29907.67, abs=0.01)

    memoria = cliente.get(f"/api/simulacoes/{sim['id']}/memoria?secao=Lucro Real", headers=analista).json()
    assert any(p["descricao"] == "(=) LAIR" for p in memoria)


def test_dado_alterado_desatualiza_simulacao(cliente, contador, pid):
    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    r = cliente.put(f"/api/planejamentos/{pid}/folha", headers=contador,
                    json=[{"competencia": "2026-06", "folha": "0", "pro_labore": "0"}])
    assert r.status_code == 204
    lista = cliente.get(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    assert next(s for s in lista if s["id"] == sim["id"])["desatualizada"] is True
    r = cliente.post(f"/api/simulacoes/{sim['id']}/aprovar", headers=contador)
    assert r.status_code == 422


def test_crescimento_personalizado(cliente, contador, pid):
    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    linhas = cliente.get(f"/api/simulacoes/{sim['id']}/crescimento?rbt12=5000000&rbt12=1000000",
                         headers=contador).json()
    assert [l["rbt12"] for l in linhas] == [1000000, 5000000]
    assert linhas[1]["aliquota_simples"] is None  # acima do teto


def test_excel_somente_contador(cliente, contador, analista, pid):
    sim = cliente.get(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()[0]
    assert cliente.get(f"/api/simulacoes/{sim['id']}/excel", headers=analista).status_code == 403
    r = cliente.get(f"/api/simulacoes/{sim['id']}/excel", headers=contador)
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert {"Comparativo 3 Regimes", "Base da Operação", "Lucro Real", "Reforma 2026-2033",
            "Memória de Cálculo"} <= set(wb.sheetnames)


def test_transicao_de_status(cliente, contador, analista):
    emp = cliente.get("/api/empresas?busca=Empresa Teste", headers=contador).json()[0]
    p = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-07", "competencia_final": "2026-09"}).json()
    r = cliente.post(f"/api/planejamentos/{p['id']}/status", headers=analista, json={"status": "PRONTO_PARA_SIMULAR"})
    assert r.status_code == 422
    r = cliente.post(f"/api/planejamentos/{p['id']}/status", headers=analista, json={"status": "EM_CONFERENCIA"})
    assert r.status_code == 409 and "observações" in r.json()["erro"]
    assert cliente.get(f"/api/planejamentos/{p['id']}/observacoes", headers=analista).json()["aceitas_em"] is None
    assert cliente.post(f"/api/planejamentos/{p['id']}/observacoes/aceite", headers=analista).status_code == 204
    obs = cliente.get(f"/api/planejamentos/{p['id']}/observacoes", headers=analista).json()
    assert len(obs["textos"]) == 3 and obs["aceitas_por"] == "Analista Demonstração"
    assert cliente.post(f"/api/planejamentos/{p['id']}/status", headers=analista,
                        json={"status": "EM_CONFERENCIA"}).status_code == 200
    assert cliente.post(f"/api/planejamentos/{p['id']}/status", headers=analista,
                        json={"status": "PRONTO_PARA_SIMULAR"}).status_code == 403
    assert cliente.post(f"/api/planejamentos/{p['id']}/status", headers=contador,
                        json={"status": "EM_COLETA"}).status_code == 422  # falta motivo


NFE = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe><infNFe Id="NFe35260711444777000161550010000001231000001234" versao="4.00">
<ide><nNF>123</nNF><dhEmi>2026-07-15T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>
<emit><CNPJ>11444777000161</CNPJ><enderEmit><UF>SP</UF></enderEmit></emit>
<dest><CPF>12345678909</CPF><enderDest><UF>RJ</UF></enderDest></dest>
<det nItem="1"><prod><cProd>A1</cProd><xProd>BOBINA IGNICAO</xProd><NCM>85113020</NCM><CFOP>6108</CFOP>
<qCom>2</qCom><vUnCom>100.00</vUnCom><vProd>200.00</vProd><vDesc>10.00</vDesc><vFrete>5.00</vFrete></prod>
<imposto><ICMS><ICMSSN102><CSOSN>102</CSOSN></ICMSSN102></ICMS></imposto></det>
</infNFe></NFe></nfeProc>"""


def test_importa_xml_nfe(cliente, contador):
    p = next(x for x in cliente.get("/api/planejamentos", headers=contador).json() if x["cnpj"] == "11444777000161")
    arq = {"arquivo": ("nota.xml", NFE.encode(), "text/xml")}
    r = cliente.post(f"/api/planejamentos/{p['id']}/nfe", headers=contador, files=arq).json()
    assert (r["importados"], r["ignorados"]) == (1, 0)
    r = cliente.post(f"/api/planejamentos/{p['id']}/nfe", headers=contador, files=arq).json()
    assert r["ignorados"] == 1 and "já importada" in r["log"][0]
    coleta = cliente.get(f"/api/planejamentos/{p['id']}/coleta", headers=contador).json()
    assert coleta["saidas"][0]["valor"] == pytest.approx(195.00)


def test_dashboard(cliente, analista):
    d = cliente.get("/api/dashboard", headers=analista).json()
    assert d["empresas_ativas"] >= 2
    assert d["economia_anual_estimada"] > 0


def test_aceite_conta_no_progresso_e_nao_desatualiza_simulacao(cliente, contador, pid):
    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    assert cliente.post(f"/api/planejamentos/{pid}/observacoes/aceite", headers=contador).status_code == 204
    blocos = cliente.get(f"/api/planejamentos/{pid}/progresso", headers=contador).json()["blocos"]
    assert next(b for b in blocos if b["codigo"] == "OBSERVACOES")["preenchidos"] == 1
    lista = cliente.get(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    assert next(s for s in lista if s["id"] == sim["id"])["desatualizada"] is False
