"""Calculadora do Simples por nota: motor puro e rotas."""
from decimal import Decimal as D

import pytest

from app.motor.calculadora_simples import LinhaNota, calcular
from app.motor.simples import aliquota_efetiva, reparticao
from app.seeds.tabelas import faixas_simples

FAIXAS = {a: list(faixas_simples(a)) for a in ("I", "II", "III", "IV", "V")}
CNPJ = "44556677000186"


def test_valor_digitado_anexo_i():
    r = calcular([LinhaNota("venda", D("1000"))], D("500000"), FAIXAS)
    efetiva = aliquota_efetiva(D("500000"), FAIXAS["I"]).efetiva
    assert r.das == D("1000") * efetiva
    assert sum(r.tributos.values()) == r.das
    assert r.aliquota_media == efetiva


def test_st_monofasico_e_iss_fora_saem_do_das():
    rbt12 = D("500000")
    rep_i = reparticao(aliquota_efetiva(rbt12, FAIXAS["I"]))
    rep_iii = reparticao(aliquota_efetiva(rbt12, FAIXAS["III"]))
    r = calcular([
        LinhaNota("peça com ST e monofásica", D("1000"), "I", st=True, monofasico=True),
        LinhaNota("serviço com ISS retido", D("2000"), "III", iss_fora_do_das="RETIDO"),
    ], rbt12, FAIXAS)
    peca, servico = r.linhas
    assert set(peca.tributos) == {"IRPJ", "CSLL", "CPP"}
    assert peca.aliquota == rep_i["IRPJ"] + rep_i["CSLL"] + rep_i["CPP"]
    assert "ISS" not in servico.tributos
    assert servico.das == D("2000") * (sum(rep_iii.values()) - rep_iii["ISS"])


def test_acima_do_sublimite_iss_vai_para_o_municipio():
    linhas = [LinhaNota("serviço", D("10000"), "III"), LinhaNota("serviço com ISS fixo", D("5000"), "III", iss_fora_do_das="FIXO"),
              LinhaNota("venda", D("1000"), "I")]
    r = calcular(linhas, D("4000000"), FAIXAS, aliq_iss_municipio=D("0.03"))
    assert "ISS" not in r.tributos  # 6ª faixa: sem ISS no DAS
    assert r.iss_municipio == D("300") and r.linhas[0].iss_municipio == D("300")
    assert r.linhas[1].iss_municipio == 0 and r.linhas[2].iss_municipio == 0
    sem = calcular(linhas, D("4000000"), FAIXAS)
    assert sem.iss_municipio == 0 and any("alíquota de ISS do município" in a for a in sem.avisos)
    # abaixo do sublimite a alíquota do município não entra
    assert calcular(linhas, D("500000"), FAIXAS, aliq_iss_municipio=D("0.03")).iss_municipio == 0


def test_fator_r_escolhe_o_anexo():
    linha = [LinhaNota("consultoria", D("1000"), fator_r=True)]
    assert calcular(linha, D("1000000"), FAIXAS, folha_12m=D("280000")).linhas[0].anexo == "III"
    r = calcular(linha, D("1000000"), FAIXAS, folha_12m=D("100000"))
    assert r.linhas[0].anexo == "V" and r.fator_r == D("0.1")
    assert any("Fator R" in a for a in r.avisos)
    with pytest.raises(ValueError, match="folha"):
        calcular(linha, D("1000000"), FAIXAS)


def test_previsao_do_mes_e_avisos_de_limite():
    r = calcular([LinhaNota("a", D("30000"), competencia="2026-11"), LinhaNota("b", D("20000"), competencia="2026-11"),
                  LinhaNota("c", D("10000"), competencia="2026-12")], D("3570000"), FAIXAS)
    assert r.por_competencia["2026-11"] + r.por_competencia["2026-12"] == r.das
    assert any("passa do sublimite" in a for a in r.avisos)
    assert any("faixa 6" in a for a in r.avisos)


