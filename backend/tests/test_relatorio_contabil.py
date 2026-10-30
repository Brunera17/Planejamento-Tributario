"""Importação do relatório "Movimentação de Produtos – ICMS – PIS – COFINS" do sistema contábil.

Os arquivos são gerados aqui, no mesmo layout do relatório real (cabeçalho nas linhas 1–6, colunas
espaçadas como no .xls exportado e linha de totais no fim), sem dados de clientes.
"""
import io
from decimal import Decimal

import pytest
import xlwt
from openpyxl import Workbook

from app.services.relatorio_contabil import RelatorioInvalido, ler_relatorio

# posição das colunas no relatório exportado
COL = {"codigo": 0, "numero": 2, "data": 4, "produto": 6, "cfop": 8, "ncm": 9, "qtde": 10, "unit": 11, "valor": 15,
       "base_icms": 17, "aliq_icms": 19, "icms": 21, "cst_icms": 23, "base_pis": 25, "pis": 30, "cst_pis": 32,
       "base_cofins": 34, "cofins": 38, "cst_cofins": 42}
CABECALHO = {0: "Código", 2: "Numero", 4: "Data", 6: "Produto", 8: "CFOP", 9: "NCM", 10: "Qtde", 11: "R$ Unit.",
             15: "R$ Produto", 17: "R$ Base", 19: "Aliq.", 21: "R$ ICMS", 23: "CST", 25: "R$ Base", 28: "Aliq.",
             30: "R$ PIS", 32: "CST", 34: "R$ Base", 36: "Aliq.", 38: "R$ COFINS", 42: "CST"}


def gerar(tipo: str, mes: str, itens: list[tuple], formato: str = "xls", total: float | None = None) -> bytes:
    """itens: (numero, dia, produto, cfop, ncm, qtde, unit, valor, icms)."""
    linhas = [
        {0: f"Movimentação de Produtos - de: 01/{mes}/2026 até 28/{mes}/2026", 38: "Página: 1/1"},
        {0: "Empresa: 0001 - EMPRESA TESTE", 37: "Data: 02/10/2026"},
        {0: tipo},
        {16: "ICMS", 25: "PIS", 34: "COFINS"},
        {},
        CABECALHO,
    ]
    for n, (numero, dia, produto, cfop, ncm, qtde, unit, valor, icms) in enumerate(itens, start=1):
        linhas.append({0: float(n), 2: float(numero), 4: f"{dia:02d}/{mes}/2026", 6: produto, 8: float(cfop), 9: ncm,
                       10: float(qtde), 11: unit, 15: valor, 17: 0.0, 19: 0.0, 21: icms, 23: 102.0, 25: valor,
                       32: 99.0, 34: valor, 42: 99.0})
    soma = sum(i[7] for i in itens) if total is None else total
    linhas.append({12: soma, 16: 0.0, 20: 0.0})
    buf = io.BytesIO()
    if formato == "xls":
        livro = xlwt.Workbook()
        aba = livro.add_sheet("Movimentação de Produtos - ICMS")
        for r, linha in enumerate(linhas):
            for c, v in linha.items():
                aba.write(r, c, v)
        livro.save(buf)
    else:
        livro = Workbook()
        aba = livro.active
        for r, linha in enumerate(linhas, start=1):
            for c, v in linha.items():
                aba.cell(row=r, column=c + 1, value=v)
        livro.save(buf)
    return buf.getvalue()


SAIDAS_JUL = [
    (101, 2, "A1 - BOBINA IGNICAO", 5106, "85113020", 2, 100.0, 200.0, 0.0),
    (101, 2, "A2 - JUNTA TAMPA", 5106, "40169300", 1, 50.0, 55.0, 0.0),
    (102, 3, "A1 - BOBINA IGNICAO", 6106, "85113020", 1, 100.0, 100.0, 0.0),
    (103, 4, "A3 - SENSOR", 6949, "90328929", 1, 30.0, 30.0, 0.0),
]
ENTRADAS_JUL = [
    (900, 5, "A1 - BOBINA IGNICAO", 2202, "85113020", 1, 100.0, 100.0, 0.0),
    (901, 6, "Z9 - LOTE FORNECEDOR", 1403, "87088000", 10, 5.0, 50.0, 0.0),
    (902, 7, "A3 - SENSOR", 2949, "90328929", 1, 30.0, 30.0, 0.0),
]


# ------------------------------------------------------------------ leitura


@pytest.mark.parametrize("formato", ["xls", "xlsx"])
def test_le_relatorio_de_saidas(formato):
    nome = f"saidas.{formato}"
    rel = ler_relatorio(nome, gerar("Saídas", "07", SAIDAS_JUL, formato))
    assert rel.tipo == "SAIDA"
    assert rel.periodo[0].isoformat() == "2026-07-01"
    assert rel.empresa == "0001 - EMPRESA TESTE"
    assert len(rel.linhas) == 4 and not rel.avisos
    primeiro = rel.linhas[0]
    assert (primeiro.numero, primeiro.cod_produto, primeiro.descricao, primeiro.cfop, primeiro.ncm) == \
        ("101", "A1", "BOBINA IGNICAO", 5106, "85113020")
    assert sum(l.valor for l in rel.linhas) == Decimal("385")


def test_total_do_rodape_diferente_gera_aviso():
    rel = ler_relatorio("saidas.xls", gerar("Saídas", "07", SAIDAS_JUL, total=999.0))
    assert "difere do total do rodapé" in rel.avisos[0]


