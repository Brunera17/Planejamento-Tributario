"""Movimento mensal pelos arquivos: XML de entrada preenche compras e devoluções; planilha padrão .xlsx."""
import io

import pytest
from openpyxl import Workbook, load_workbook

from app.services.relatorio_contabil import cfop_de_entrada

CNPJ = "71364528000198"  # fictício
FORNECEDOR = "33000167000101"
CLIENTE = "11222333000181"


def _nfe(n: int, emit: str, dest: str, cfop: int, valor: str, tp_nf: int = 1, mes: str = "08") -> bytes:
    chave = f"35{n:042d}"
    return (f'<?xml version="1.0" encoding="UTF-8"?><nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe>'
            f'<infNFe Id="NFe{chave}"><ide><nNF>{n}</nNF><dhEmi>2026-{mes}-10T10:00:00-03:00</dhEmi><tpNF>{tp_nf}</tpNF></ide>'
            f"<emit><CNPJ>{emit}</CNPJ><enderEmit><UF>SP</UF></enderEmit><CRT>3</CRT></emit>"
            f"<dest><CNPJ>{dest}</CNPJ><enderDest><UF>SP</UF></enderDest></dest>"
            f'<det nItem="1"><prod><cProd>P1</cProd><xProd>ITEM</xProd><NCM>22021000</NCM><CFOP>{cfop}</CFOP>'
            f"<qCom>1</qCom><vUnCom>{valor}</vUnCom><vProd>{valor}</vProd></prod><imposto><ICMS><ICMS00><orig>0</orig>"
            f"<CST>00</CST><pICMS>18</pICMS><vICMS>0</vICMS></ICMS00></ICMS></imposto></det>"
            f"</infNFe></NFe></nfeProc>").encode()


@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "MOVIMENTO MENSAL LTDA", "cnpj": CNPJ, "regime_tributario": "SIMPLES_NACIONAL", "uf": "SP"})
    assert emp.status_code == 201, emp.text
    return cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp.json()["id"], "competencia_inicial": "2026-08", "competencia_final": "2026-10"}).json()["id"]


def _xml(cliente, contador, pid, conteudo, nome="n.xml"):
    r = cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador, files={"arquivo": (nome, conteudo)})
    assert r.status_code == 200, r.text
    return r.json()


def _coleta(cliente, contador, pid):
    return cliente.get(f"/api/planejamentos/{pid}/coleta", headers=contador).json()


def test_cfop_do_fornecedor_vira_cfop_de_entrada():
    assert [cfop_de_entrada(c) for c in (5102, 6102, 5405, 6404, 5202, 1202, 5949)] == [1102, 2102, 1403, 2403, 1202, 1202, 1949]


def test_xml_de_entrada_preenche_compras_e_devolucoes(cliente, contador, pid):
    r = _xml(cliente, contador, pid, _nfe(1, FORNECEDOR, CNPJ, 5102, "1000.00"))
    assert r["importados"] == 1
    assert any("compras para revenda preenchidas com R$ 1.000,00" in a for a in r["avisos"])
    # devolução emitida pela própria empresa (nota de entrada, tpNF 0) e devolução emitida pelo cliente (CFOP 5202)
    _xml(cliente, contador, pid, _nfe(2, CNPJ, CLIENTE, 1202, "50.00", tp_nf=0))
    _xml(cliente, contador, pid, _nfe(3, CLIENTE, CNPJ, 5202, "30.00"))
    c = _coleta(cliente, contador, pid)
    assert float(c["compras"]["2026-08"]) == 1000
    assert float(c["devolucoes"]["2026-08"]) == 80

    # nota nova do mesmo mês atualiza o que veio das notas
    _xml(cliente, contador, pid, _nfe(4, FORNECEDOR, CNPJ, 5405, "500.00"))
    assert float(_coleta(cliente, contador, pid)["compras"]["2026-08"]) == 1500


