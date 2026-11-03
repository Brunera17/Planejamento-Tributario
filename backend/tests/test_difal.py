"""DIFAL das vendas a consumidor final não contribuinte de outro estado (EC 87/2015, LC 190/2022)."""
from decimal import Decimal

import pytest

from app.motor.icms import difal_item
from app.motor.tipos import DestinoDifal
from app.services.entrada import _difal
from app.services.nfe_xml import ler_xml

CNPJ = "50948371000178"


def test_base_dupla_e_base_unica():
    # R$ 1.000 de SP para a BA (20,5%) a 7%: base = 930 ÷ 0,795 = 1.169,81; DIFAL = 239,81 − 70 = 169,81
    assert difal_item(Decimal("1000"), Decimal("0.07"), DestinoDifal("BA", Decimal("0.205"))).quantize(Decimal("0.01")) == Decimal("169.81")
    assert difal_item(Decimal("1000"), Decimal("0.07"), DestinoDifal("BA", Decimal("0.205"), base_dupla=False)) == Decimal("135.000")
    # RJ: 20% + 2% de FCP sobre a mesma base
    rj = difal_item(Decimal("1000"), Decimal("0.12"), DestinoDifal("RJ", Decimal("0.20"), Decimal("0.02")))
    assert rj.quantize(Decimal("0.01")) == Decimal("128.21")
    # importado a 4% para MG (18%)
    assert difal_item(Decimal("1000"), Decimal("0.04"), DestinoDifal("MG", Decimal("0.18"))).quantize(Decimal("0.01")) == Decimal("170.73")


class _Aliq:
    def __init__(self, uf, aliquota, inicio, fim=None):
        from datetime import date
        self.uf, self.aliquota, self.fcp, self.base_dupla = uf, Decimal(aliquota), Decimal("0"), True
        self.vigencia_inicio, self.vigencia_fim = date.fromisoformat(inicio), date.fromisoformat(fim) if fim else None


def test_quem_paga_e_qual_aliquota_vale():
    destinos = {"AL": [_Aliq("AL", "0.19", "2000-01-01", "2026-03-31"), _Aliq("AL", "0.205", "2026-04-01")]}
    assert _difal(destinos, "SP", "AL", "2026-03", True, False).aliquota == Decimal("0.19")
    assert _difal(destinos, "SP", "AL", "2026-04", True, False).aliquota == Decimal("0.205")
    assert _difal(destinos, "SP", "AL", "2026-04", True, None) is not None  # consumidor final sem indIEDest: pessoa física
    assert _difal(destinos, "SP", "AL", "2026-04", True, True) is None  # contribuinte: o destinatário recolhe
    assert _difal(destinos, "SP", "AL", "2026-04", False, False) is None  # revenda
    assert _difal(destinos, "SP", "SP", "2026-04", True, False) is None


@pytest.mark.parametrize("dest, esperado", [
    ("<CPF>12345678909</CPF>", False),
    ("<CNPJ>11222333000181</CNPJ><indIEDest>1</indIEDest>", True),
    ("<CNPJ>11222333000181</CNPJ><indIEDest>9</indIEDest>", False),
    ("<CNPJ>11222333000181</CNPJ><indIEDest>2</indIEDest>", False),
    ("<CNPJ>11222333000181</CNPJ>", None),
])
def test_leitura_do_contribuinte(dest, esperado):
    xml = (f'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe{"1" * 44}"><ide><nNF>1</nNF>'
           f"<dhEmi>2026-07-01T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide><emit><CNPJ>{CNPJ}</CNPJ></emit><dest>{dest}</dest>"
           "</infNFe></NFe></nfeProc>").encode()
    assert ler_xml(xml).dest_contribuinte is esperado


def _venda(n: int, uf: str, dest: str, ind_final: str = "1") -> bytes:
    return (f'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe35{n:042d}"><ide><nNF>{n}</nNF>'
            f"<dhEmi>2026-07-10T10:00:00-03:00</dhEmi><tpNF>1</tpNF><indFinal>{ind_final}</indFinal></ide>"
            f"<emit><CNPJ>{CNPJ}</CNPJ><enderEmit><UF>SP</UF></enderEmit><CRT>3</CRT></emit>"
            f"<dest>{dest}<enderDest><UF>{uf}</UF></enderDest></dest>"
            '<det nItem="1"><prod><cProd>A</cProd><xProd>PECA</xProd><NCM>87089990</NCM><CFOP>6108</CFOP><qCom>1</qCom>'
            "<vUnCom>1000</vUnCom><vProd>1000.00</vProd></prod><imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST>"
            "<pICMS>7</pICMS><vICMS>70</vICMS></ICMS00></ICMS></imposto></det></infNFe></NFe></nfeProc>").encode()


def test_difal_entra_no_icms_do_lucro_presumido_e_nao_no_simples(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "DIFAL LTDA", "cnpj": CNPJ, "regime_tributario": "LUCRO_PRESUMIDO", "uf": "SP"}).json()
    pid = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-07", "competencia_final": "2026-07"}).json()["id"]
    for n, xml in enumerate([_venda(1, "BA", "<CPF>12345678909</CPF>"),
                             _venda(2, "BA", "<CNPJ>11222333000181</CNPJ><indIEDest>1</indIEDest>", "0")], start=1):
        assert cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador, files={"arquivo": (f"{n}.xml", xml)}).status_code == 200
    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    r = cliente.get(f"/api/simulacoes/{sim['id']}", headers=contador).json()["resultado"]
    # só a venda a pessoa física paga DIFAL: 169,81 para a BA
    assert Decimal(str(r["base"]["TOTAL"]["icms_difal"])).quantize(Decimal("0.01")) == Decimal("169.81")
    assert any(pc["codigo"] == "DIFAL" and "BA" in pc["texto"] for pc in r["pontos_criticos"])
    memoria = cliente.get(f"/api/simulacoes/{sim['id']}/memoria", headers=contador)
    if memoria.status_code == 200:
        assert any("DIFAL" in str(m) for m in memoria.json())


def test_nova_aliquota_fecha_a_anterior(cliente, contador, analista):
    corpo = {"aliquota": 0.21, "fcp": 0, "base_dupla": True, "vigencia_inicio": "2027-01-01", "fonte": "Lei de teste 1/2026"}
    assert cliente.post("/api/tabelas/aliquotas-uf/TO", headers=analista, json=corpo).status_code == 403
    assert cliente.post("/api/tabelas/aliquotas-uf/TO", headers=contador, json={**corpo, "aliquota": 2.1}).status_code == 422
    assert cliente.post("/api/tabelas/aliquotas-uf/TO", headers=contador, json={**corpo, "vigencia_inicio": "1999-01-01"}).status_code == 422
    assert cliente.post("/api/tabelas/aliquotas-uf/TO", headers=contador, json=corpo).status_code == 201
    to = [a for a in cliente.get("/api/tabelas/aliquotas-uf", headers=contador).json() if a["uf"] == "TO"]
    assert [(a["vigencia_fim"], Decimal(str(a["aliquota"]))) for a in to] == [("2026-12-31", Decimal("0.2")), (None, Decimal("0.21"))]
