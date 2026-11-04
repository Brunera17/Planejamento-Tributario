"""Extrato do PGDAS-D: RBT12 e anexo declarados, lidos do PDF enviado em Documentos."""
import io
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services.pgdas import ler

CNPJ = "71563428000190"


def _extrato(atividade: str, rbt12: str = "1.380.250,75", pa: str = "06/2026") -> bytes:
    """PDF com as linhas que o extrato do PGDAS-D traz (período, RBT12 e atividade do estabelecimento)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for linha in ["Extrato do Simples Nacional", f"Período de Apuração (PA): {pa}",
                  "2.2) Receitas Brutas Anteriores", "Mercado Interno Mercado Externo Total",
                  f"Receita bruta acumulada nos doze meses anteriores ao PA (RBT12) {rbt12} 0,00 {rbt12}",
                  "2.8) Informações da Declaração por Estabelecimento", f"Atividade: {atividade}"]:
        c.drawString(40, y, linha)
        y -= 18
    c.save()
    return buf.getvalue()


def test_leitura_do_extrato():
    e = ler(_extrato("Revenda de mercadorias, exceto para o exterior - Sem substituição tributária"), "extrato.pdf")
    assert e.competencia == "2026-06" and e.rbt12 == Decimal("1380250.75") and e.anexos == {"I"}
    e = ler(_extrato("Venda de mercadorias industrializadas pelo contribuinte, exceto para o exterior"))
    assert e.anexos == {"II"}
    assert ler(b"nao e pdf").lido is False


def test_extrato_preenche_o_rbt12_e_avisa_anexo_diferente(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "EXTRATO PGDAS LTDA", "cnpj": CNPJ, "regime_tributario": "SIMPLES_NACIONAL", "uf": "SP",
        "cnae": "4530703", "atividade": "COMERCIO"}).json()
    assert emp["anexo_simples"] == "I"  # sugerido pelo CNAE de comércio
    pid = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-06", "competencia_final": "2026-06"}).json()["id"]
    tipos = cliente.get(f"/api/planejamentos/{pid}/documentos", headers=contador).json()["tipos"]
    tipo = next(t["id"] for t in tipos if "PGDAS" in t["nome"])
    pdf = _extrato("Venda de mercadorias industrializadas pelo contribuinte, exceto para o exterior")
    r = cliente.post(f"/api/planejamentos/{pid}/documentos/2026-06/{tipo}", headers=contador, files={"arquivo": ("extrato.pdf", pdf)})
    assert r.status_code == 201, r.text

    coleta = cliente.get(f"/api/planejamentos/{pid}/coleta", headers=contador).json()
    auto = coleta["premissas_auto"]["rbt12_informado"]
    assert Decimal(str(auto["valor"])) == Decimal("1380250.75") and "PGDAS-D de 06/2026" in auto["fonte"]

    venda = (f'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe35{1:042d}"><ide><nNF>1</nNF>'
             f"<dhEmi>2026-06-10T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide><emit><CNPJ>{CNPJ}</CNPJ><enderEmit><UF>SP</UF></enderEmit></emit>"
             "<dest><CNPJ>11222333000181</CNPJ><enderDest><UF>SP</UF></enderDest></dest>"
             '<det nItem="1"><prod><cProd>A</cProd><xProd>PECA</xProd><NCM>87089990</NCM><CFOP>5102</CFOP><qCom>1</qCom>'
             "<vUnCom>1000</vUnCom><vProd>1000.00</vProd></prod></det></infNFe></NFe></nfeProc>").encode()
    assert cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador, files={"arquivo": ("v.xml", venda)}).status_code == 200
    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    assert "declara Anexo II, mas o cálculo usa o Anexo I" in (sim.get("pendencias") or "")
