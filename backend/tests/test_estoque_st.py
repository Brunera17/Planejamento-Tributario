"""Crédito do ICMS-ST do estoque das autopeças que saíram da ST em SP em 1º/10/2026 (Portaria CAT 28/2020)."""
import io
import zipfile
from decimal import Decimal

import pytest

from app.services.estoque_st import credito_item

CNPJ = "19131243000197"
AL = Decimal("0.18")


def _nfe(n: int, dia: str, emitente: str, uf_emit: str, crt: str, icms: str, ncm: str = "87089990", vprod: str = "1000.00") -> bytes:
    chave = f"35{n:042d}"
    return (f'<?xml version="1.0" encoding="UTF-8"?><nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe>'
            f'<infNFe Id="NFe{chave}"><ide><nNF>{n}</nNF><dhEmi>{dia}T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>'
            f"<emit><CNPJ>{emitente}</CNPJ><enderEmit><UF>{uf_emit}</UF></enderEmit><CRT>{crt}</CRT></emit>"
            f"<dest><CNPJ>{CNPJ}</CNPJ><enderDest><UF>SP</UF></enderDest></dest>"
            f'<det nItem="1"><prod><cProd>X{n}</cProd><xProd>PECA</xProd><NCM>{ncm}</NCM><CFOP>5405</CFOP><qCom>10</qCom>'
            f"<vUnCom>100</vUnCom><vProd>{vprod}</vProd></prod><imposto><ICMS>{icms}</ICMS></imposto></det>"
            f"</infNFe></NFe></nfeProc>").encode()


def _zip(*xmls: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i, x in enumerate(xmls):
            z.writestr(f"n{i}.xml", x)
    return buf.getvalue()


@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "ESTOQUE ST LTDA", "cnpj": CNPJ, "regime_tributario": "LUCRO_PRESUMIDO", "uf": "SP"}).json()
    return cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-08", "competencia_final": "2026-09"}).json()["id"]


def test_formulas_dos_anexos():
    # RPA comprando de substituído (CST 60): BC ST × alíquota
    assert credito_item(True, "60", "3", False, Decimal("1500"), Decimal("1000"), AL, Decimal("0.12"))[0] == Decimal("270")
    # RPA comprando de fornecedor do Simples de SP que reteve: (BC ST − mercadoria) × alíquota
    assert credito_item(True, "201", "1", False, Decimal("1500"), Decimal("1000"), AL, Decimal("0.12"))[0] == Decimal("90")
    # RPA, fornecedor do Simples de outro estado: BC ST × interna − mercadoria × interestadual
    assert credito_item(True, "201", "1", True, Decimal("1500"), Decimal("1000"), AL, Decimal("0.12"))[0] == Decimal("150")
    # detentor do Simples: (BC ST − mercadoria) × alíquota, qualquer fornecedor
    assert credito_item(False, "60", "3", False, Decimal("1500"), Decimal("1000"), AL, Decimal("0.12"))[0] == Decimal("90")


def test_sem_entradas_com_st_nao_ha_estimativa(cliente, contador, pid):
    venda = _nfe(1, "2026-08-10", CNPJ, "SP", "3", "<ICMS00><orig>0</orig><CST>00</CST><vICMS>180</vICMS></ICMS00>").replace(
        f"<dest><CNPJ>{CNPJ}</CNPJ>".encode(), b"<dest><CNPJ>11222333000181</CNPJ>")
    cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador, files={"arquivo": ("v.xml", venda)})
    e = cliente.get(f"/api/planejamentos/{pid}/estoque-st", headers=contador).json()
    assert e["corte"] == "2026-09-30" and "Autopeças" in e["segmentos"] and e["norma"] == "Portaria SRE 34/2026 (SP)"
    assert e["taxa"] is None and e["credito"] is None


def test_credito_estimado_e_parcelas(cliente, contador, pid):
    st60 = "<ICMS60><orig>0</orig><CST>60</CST><vBCSTRet>1500.00</vBCSTRet><pST>18</pST><vICMSSTRet>90.00</vICMSSTRet></ICMS60>"
    sem_base = "<ICMS60><orig>0</orig><CST>60</CST></ICMS60>"
    r = cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador, files={"arquivo": ("e.zip", _zip(
        _nfe(2, "2026-09-05", "33000167000101", "SP", "3", st60),
        _nfe(3, "2026-09-06", "33000167000101", "SP", "3", sem_base),
        _nfe(4, "2026-09-07", "33000167000101", "SP", "3", st60, ncm="40111000"),  # pneu: também saiu em 1º/10
    ))})
    assert r.status_code == 200, r.text

    e = cliente.put(f"/api/planejamentos/{pid}/estoque-st", headers=contador, json={"valor": 54500}).json()
    # duas entradas com base: crédito 270 cada sobre custo de 1.090 (mercadoria + ST) = 24,77% do custo
    assert len(e["entradas"]) == 2 and e["sem_base"] == 1
    assert Decimal(str(e["taxa"])).quantize(Decimal("0.0001")) == Decimal("0.2477")
    assert Decimal(str(e["credito"])) == Decimal("13500.00")
    assert len(e["parcelas"]) == 12 and e["parcelas"][0]["competencia"] == "2026-10"
    assert sum(Decimal(str(x["valor"])) for x in e["parcelas"]) == Decimal("13500.00")

    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    ops = cliente.get(f"/api/simulacoes/{sim['id']}", headers=contador).json()["resultado"]["oportunidades"]
    op = next(o for o in ops if o["codigo"] == "CREDITO_ESTOQUE_ST")
    assert Decimal(str(op["impacto"])) == Decimal("13500.00") and "30/09/2026" in op["acao"]


def test_reimportar_completa_a_base_da_st(cliente, contador, pid):
    from app.db.session import SessionLocal  # substituída pela sessão de teste no conftest
    from app.models import NotaItem
    with SessionLocal() as db:
        db.query(NotaItem).filter(NotaItem.bc_st.is_not(None)).update({"bc_st": None, "vl_icms_st": None})
        db.commit()
    st60 = "<ICMS60><orig>0</orig><CST>60</CST><vBCSTRet>1500.00</vBCSTRet><vICMSSTRet>90.00</vICMSSTRet></ICMS60>"
    r = cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador,
                     files={"arquivo": ("e.xml", _nfe(2, "2026-09-05", "33000167000101", "SP", "3", st60))}).json()
    assert "base do ICMS-ST completada em 1 item" in r["log"][0]
    assert len(cliente.get(f"/api/planejamentos/{pid}/estoque-st", headers=contador).json()["entradas"]) == 1
