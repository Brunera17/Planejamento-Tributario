"""Envio em lote de documentos: tipo e mês sugeridos pelo conteúdo ou pelo nome, sem gravar nada."""
import io
import zipfile

import pytest
from openpyxl import Workbook

from app.services.classificacao_documentos import (
    APLICACAO,
    ENTRADAS,
    EXTRATO,
    FINANCEIRO,
    INVENTARIO,
    MARKETPLACE,
    PGDAS,
    SAIDAS,
    classificar,
)
from tests.test_pgdas import _extrato
from tests.test_relatorio_contabil import gerar

CNPJ = "48217593000179"
OUTRO = "33000167000101"
COMPS = ["2026-07", "2026-08", "2026-09"]


def _nfe(n: int, emitente: str, destinatario: str, data: str = "2026-08-10") -> bytes:
    return (f'<?xml version="1.0" encoding="UTF-8"?><nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe>'
            f'<infNFe Id="NFe35{n:042d}"><ide><nNF>{n}</nNF><dhEmi>{data}T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>'
            f"<emit><CNPJ>{emitente}</CNPJ><enderEmit><UF>SP</UF></enderEmit><CRT>3</CRT></emit>"
            f"<dest><CNPJ>{destinatario}</CNPJ><enderDest><UF>SP</UF></enderDest></dest>"
            f'<det nItem="1"><prod><cProd>P1</cProd><xProd>PECA</xProd><NCM>87089990</NCM><CFOP>5102</CFOP>'
            f"<qCom>1</qCom><vUnCom>100</vUnCom><vProd>100.00</vProd></prod><imposto><ICMS><ICMS00><orig>0</orig>"
            f"<CST>00</CST></ICMS00></ICMS></imposto></det></infNFe></NFe></nfeProc>").encode()


def _zip(*xmls: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i, x in enumerate(xmls):
            z.writestr(f"n{i}.xml", x)
    return buf.getvalue()


def _planilha(*linhas) -> bytes:
    wb = Workbook()
    for linha in linhas:
        wb.active.append(list(linha))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_nfe_emitida_e_recebida():
    s = classificar("notas.xml", _nfe(1, CNPJ, OUTRO), CNPJ, COMPS)
    assert (s.tipo, s.competencia) == (SAIDAS, "2026-08")
    s = classificar("compras.zip", _zip(_nfe(1, OUTRO, CNPJ, "2026-07-03"), _nfe(2, OUTRO, CNPJ, "2026-09-01"),
                                        _nfe(3, OUTRO, CNPJ, "2026-09-02")), CNPJ, COMPS)
    assert (s.tipo, s.competencia, s.competencias_no_arquivo) == (ENTRADAS, "2026-09", ["2026-07", "2026-09"])


def test_pgdas_pelo_periodo_de_apuracao():
    s = classificar("qualquer.pdf", _extrato("Revenda de mercadorias", pa="07/2026"), CNPJ, COMPS)
    assert (s.tipo, s.competencia) == (PGDAS, "2026-07")
    # declaração (não o extrato): o período vem com o dia, e o nome do arquivo não ajuda
    s = classificar("doc.pdf", _extrato("Revenda de mercadorias", pa="01/08/2026 a 31/08/2026"), CNPJ, COMPS)
    assert (s.tipo, s.competencia, s.competencias_no_arquivo) == (PGDAS, "2026-08", ["2026-08"])


def test_relatorio_da_dominio():
    s = classificar("rel.xls", gerar("Entradas", "08", [(1, 5, "PECA", 1102, "87089990", 1, 10, 10, 0)]), CNPJ, COMPS)
    assert (s.tipo, s.competencia) == (ENTRADAS, "2026-08")


@pytest.mark.parametrize("nome,conteudo,tipo,comp", [
    ("Extrato CDB set-2026.pdf", b"%PDF-1.4", APLICACAO, "2026-09"),
    ("extrato_banco_07_2026.csv", b"data;valor\n", EXTRATO, "2026-07"),
    ("planilha.xlsx", _planilha(["Inventário de estoque em 31/08/2026"], ["Produto", "Qtde"]), INVENTARIO, "2026-08"),
    ("documento.csv", b"Saldo anterior;10\n05/09/2026;20\n", EXTRATO, "2026-09"),
    # como no extrato do Banco do Brasil: título no topo; tarifa e aplicação automática no meio
    ("documento.csv", "Extrato de Conta Corrente\n05/09/2026;Tarifa pacote de serviços\n06/09/2026;BB Rende Fácil\n"
     "Total Aplicações Financeiras\n".encode(), EXTRATO, "2026-09"),
    ("Banco_do_Brasil_09_2026.csv", b"x", EXTRATO, "2026-09"),
    ("documento.csv", "Extrato de Aplicação Financeira\n30/09/2026;CDB\n".encode(), APLICACAO, "2026-09"),
    ("documento.csv", b"Relatorio de tarifas de venda\n10/08/2026;Comissao\n", MARKETPLACE, "2026-08"),
])
def test_palavras_chave_no_nome_ou_no_conteudo(nome, conteudo, tipo, comp):
    s = classificar(nome, conteudo, CNPJ, COMPS)
    assert (s.tipo, s.competencia) == (tipo, comp)


def test_nao_reconhecido_e_mes_fora_do_periodo_ficam_em_branco():
    s = classificar("IMG_0042.jpg", b"\xff\xd8\xff", CNPJ, COMPS)
    assert s.tipo is None and s.competencia is None and "escolha" in s.motivo
    assert classificar("extrato 01-2025.csv", b"x", CNPJ, COMPS).competencia is None


def test_rota_classifica_sem_gravar(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "LOTE DOCS LTDA", "cnpj": CNPJ, "regime_tributario": "LUCRO_REAL"}).json()
    pid = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-07", "competencia_final": "2026-09"}).json()["id"]
    r = cliente.post(f"/api/planejamentos/{pid}/documentos/classificar", headers=contador, files=[
        ("arquivos", ("vendas.xml", _nfe(1, CNPJ, OUTRO))), ("arquivos", ("x.exe", b"MZ"))])
    assert r.status_code == 200
    ok, ruim = r.json()
    tipos = {t["nome"]: t["id"] for t in cliente.get(f"/api/planejamentos/{pid}/documentos", headers=contador).json()["tipos"]}
    assert ok["tipo_documento_id"] == tipos[SAIDAS] and ok["competencia"] == "2026-08"
    assert "erro" in ruim
    assert cliente.get(f"/api/planejamentos/{pid}/documentos", headers=contador).json()["documentos"] == []