def test_valor_digitado_nao_e_sobrescrito(cliente, contador, pid):
    assert cliente.put(f"/api/planejamentos/{pid}/compras", headers=contador,
                       json=[{"competencia": "2026-09", "valor": 777}]).status_code == 204
    r = _xml(cliente, contador, pid, _nfe(5, FORNECEDOR, CNPJ, 5102, "200.00", mes="09"))
    assert any("o valor informado foi mantido" in a for a in r["avisos"])
    assert float(_coleta(cliente, contador, pid)["compras"]["2026-09"]) == 777


def test_planilha_padrao_ida_e_volta(cliente, contador, pid):
    assert cliente.put(f"/api/planejamentos/{pid}/compras", headers=contador,
                       json=[{"competencia": "2026-09", "valor": 777}]).status_code == 204
    r = cliente.get(f"/api/planejamentos/{pid}/planilha-mensal", headers=contador)
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    linhas = [list(x) for x in ws.iter_rows(values_only=True)]
    assert linhas[0] == ["Competência", "Compras", "Devoluções", "Folha", "Pró-labore"]
    assert [x[0] for x in linhas[1:]] == ["08/2026", "09/2026", "10/2026"]

    wb = Workbook()
    ws = wb.active
    ws.append(linhas[0])
    ws.append(["10/2026", 1234.5, None, 3000, "1.500,00"])
    ws.append(["09/2026", None, 12, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    r = cliente.post(f"/api/planejamentos/{pid}/planilha-mensal", headers=contador,
                     files={"arquivo": ("mov.xlsx", buf.getvalue())})
    assert r.status_code == 200, r.text
    assert r.json() == {"competencias": ["2026-09", "2026-10"], "valores": 4}
    c = _coleta(cliente, contador, pid)
    assert float(c["compras"]["2026-10"]) == 1234.5
    assert float(c["compras"]["2026-09"]) == 777  # célula vazia não altera
    assert float(c["devolucoes"]["2026-09"]) == 12
    assert float(c["folha"]["2026-10"]["folha"]) == 3000 and float(c["folha"]["2026-10"]["pro_labore"]) == 1500


def test_planilha_fora_do_modelo_e_recusada(cliente, contador, pid):
    wb = Workbook()
    wb.active.append(["Mes", "Valor"])
    buf = io.BytesIO()
    wb.save(buf)
    r = cliente.post(f"/api/planejamentos/{pid}/planilha-mensal", headers=contador,
                     files={"arquivo": ("x.xlsx", buf.getvalue())})
    assert r.status_code == 422 and "modelo" in r.text


def test_nota_antiga_com_cfop_do_fornecedor_e_corrigida_na_reimportacao(cliente, contador, pid, fabrica_sessao):
    from sqlalchemy import select, update

    from app.models import NotaFiscal, NotaItem

    _xml(cliente, contador, pid, _nfe(30, FORNECEDOR, CNPJ, 5102, "400.00", mes="10"))
    with fabrica_sessao() as db:  # simula a importação de antes da correção: CFOP do fornecedor gravado
        ids = select(NotaFiscal.id).where(NotaFiscal.planejamento_id == pid, NotaFiscal.numero == "30")
        db.execute(update(NotaItem).where(NotaItem.nota_fiscal_id.in_(ids)).values(cfop=5102))
        db.commit()
    _xml(cliente, contador, pid, _nfe(30, FORNECEDOR, CNPJ, 5102, "400.00", mes="10"))
    with fabrica_sessao() as db:
        assert db.scalar(select(NotaItem.cfop).join(NotaFiscal).where(NotaFiscal.planejamento_id == pid,
                                                                      NotaFiscal.numero == "30")) == 1102


def test_planilha_com_competencia_repetida_ou_vazia_e_recusada(cliente, contador, pid):
    for linhas in ([["10/2026", 1, None, None, None], ["10/2026", 2, None, None, None]], [["10/2026", None, None, None, None]]):
        wb = Workbook()
        wb.active.append(["Competência", "Compras", "Devoluções", "Folha", "Pró-labore"])
        for l in linhas:
            wb.active.append(l)
        buf = io.BytesIO()
        wb.save(buf)
        r = cliente.post(f"/api/planejamentos/{pid}/planilha-mensal", headers=contador, files={"arquivo": ("x.xlsx", buf.getvalue())})
        assert r.status_code == 422, r.text