FORNECEDOR = "11222333000181"


def _venda(n: int, ncm: str, cfop: int = 5102, emitente: str = CNPJ, csosn: str = "102") -> bytes:
    icms = f"<ICMSSN{csosn}><orig>0</orig><CSOSN>{csosn}</CSOSN></ICMSSN{csosn}>"
    return (f'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe35{n:042d}"><ide><nNF>{n}</nNF>'
            f"<dhEmi>2026-11-10T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>"
            f"<emit><CNPJ>{emitente}</CNPJ><enderEmit><UF>SP</UF></enderEmit><CRT>1</CRT></emit>"
            "<dest><CPF>12345678909</CPF><enderDest><UF>SP</UF></enderDest></dest>"
            f'<det nItem="1"><prod><cProd>A</cProd><xProd>PECA</xProd><NCM>{ncm}</NCM><CFOP>{cfop}</CFOP><qCom>1</qCom>'
            f"<vUnCom>1000</vUnCom><vProd>1000.00</vProd></prod><imposto><ICMS>{icms}</ICMS></imposto></det>"
            "</infNFe></NFe></nfeProc>").encode()


def _compra(n: int, ncm: str, com_st: bool, cst_pis: str) -> bytes:
    """Nota do fornecedor (regime normal) para a empresa: CST 10 com ICMS-ST retido, ou CST 00 sem ST."""
    icms = ("<ICMS10><orig>0</orig><CST>10</CST><vBCST>120.00</vBCST><vICMSST>9.00</vICMSST></ICMS10>" if com_st
            else "<ICMS00><orig>0</orig><CST>00</CST><pICMS>18</pICMS><vICMS>18.00</vICMS></ICMS00>")
    return (f'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe35{n:042d}"><ide><nNF>{n}</nNF>'
            f"<dhEmi>2026-11-05T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>"
            f"<emit><CNPJ>{FORNECEDOR}</CNPJ><enderEmit><UF>SP</UF></enderEmit><CRT>3</CRT></emit>"
            f"<dest><CNPJ>{CNPJ}</CNPJ><enderDest><UF>SP</UF></enderDest></dest>"
            f'<det nItem="1"><prod><cProd>B</cProd><xProd>ITEM</xProd><NCM>{ncm}</NCM><CFOP>5405</CFOP><qCom>1</qCom>'
            f"<vUnCom>100</vUnCom><vProd>100.00</vProd></prod><imposto><ICMS>{icms}</ICMS>"
            f"<PIS><PISAliq><CST>{cst_pis}</CST></PISAliq></PIS></imposto></det></infNFe></NFe></nfeProc>").encode()


def _ler(cliente, headers, empresa, arquivos):
    r = cliente.post("/api/calculadora-simples/nfe", headers=headers, data={"empresa_id": empresa},
                     files=[("arquivos", (f"{i}.xml", x)) for i, x in enumerate(arquivos)])
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def empresa(cliente, contador):
    r = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "CALCULADORA LTDA", "cnpj": CNPJ, "regime_tributario": "SIMPLES_NACIONAL", "uf": "SP",
        "anexo_simples": "I"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_rota_dados_da_empresa(cliente, contador, empresa):
    r = cliente.get(f"/api/calculadora-simples/empresas/{empresa}", headers=contador).json()
    assert r["anexo"] == "I" and r["rbt12"] is None
    assert cliente.get("/api/calculadora-simples/empresas/999999", headers=contador).status_code == 404


