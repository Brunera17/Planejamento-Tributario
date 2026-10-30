"""Caminho completo pela API: outras despesas, status dos levantamentos e regras de NCM/CFOP novas."""
import pytest

NFE = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe><infNFe Id="NFe35260912345678000195550010000000011000000011" versao="4.00">
<ide><nNF>1</nNF><dhEmi>2026-09-10T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>
<emit><CNPJ>12345678000195</CNPJ><enderEmit><UF>SP</UF></enderEmit></emit>
<dest><CPF>12345678909</CPF><enderDest><UF>SP</UF></enderDest></dest>
<det nItem="1"><prod><cProd>N1</cProd><xProd>PRODUTO NOVO</xProd><NCM>87087090</NCM><CFOP>5117</CFOP>
<qCom>1</qCom><vUnCom>500.00</vUnCom><vProd>500.00</vProd></prod><imposto><ICMS><ICMSSN102><CSOSN>102</CSOSN></ICMSSN102></ICMS></imposto></det>
</infNFe></NFe></nfeProc>"""
REGRA_NCM = {"ncm": "87087090", "monofasico": True, "confianca": "ALTA", "cst_ibs_cbs": "000", "cclass_trib": "000001"}


@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "FLUXO COMPLETO LTDA", "cnpj": "12.345.678/0001-95", "regime_tributario": "SIMPLES_NACIONAL",
        "anexo_simples": "I"}).json()
    return cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-09", "competencia_final": "2026-09"}).json()["id"]


def status(cliente, h, pid, novo, motivo=None):
    return cliente.post(f"/api/planejamentos/{pid}/status", headers=h, json={"status": novo, "motivo": motivo})


def test_outras_despesas_por_grupo(cliente, analista, pid):
    grupos = [g["id"] for g in cliente.get("/api/tabelas/catalogo-despesas", headers=analista).json()]
    r = cliente.put(f"/api/planejamentos/{pid}/levantamentos/2026-09", headers=analista, json={
        "outras": [{"grupo_id": grupos[0], "descricao": "Taxa de feira", "valor": "150.00"}],
        "grupos_sem_outras": grupos[1:]})
    assert r.status_code == 204
    lv = cliente.get(f"/api/planejamentos/{pid}/levantamentos/2026-09", headers=analista).json()
    assert lv["grupos_sem_outras"] == grupos[1:] and lv["outras"][0]["descricao"] == "Taxa de feira"
    blocos = cliente.get(f"/api/planejamentos/{pid}/progresso", headers=analista).json()["blocos"]
    assert next(b for b in blocos if b["codigo"] == "OUTRAS_DESPESAS")["preenchidos"] == len(grupos)


def test_ncm_e_cfop_novos_viram_pendencia_e_sao_resolvidos(cliente, contador, analista, pid):
    assert cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador,
                        files={"arquivo": ("n.xml", NFE.encode(), "text/xml")}).json()["importados"] == 1
    pendentes = cliente.get("/api/tabelas/ncm/pendentes", headers=analista).json()
    assert pendentes == [{"codigo": "87087090", "produto_exemplo": "PRODUTO NOVO", "valor": pytest.approx(500.0), "planejamentos": 1}]
    assert [c["codigo"] for c in cliente.get("/api/tabelas/cfop/pendentes", headers=analista).json()] == [5117]

    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    assert "NCM sem regra: 87087090" in sim["pendencias"] and "CFOP sem regra: 5117" in sim["pendencias"]

    assert cliente.put("/api/tabelas/ncm", headers=analista, json=REGRA_NCM).status_code == 403
    assert cliente.put("/api/tabelas/ncm", headers=contador, json=REGRA_NCM).status_code == 200
    assert cliente.put("/api/tabelas/cfop", headers=contador, json={
        "cfop": 5117, "natureza": "Venda em consignação", "gera_receita": True}).status_code == 200

    assert cliente.get("/api/tabelas/ncm/pendentes", headers=analista).json() == []
    lista = cliente.get(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    assert lista[0]["desatualizada"] is True  # a regra nova muda o cálculo
    blocos = cliente.get(f"/api/planejamentos/{pid}/progresso", headers=contador).json()["blocos"]
    assert next(b for b in blocos if b["codigo"] == "NCM")["preenchidos"] == 1
    assert cliente.get(f"/api/planejamentos/{pid}", headers=contador).json()["status"] == "EM_COLETA"  # simular não pula etapas


def test_status_trava_e_libera_os_meses(cliente, contador, analista, pid):
    cliente.post(f"/api/planejamentos/{pid}/observacoes/aceite", headers=analista)
    item = {"itens": [{"item_despesa_id": 1, "valor": "10.00"}]}
    url = f"/api/planejamentos/{pid}/levantamentos/2026-09"

    assert status(cliente, analista, pid, "EM_CONFERENCIA").status_code == 200
    assert cliente.get(url, headers=analista).json()["status"] == "ENVIADO"
    assert cliente.put(url, headers=analista, json=item).status_code == 409

    assert status(cliente, contador, pid, "EM_COLETA", "Faltou o extrato").status_code == 200
    assert cliente.get(url, headers=analista).json()["status"] == "EM_PREENCHIMENTO"
    assert cliente.put(url, headers=analista, json=item).status_code == 204
    historico = cliente.get(f"/api/planejamentos/{pid}/historico", headers=contador).json()
    assert (historico[-1]["motivo"], historico[-1]["usuario"]) == ("Faltou o extrato", "Contador Demonstração")

    assert status(cliente, analista, pid, "EM_CONFERENCIA").status_code == 200
    assert status(cliente, contador, pid, "PRONTO_PARA_SIMULAR").status_code == 200
    assert cliente.get(url, headers=analista).json()["status"] == "CONFERIDO"
    cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador)
    assert cliente.get(f"/api/planejamentos/{pid}", headers=contador).json()["status"] == "SIMULADO"


def test_nao_aprova_sem_passar_pela_conferencia(cliente, contador):
    from app.db.session import SessionLocal  # substituída pela sessão de teste no conftest
    from app.models import Empresa, Planejamento
    from app.seeds.exemplo import CNPJ, carregar_exemplo

    with SessionLocal() as db:
        p = carregar_exemplo(db)
        db.commit()
        assert db.get(Empresa, p.empresa_id).cnpj == CNPJ
        estado_original = p.status
        db.get(Planejamento, p.id).status = "EM_COLETA"
        db.commit()
    sim = cliente.post(f"/api/planejamentos/{p.id}/simulacoes", headers=contador).json()
    r = cliente.post(f"/api/simulacoes/{sim['id']}/aprovar", headers=contador)
    assert r.status_code == 422 and "conferência" in r.json()["erro"]
    with SessionLocal() as db:
        db.get(Planejamento, p.id).status = estado_original
        db.commit()


@pytest.fixture(scope="module")
def pid_premissas(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "PREMISSAS LTDA", "cnpj": "98.765.432/0001-98", "regime_tributario": "LUCRO_PRESUMIDO"}).json()
    return cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-09", "competencia_final": "2026-09"}).json()["id"]


@pytest.mark.parametrize("corpo,campo", [
    ({"rbt12_informado": "abc"}, "rbt12_informado"),
    ({"adicoes_lr": "-5"}, "adicoes_lr"),
    ({"pct_compras_credito_ibs_cbs": "1.5"}, "pct_compras_credito_ibs_cbs"),
    ({"credito_frete_integral": "sim"}, "credito_frete_integral"),
    ({"estoque_inicial": "1000"}, "estoque_final"),
    ({"inexistente": "1"}, "inexistente"),
])
def test_premissa_invalida(cliente, contador, pid_premissas, corpo, campo):
    r = cliente.put(f"/api/planejamentos/{pid_premissas}/premissas", headers=contador, json=corpo)
    assert r.status_code == 422 and campo in r.json()["campos"]


def test_premissas_gravam_limpam_e_exigem_contador(cliente, contador, analista, pid_premissas):
    url = f"/api/planejamentos/{pid_premissas}/premissas"
    assert cliente.put(url, headers=analista, json={"rbt12_informado": "1000"}).status_code == 403
    corpo = {"rbt12_informado": "2400000.00", "estoque_inicial": "100", "estoque_final": "150", "credito_frete_integral": True}
    assert cliente.put(url, headers=contador, json=corpo).status_code == 204
    pr = cliente.get(f"/api/planejamentos/{pid_premissas}/coleta", headers=contador).json()["premissas"]
    assert pr["rbt12_informado"] == "2400000.00" and pr["credito_frete_integral"] is True
    assert cliente.put(url, headers=contador, json={"estoque_inicial": None, "estoque_final": ""}).status_code == 204
    pr = cliente.get(f"/api/planejamentos/{pid_premissas}/coleta", headers=contador).json()["premissas"]
    assert "estoque_inicial" not in pr and "estoque_final" not in pr


def test_origem_das_compras_muda_credito_e_aviso(cliente, contador, pid_premissas):
    nfe = NFE.replace("12345678000195", "98765432000198").replace("87087090", "85113020").replace("5117", "5102") \
        .replace("NFe35260912345678000195", "NFe35260998765432000198")
    cliente.post(f"/api/planejamentos/{pid_premissas}/nfe", headers=contador, files={"arquivo": ("n.xml", nfe.encode(), "text/xml")})
    cliente.put(f"/api/planejamentos/{pid_premissas}/compras", headers=contador, json=[{"competencia": "2026-09", "valor": "100.00"}])

    def simular():
        sim = cliente.post(f"/api/planejamentos/{pid_premissas}/simulacoes", headers=contador).json()
        return cliente.get(f"/api/simulacoes/{sim['id']}", headers=contador).json()["resultado"]

    assumido = simular()
    assert assumido["base"]["2026-09"]["icms_credito"] == pytest.approx(18.0)
    assert any("não informada" in p["texto"] for p in assumido["pontos_criticos"])

    r = cliente.put(f"/api/planejamentos/{pid_premissas}/composicao-compras", headers=contador, json=[
        {"origem": "Internas", "aliquota": "0.18", "percentual": "0.5"}, {"origem": "Importados", "aliquota": "0.04", "percentual": "0.4"}])
    assert r.status_code == 422  # soma 90%
    r = cliente.put(f"/api/planejamentos/{pid_premissas}/composicao-compras", headers=contador, json=[
        {"origem": "Internas", "aliquota": "0.18", "percentual": "0.5"}, {"origem": "Importados", "aliquota": "0.04", "percentual": "0.5"}])
    assert r.status_code == 204

    informado = simular()
    assert informado["base"]["2026-09"]["icms_credito"] == pytest.approx(11.0)
    assert not any("não informada" in p["texto"] for p in informado["pontos_criticos"])