def _xls_como_dominio(xls: bytes, blanks: int = 300) -> bytes:
    """Imita o .xls da Domínio: registros BLANK soltos entre a área global e a aba, com o endereço da aba
    apontando para eles. O Excel abre; o xlrd sozinho recusa ("Expected BOF record")."""
    import struct

    from xlrd import compdoc
    from xlwt.CompoundDoc import XlsDoc

    s = compdoc.CompDoc(xls, logfile=io.StringIO()).get_named_stream("Workbook")
    pos, sheets = 0, []
    while True:
        tipo, tam = struct.unpack_from("<HH", s, pos)
        if tipo == 0x0085:
            sheets.append(pos)
        pos += 4 + tam
        if tipo == 0x000A:
            break
    lixo = struct.pack("<HHHHH", 0x0201, 6, 0, 0, 15) * blanks
    novo = bytearray(s[:pos] + lixo + s[pos:])
    for p in sheets:  # abas que vinham depois continuam no lugar certo; a primeira aponta para o lixo
        antigo = struct.unpack_from("<I", novo, p + 4)[0]
        struct.pack_into("<I", novo, p + 4, antigo if antigo == pos else antigo + len(lixo))
    buf = io.BytesIO()
    XlsDoc().save(buf, bytes(novo))
    return buf.getvalue()


def test_xls_da_dominio_com_registros_soltos():
    xls = _xls_como_dominio(gerar("Saídas", "09", [(1, 5, "PECA", 5102, "87089990", 1, 10, 10, 0)]))
    import xlrd
    with pytest.raises(xlrd.XLRDError):
        xlrd.open_workbook(file_contents=xls, logfile=io.StringIO())
    s = classificar("documento.xls", xls, CNPJ, COMPS)
    assert (s.tipo, s.competencia) == (SAIDAS, "2026-09")


def test_zip_dentro_de_zip():
    interno = _zip(*[_nfe(i, CNPJ, OUTRO, "2026-09-05") for i in range(1, 4)])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("09 2026/danfe.pdf", b"%PDF-1.4")
        z.writestr("09 2026/notas.zip", interno)
    s = classificar("09_2026.zip", buf.getvalue(), CNPJ, COMPS)
    assert (s.tipo, s.competencia) == (SAIDAS, "2026-09") and s.motivo.startswith("3 NF-e emitidas")


def test_planilha_de_despesas_e_financeira():
    xlsx = _planilha(["PLANEJAMENTO TRIBUTÁRIO PARA 2026"], ["DESPESAS COM VENDAS", "__/2026"], ["Fretes"])
    assert classificar("planilha.xlsx", xlsx, CNPJ, COMPS).tipo == FINANCEIRO
