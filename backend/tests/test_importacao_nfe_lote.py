"""Importação de NF-e em lote: mesmo resultado da importação nota a nota, com número de consultas que não cresce
com a quantidade de notas do .zip."""
import io
import zipfile

import pytest
from sqlalchemy import event, func, select

from app.models import NotaFiscal, NotaItem

CNPJ = "58316274000174"  # fictício
FORNECEDOR = "33000167000101"


def _nfe(n: int, itens: int = 2, st: bool = True) -> bytes:
    """Nota de entrada (compra) de julho, com `itens` itens; com `st`, o ICMS-ST retido em etapa anterior."""
    chave = f"35{n:042d}"
    icms = ("<ICMS60><orig>0</orig><CST>60</CST><vBCSTRet>150.00</vBCSTRet><vICMSSTRet>9.00</vICMSSTRet></ICMS60>"
            if st else "<ICMS60><orig>0</orig><CST>60</CST></ICMS60>")
    dets = "".join(
        f'<det nItem="{i}"><prod><cProd>P{i}</cProd><xProd>PECA {i}</xProd><NCM>87089990</NCM><CFOP>1102</CFOP>'
        f"<qCom>1</qCom><vUnCom>100</vUnCom><vProd>100.00</vProd></prod><imposto><ICMS>{icms}</ICMS></imposto></det>"
        for i in range(1, itens + 1))
    return (f'<?xml version="1.0" encoding="UTF-8"?><nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe>'
            f'<infNFe Id="NFe{chave}"><ide><nNF>{n}</nNF><dhEmi>2026-07-10T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>'
            f"<emit><CNPJ>{FORNECEDOR}</CNPJ><enderEmit><UF>SP</UF></enderEmit><CRT>3</CRT></emit>"
            f"<dest><CNPJ>{CNPJ}</CNPJ><enderDest><UF>SP</UF></enderDest></dest>{dets}"
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
        "razao_social": "IMPORTACAO EM LOTE LTDA", "cnpj": CNPJ, "regime_tributario": "LUCRO_PRESUMIDO", "uf": "SP"})
    assert emp.status_code == 201, emp.text
    return cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp.json()["id"], "competencia_inicial": "2026-07", "competencia_final": "2026-07"}).json()["id"]


def _importar(cliente, contador, pid, conteudo: bytes, nome="notas.zip") -> dict:
    r = cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador, files={"arquivo": (nome, conteudo)})
    assert r.status_code == 200, r.text
    return r.json()


def _contar_consultas(fabrica_sessao):
    n = {"q": 0}

    def contar(*_):
        n["q"] += 1

    engine = fabrica_sessao.kw["bind"]
    event.listen(engine, "before_cursor_execute", contar)
    return n, lambda: event.remove(engine, "before_cursor_execute", contar)


def test_nota_repetida_no_zip_entra_uma_vez(cliente, contador, pid, fabrica_sessao):
    r = _importar(cliente, contador, pid, _zip(_nfe(1), _nfe(1), _nfe(2, itens=3)))
    assert (r["lidos"], r["importados"], r["ignorados"]) == (3, 2, 1)
    assert r["log"] == ["NF 1: já importada"]
    with fabrica_sessao() as db:
        assert db.scalar(select(func.count(NotaItem.id)).join(NotaFiscal).where(NotaFiscal.planejamento_id == pid)) == 5


def test_reimportacao_completa_a_st_de_varias_notas(cliente, contador, pid, fabrica_sessao):
    _importar(cliente, contador, pid, _zip(_nfe(10, st=False), _nfe(11, st=False)))
    r = _importar(cliente, contador, pid, _zip(_nfe(10), _nfe(11)))
    assert r["importados"] == 0 and r["ignorados"] == 2
    assert r["log"] == ["NF 10: já importada; base do ICMS-ST completada em 2 item(ns)",
                        "NF 11: já importada; base do ICMS-ST completada em 2 item(ns)"]
    with fabrica_sessao() as db:
        sem_base = db.scalar(select(func.count(NotaItem.id)).join(NotaFiscal).where(
            NotaFiscal.planejamento_id == pid, NotaFiscal.numero.in_(["10", "11"]), NotaItem.bc_st.is_(None)))
        assert sem_base == 0


def test_consultas_nao_crescem_com_o_numero_de_notas(cliente, contador, pid, fabrica_sessao):
    contagem, parar = _contar_consultas(fabrica_sessao)
    try:
        _importar(cliente, contador, pid, _zip(*(_nfe(100 + i) for i in range(5))))
        poucas = contagem["q"]
        contagem["q"] = 0
        _importar(cliente, contador, pid, _zip(*(_nfe(200 + i) for i in range(60))))
        muitas = contagem["q"]
    finally:
        parar()
    # nota a nota eram ~3 consultas por nota (busca da chave, flush da nota, flush dos itens): +165 aqui
    assert muitas - poucas < 20, (poucas, muitas)
