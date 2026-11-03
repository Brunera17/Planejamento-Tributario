"""Premissas tiradas das notas: origem das compras, ST pelo CST, IBS/CBS pelo regime do fornecedor e B2C."""
from decimal import Decimal

import pytest


def _cnpj(base: str) -> str:
    def dv(n: str) -> str:
        pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(n):]
        r = sum(int(a) * b for a, b in zip(n, pesos)) % 11
        return "0" if r < 2 else str(11 - r)
    d1 = dv(base)
    return base + d1 + dv(base + d1)


CNPJ = _cnpj("612345670001")
FORNECEDOR = _cnpj("998877660001")


def _nfe(chave: str, tipo: int, emit: str, uf_emit: str, crt: str, dest: str, uf_dest: str, cfop: str, valor: str,
         icms: str, ind_final: str = "0") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe><infNFe Id="NFe{chave:0>44}" versao="4.00">
<ide><nNF>{chave[-4:]}</nNF><dhEmi>2026-07-15T10:00:00-03:00</dhEmi><tpNF>{tipo}</tpNF><indFinal>{ind_final}</indFinal></ide>
<emit><CNPJ>{emit}</CNPJ><enderEmit><UF>{uf_emit}</UF></enderEmit><CRT>{crt}</CRT></emit>
<dest><CNPJ>{dest}</CNPJ><enderDest><UF>{uf_dest}</UF></enderDest></dest>
<det nItem="1"><prod><cProd>P{chave[-2:]}</cProd><xProd>PECA</xProd><NCM>87089990</NCM><CFOP>{cfop}</CFOP>
<qCom>1</qCom><vUnCom>{valor}</vUnCom><vProd>{valor}</vProd></prod>
<imposto><ICMS>{icms}</ICMS></imposto></det>
</infNFe></NFe></nfeProc>""".encode()


def _icms(orig: str, cst: str, aliq: str = "0") -> str:
    return f"<ICMS{cst}><orig>{orig}</orig><CST>{cst}</CST><pICMS>{aliq}</pICMS></ICMS{cst}>"


@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "PREMISSAS PELAS NOTAS LTDA", "cnpj": CNPJ, "regime_tributario": "LUCRO_PRESUMIDO", "uf": "SP"})
    assert emp.status_code == 201, emp.text
    p = cliente.post("/api/planejamentos", headers=contador,
                     json={"empresa_id": emp.json()["id"], "competencia_inicial": "2026-07", "competencia_final": "2026-07"})
    assert p.status_code == 201, p.text
    return p.json()["id"]


def _importar(cliente, contador, pid, nome, xml):
    r = cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador, files={"arquivo": (nome, xml, "text/xml")})
    assert r.json()["importados"] == 1, r.json()


def _faltam(cliente, contador, pid) -> list[str]:
    blocos = cliente.get(f"/api/planejamentos/{pid}/progresso", headers=contador).json()["blocos"]
    return [x["descricao"] for x in next(b for b in blocos if b["codigo"] == "PREMISSAS")["pendencias"]]


def test_sem_notas_tudo_fica_pendente(cliente, contador, pid):
    faltam = _faltam(cliente, contador, pid)
    assert len(faltam) == 12 and faltam[0] == "Origem das compras"


def test_notas_preenchem_as_premissas(cliente, contador, pid):
    # compras: MG regime normal 12% (1.000), SP do Simples (500) e PR importado a 4% (500)
    _importar(cliente, contador, pid, "e1.xml", _nfe("1001", 0, FORNECEDOR, "MG", "3", CNPJ, "SP", "2102", "1000.00", _icms("0", "00", "12.00")))
    _importar(cliente, contador, pid, "e2.xml", _nfe("1002", 0, FORNECEDOR, "SP", "1", CNPJ, "SP", "1102", "500.00",
                                                     "<ICMSSN102><orig>0</orig><CSOSN>102</CSOSN></ICMSSN102>"))
    _importar(cliente, contador, pid, "e3.xml", _nfe("1003", 0, FORNECEDOR, "PR", "3", CNPJ, "SP", "2102", "500.00", _icms("1", "00", "4.00")))
    # vendas no estado: uma com ST (CST 60) a consumidor final, outra tributada para empresa
    _importar(cliente, contador, pid, "s1.xml", _nfe("2001", 1, CNPJ, "SP", "3", FORNECEDOR, "SP", "5405", "300.00", _icms("0", "60"), "1"))
    _importar(cliente, contador, pid, "s2.xml", _nfe("2002", 1, CNPJ, "SP", "3", FORNECEDOR, "SP", "5102", "700.00", _icms("0", "00", "18.00")))

    c = cliente.get(f"/api/planejamentos/{pid}/coleta", headers=contador).json()
    comp = {Decimal(str(x["aliquota"])).normalize(): Decimal(str(x["percentual"])) for x in c["composicao_auto"]["linhas"]}
    assert comp == {Decimal("0.18"): Decimal("0.25"), Decimal("0.12"): Decimal("0.5"), Decimal("0.04"): Decimal("0.25")}
    auto = c["premissas_auto"]
    assert auto["aplicar_st_vendas_internas"]["valor"] is True and "CST" in auto["aplicar_st_vendas_internas"]["fonte"]
    assert Decimal(str(auto["pct_compras_credito_ibs_cbs"]["valor"])) == Decimal("0.75")
    assert auto["vendas_b2c"]["valor"] is False  # 30% a consumidor final

    faltam = _faltam(cliente, contador, pid)
    assert not {"Origem das compras", "Vendas internas com ICMS-ST", "Compras com crédito de IBS/CBS", "Vendas para consumidor final"} & set(faltam)
    assert "Receita bruta dos últimos 12 meses (RBT12)" in faltam


def test_informado_vale_mais_que_as_notas(cliente, contador, pid):
    from app.db.session import SessionLocal
    from app.models import Planejamento
    from app.services.entrada import premissas_do_planejamento

    assert cliente.put(f"/api/planejamentos/{pid}/premissas", headers=contador, json={"vendas_b2c": True}).status_code == 204
    comp = [{"origem": "Compras internas", "aliquota": "0.18", "percentual": "1"}]
    assert cliente.put(f"/api/planejamentos/{pid}/composicao-compras", headers=contador, json=comp).status_code == 204
    with SessionLocal() as db:
        pr = premissas_do_planejamento(db, db.get(Planejamento, pid))
    assert pr.vendas_b2c is True and pr.composicao_compras == {Decimal("0.18"): Decimal("1")}
    assert pr.aplicar_st_vendas_internas is True  # continua vindo das notas

    # apagar a composição informada volta para a das notas
    assert cliente.delete(f"/api/planejamentos/{pid}/composicao-compras", headers=contador).status_code == 204
    with SessionLocal() as db:
        pr = premissas_do_planejamento(db, db.get(Planejamento, pid))
    assert pr.composicao_compras[Decimal("0.12")] == Decimal("0.5")


@pytest.mark.parametrize("cst,st", [("60", True), ("060", True), ("500", True), ("00", False), ("102", False), ("", None)])
def test_cst_de_st(cst, st):
    from app.services.premissas_auto import eh_st

    assert eh_st(cst or None) is st
