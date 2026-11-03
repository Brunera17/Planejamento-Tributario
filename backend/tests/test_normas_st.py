"""Biblioteca de normas e substituição tributária do ICMS por NCM com vigência (Portaria CAT 68/2019 e revogações)."""
from datetime import date
from decimal import Decimal

from app.motor.classificacao import ItemBruto, RegraCfop, RegraNcm, classificar
from app.services.substituicao import Regra, TabelaSt


def _consulta(cliente, h, ncm, competencia):
    return cliente.get("/api/tabelas/st/consulta", headers=h, params={"ncm": ncm, "competencia": competencia}).json()


def test_biblioteca_traz_as_normas_de_icms_pis_cofins_cbs_e_ibs(cliente, analista):
    normas = {n["codigo"]: n for n in cliente.get("/api/tabelas/normas", headers=analista).json()}
    for codigo in ("lc87-1996", "ricms-sp-2000", "lei-10485-2002", "lei-10833-2003", "lc214-2025", "portaria-sre-34-2026"):
        assert codigo in normas and normas[codigo]["url"].startswith("http")
    assert set(normas["lc214-2025"]["tributos"]) == {"CBS", "IBS"}
    assert normas["portaria-cat-68-2019"]["regras_st"] > 800
    assert normas["portaria-sre-34-2026"]["regras_st_encerradas"] > 150  # autopeças, pneus, ferramentas...


def test_st_de_autopecas_acaba_em_outubro_de_2026(cliente, analista):
    antes = _consulta(cliente, analista, "8708.99.90", "2026-09")
    depois = _consulta(cliente, analista, "8708.99.90", "2026-10")
    assert antes["sujeito_st"] is True and antes["regra"]["segmento"] == "Autopeças"
    assert depois["sujeito_st"] is False
    assert depois["regra"]["revogada_por"] == "Portaria SRE 34/2026 (SP)" and depois["regra"]["fim"] == "2026-09-30"


def test_ncm_que_saiu_da_st_antes(cliente, analista):
    # parafusos saíram da ST em 1º/04/2022 (Portaria SRE 18/2022)
    r = _consulta(cliente, analista, "73181500", "2026-07")
    assert r["sujeito_st"] is False and r["regra"]["fim"] == "2022-03-31"
    assert _consulta(cliente, analista, "73181500", "2022-03")["sujeito_st"] is True


def test_excecao_e_prefixo_mais_longo():
    tabela = TabelaSt([
        Regra("7325", ("73259100",), "Autopeças", "20", date(2000, 1, 1), date(2026, 9, 30), None),
    ])
    assert tabela.vigente("73251000", "2026-01") and tabela.vigente("73259100", "2026-01") is None


def test_classificacao_usa_a_st_da_competencia():
    brutos = [ItemBruto("2026-09", "87089990", 5102, "SP", Decimal("100"), sujeito_st=True),
              ItemBruto("2026-10", "87089990", 5102, "SP", Decimal("100"), sujeito_st=False)]
    cls = classificar(brutos, {5102: RegraCfop(5102, True)}, {"87089990": RegraNcm("87089990", True, True)}, "SP")
    assert [i.sujeito_st for i in cls.itens] == [True, False]


def test_so_o_contador_altera_e_a_alteracao_desatualiza(cliente, contador, analista):
    corpo = {"titulo": "Decreto 99.999/2026 (SP)", "esfera": "ESTADUAL", "uf": "sp", "tributos": ["ICMS"],
             "resumo": "Norma de teste para a biblioteca", "url": "https://legislacao.fazenda.sp.gov.br/"}
    assert cliente.post("/api/tabelas/normas", headers=analista, json=corpo).status_code == 403
    assert cliente.post("/api/tabelas/normas", headers=contador, json={**corpo, "url": "legislacao"}).status_code == 422
    r = cliente.post("/api/tabelas/normas", headers=contador, json=corpo)
    assert r.status_code == 201 and r.json()["uf"] == "SP" and r.json()["alterado_por_nome"]

    regra = next(x for x in cliente.get("/api/tabelas/st", headers=contador).json() if x["ncm"] == "8708")  # posição inteira: partes e acessórios
    corpo_st = {**{k: regra[k] for k in ("uf", "ncm", "excecoes", "cest", "segmento", "item", "descricao", "norma_id", "revogada_por_id")},
                "vigencia_inicio": regra["vigencia_inicio"], "vigencia_fim": "2026-12-31"}
    assert cliente.put(f"/api/tabelas/st/{regra['id']}", headers=contador, json={**corpo_st, "vigencia_fim": "1999-01-01"}).status_code == 422
    assert cliente.put(f"/api/tabelas/st/{regra['id']}", headers=contador, json=corpo_st).status_code == 200
    assert _consulta(cliente, contador, "87089990", "2026-11")["sujeito_st"] is True
    # devolve como estava para os outros testes
    cliente.put(f"/api/tabelas/st/{regra['id']}", headers=contador, json={**corpo_st, "vigencia_fim": regra["vigencia_fim"]})