def test_rota_le_nfe_e_calcula(cliente, analista, empresa):
    lido = _ler(cliente, analista, empresa, [_venda(1, "87089990"), _venda(1, "87089990")])  # repetida conta uma vez
    assert len(lido["linhas"]) == 1 and lido["linhas"][0]["valor"] == 1000
    assert (lido["vendas"], lido["compras"]) == (1, 0)
    assert "opcionais" in lido["info"][0]  # sem compras: avisa que elas melhoram o cálculo, sem exigir
    outra = _ler(cliente, analista, empresa, [_venda(2, "87089990", emitente="99888777000161")])
    assert outra["linhas"] == [] and "fora do cálculo" in outra["avisos"][0]

    calc = cliente.post("/api/calculadora-simples", headers=analista,
                        json={"rbt12": 500000, "linhas": lido["linhas"]})
    assert calc.status_code == 200, calc.text
    corpo = calc.json()
    assert corpo["das"] > 0 and corpo["faixas"]["I"]["faixa"] == 3
    assert corpo["por_competencia"]["2026-11"] == corpo["das"]
    assert corpo["parcelas"] == [{"anexo": "I", "monofasico": True, "st": False, "iss_fora_do_das": None, "receita": 1000}]


def test_sem_compras_o_st_segue_a_nota_de_venda(cliente, analista, empresa):
    lido = _ler(cliente, analista, empresa, [_venda(10, "21069030", csosn="102"), _venda(11, "22021000", csosn="500")])
    assert [l["st"] for l in lido["linhas"]] == [False, True]
    assert lido["avisos"] == []


def test_com_compras_o_st_segue_o_fornecedor_e_avisa(cliente, analista, empresa):
    lido = _ler(cliente, analista, empresa, [
        _venda(20, "19011090", csosn="102"),   # vendido sem ST, mas comprado com ST cobrado
        _venda(21, "40141000", csosn="500"),   # vendido como ST, mas comprado sem ST
        _venda(22, "19059090", csosn="102"),   # fora da lei do monofásico; fornecedor diz CST 04
        _compra(30, "19011090", com_st=True, cst_pis="06"),
        _compra(31, "40141000", com_st=False, cst_pis="01"),
        _compra(32, "19059090", com_st=False, cst_pis="04"),
    ])
    assert (lido["vendas"], lido["compras"]) == (3, 3) and lido["info"] == []
    assert [(l["st"], l["monofasico"]) for l in lido["linhas"]] == [(True, False), (False, False), (False, False)]
    avisos = " | ".join(lido["avisos"])
    assert "19011090" in avisos and "compra veio com ST" in avisos
    assert "40141000" in avisos and "compra veio sem ST" in avisos
    assert "19059090" in avisos and "CST 04" in avisos


def test_rota_recusa_envio_sem_arquivo_e_rar(cliente, analista, empresa):
    r = cliente.post("/api/calculadora-simples/nfe", headers=analista, data={"empresa_id": empresa})
    assert r.status_code == 422
    r = cliente.post("/api/calculadora-simples/nfe", headers=analista, data={"empresa_id": empresa},
                     files=[("arquivos", ("notas.rar", b"Rar!"))])
    assert r.status_code == 200 and "RAR" in r.json()["erros"][0]


def test_rota_iss_municipio_e_fora_do_das(cliente, analista):
    r = cliente.post("/api/calculadora-simples", headers=analista, json={
        "rbt12": 4000000, "aliq_iss_municipio": 0.05,
        "linhas": [{"valor": 1000, "anexo": "III"}, {"valor": 1000, "anexo": "III", "iss_fora_do_das": "ISENTO"}]})
    assert r.status_code == 200, r.text
    assert r.json()["iss_municipio"] == 50
    acima = cliente.post("/api/calculadora-simples", headers=analista,
                         json={"rbt12": 1, "aliq_iss_municipio": 0.06, "linhas": [{"valor": 1}]})
    assert acima.status_code == 422


def test_rota_recusa_fator_r_sem_folha(cliente, analista):
    r = cliente.post("/api/calculadora-simples", headers=analista,
                     json={"rbt12": 100000, "linhas": [{"valor": 100, "fator_r": True}]})
    assert r.status_code == 422 and "folha" in r.text