def test_arquivo_que_nao_e_o_relatorio():
    livro = Workbook()
    livro.active["A1"] = "Planilha qualquer"
    buf = io.BytesIO()
    livro.save(buf)
    with pytest.raises(RelatorioInvalido, match="Movimentação de Produtos"):
        ler_relatorio("outra.xlsx", buf.getvalue())


# ------------------------------------------------------------------ API


@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "EMPRESA TESTE LTDA", "cnpj": "45.997.418/0001-53", "regime_tributario": "SIMPLES_NACIONAL",
        "anexo_simples": "I", "uf": "SP"}).json()
    return cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-07", "competencia_final": "2026-08"}).json()["id"]


def enviar(cliente, headers, pid, nome, conteudo):
    return cliente.post(f"/api/planejamentos/{pid}/relatorio-contabil", headers=headers,
                        files={"arquivo": (nome, conteudo, "application/vnd.ms-excel")})


def test_importa_saidas_e_ignora_reimportacao(cliente, analista, pid):
    r = enviar(cliente, analista, pid, "SAIDAS 07-2026.xls", gerar("Saídas", "07", SAIDAS_JUL))
    assert r.status_code == 200, r.text
    dados = r.json()
    assert (dados["tipo"], dados["linhas"], dados["notas_importadas"]) == ("SAIDA", 4, 3)
    assert dados["por_competencia"]["2026-07"]["valor"] == pytest.approx(385.0)

    de_novo = enviar(cliente, analista, pid, "SAIDAS 07-2026.xls", gerar("Saídas", "07", SAIDAS_JUL)).json()
    assert (de_novo["notas_importadas"], de_novo["notas_ignoradas"]) == (0, 3)

    coleta = cliente.get(f"/api/planejamentos/{pid}/coleta", headers=analista).json()
    assert coleta["saidas"][0] == {"competencia": "2026-07", "notas": 3, "itens": 4, "valor": pytest.approx(385.0)}


def test_entradas_preenchem_devolucoes_e_avisam_compras(cliente, contador, pid):
    r = enviar(cliente, contador, pid, "ENTRADAS 07-2026.xls", gerar("Entradas", "07", ENTRADAS_JUL)).json()
    assert r["tipo"] == "ENTRADA"
    assert r["por_competencia"]["2026-07"]["devolucoes"] == pytest.approx(100.0)
    assert r["por_competencia"]["2026-07"]["compras_revenda"] == pytest.approx(50.0)
    assert any("devoluções de venda preenchidas" in a for a in r["avisos"])
    assert any("informe as compras do mês" in a for a in r["avisos"])
    coleta = cliente.get(f"/api/planejamentos/{pid}/coleta", headers=contador).json()
    assert coleta["devolucoes"]["2026-07"] == pytest.approx(100.0)


def test_icms_zerado_das_entradas_nao_zera_o_credito(cliente, contador, pid):
    """O relatório cobre só R$ 50 de compras; com R$ 10.000 informados, o crédito segue estimado (18%)."""
    cliente.put(f"/api/planejamentos/{pid}/compras", headers=contador, json=[
        {"competencia": "2026-07", "valor": "10000.00"}, {"competencia": "2026-08", "valor": "10000.00"}])
    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    base = cliente.get(f"/api/simulacoes/{sim['id']}", headers=contador).json()["resultado"]["base"]
    assert base["2026-07"]["icms_credito"] == pytest.approx(1800.0)


def test_nao_duplica_competencia_ja_importada_por_xml(cliente, contador, pid):
    nfe = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe><infNFe Id="NFe35260845997418000153550010000005551000005550" versao="4.00">
<ide><nNF>555</nNF><dhEmi>2026-08-10T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>
<emit><CNPJ>45997418000153</CNPJ><enderEmit><UF>SP</UF></enderEmit></emit>
<dest><CPF>12345678909</CPF><enderDest><UF>SP</UF></enderDest></dest>
<det nItem="1"><prod><cProd>A1</cProd><xProd>BOBINA</xProd><NCM>85113020</NCM><CFOP>5106</CFOP>
<qCom>1</qCom><vUnCom>80.00</vUnCom><vProd>80.00</vProd></prod><imposto><ICMS><ICMSSN102><CSOSN>102</CSOSN></ICMSSN102></ICMS></imposto></det>
</infNFe></NFe></nfeProc>"""
    assert cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador,
                        files={"arquivo": ("n.xml", nfe.encode(), "text/xml")}).json()["importados"] == 1
    saidas_ago = [(200, 11, "A1 - BOBINA IGNICAO", 5106, "85113020", 1, 80.0, 80.0, 0.0)]
    r = enviar(cliente, contador, pid, "SAIDAS 08-2026.xls", gerar("Saídas", "08", saidas_ago)).json()
    assert r["notas_importadas"] == 0
    assert any("de outra origem (XML ou carga)" in a for a in r["avisos"])


def test_rejeita_arquivo_invalido(cliente, contador, pid):
    r = enviar(cliente, contador, pid, "relatorio.csv", b"a;b")
    assert r.status_code == 415
    livro = Workbook()
    buf = io.BytesIO()
    livro.save(buf)
    r = enviar(cliente, contador, pid, "vazio.xlsx", buf.getvalue())
    assert r.status_code == 422 and "Movimentação de Produtos" in r.json()["erro"]
