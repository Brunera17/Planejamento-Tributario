"""Revisão de produtos: detecção, segregação, correção pelo contador e efeito no cálculo."""
import pytest

from tests.test_relatorio_contabil import gerar

ITENS = [
    (1, 2, "B1 - BOBINA IGNICAO FORD", 5106, "85113020", 1, 100.0, 100.0, 0.0),      # monofásico, CST 99
    (2, 2, "J1 - JUNTA TAMPA VALVULAS", 5106, "40169300", 1, 200.0, 200.0, 0.0),     # fora da lei
    (3, 3, "V1 - VALVULA CANISTER GOL", 5106, "84818099", 1, 300.0, 300.0, 0.0),     # depende de Ex
    (4, 3, "D1 - DISCO FREIO DIANTEIRO", 5106, "87083090", 1, 400.0, 400.0, 0.0),    # mesmo código com dois NCMs
    (5, 4, "D1 - DISCO FREIO DIANTEIRO", 5106, "73181500", 1, 500.0, 500.0, 0.0),
    (6, 4, "K1 - KIT BUCHA BANDEJA FOX", 5106, "87089990", 1, 600.0, 600.0, 0.0),    # parecidos com NCMs diferentes
    (7, 4, "K2 - BUCHA BANDEJA POLO", 5106, "40169300", 1, 700.0, 700.0, 0.0),
]


@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "REVISAO LTDA", "cnpj": "06.990.590/0001-23", "regime_tributario": "SIMPLES_NACIONAL", "anexo_simples": "I"}).json()
    p = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-07", "competencia_final": "2026-07"}).json()["id"]
    r = cliente.post(f"/api/planejamentos/{p}/relatorio-contabil", headers=contador,
                     files={"arquivo": ("SAIDAS.xls", gerar("Saídas", "07", ITENS), "application/vnd.ms-excel")})
    assert r.status_code == 200, r.text
    return p


def revisao(cliente, h, pid):
    return cliente.get(f"/api/planejamentos/{pid}/revisao", headers=h).json()


def produto(dados, cod, ncm):
    return next(x for x in dados["produtos"] if x["cod_produto"] == cod and x["ncm_nota"] == ncm)


def tipos(p):
    return {a["tipo"] for a in p["alertas"]}


def test_detecta_e_segrega(cliente, analista, pid):
    d = revisao(cliente, analista, pid)
    assert d["resumo"]["produtos"] == 7
    assert tipos(produto(d, "B1", "85113020")) == {"MONOFASICO_SEM_CST04"}
    assert produto(d, "B1", "85113020")["pendente"] is False  # aviso, não trava
    assert produto(d, "B1", "85113020")["fundamento"] == "Lei 10.485/2002, Anexo I, código 85.11"
    assert "CONDICIONAL" in tipos(produto(d, "V1", "84818099"))
    assert "CODIGO_COM_VARIOS_NCM" in tipos(produto(d, "D1", "73181500"))
    assert "PRODUTOS_PARECIDOS" in tipos(produto(d, "K2", "40169300"))
    assert d["resumo"]["pendentes"] == 5
    assert d["resumo"]["por_tipo"]["CONDICIONAL"]["trava"] is True
    assert d["resumo"]["por_tipo"]["MONOFASICO_SEM_CST04"]["trava"] is False


def test_pendencia_impede_simulacao_final(cliente, contador, pid):
    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    assert "5 produto(s) aguardando revisão" in sim["pendencias"]


def put(cliente, h, pid, **corpo):
    return cliente.put(f"/api/planejamentos/{pid}/revisao", headers=h, json={"motivo": "Conferido com o fornecedor", **corpo})


def test_so_o_contador_revisa_e_com_motivo(cliente, analista, contador, pid):
    assert put(cliente, analista, pid, cod_produto="J1", ncm_nota="40169300").status_code == 403
    r = cliente.put(f"/api/planejamentos/{pid}/revisao", headers=contador, json={"cod_produto": "J1", "ncm_nota": "40169300", "motivo": ""})
    assert r.status_code == 422 and "motivo" in r.json()["campos"]
    assert put(cliente, contador, pid, cod_produto="X9", ncm_nota="40169300").status_code == 404


def test_condicional_exige_decisao_e_decisao_muda_o_calculo(cliente, contador, pid):
    r = put(cliente, contador, pid, cod_produto="V1", ncm_nota="84818099")
    assert r.status_code == 422 and "monofasico" in r.json()["campos"]

    def monofasica():
        sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
        return cliente.get(f"/api/simulacoes/{sim['id']}", headers=contador).json()["resultado"]["base"]["TOTAL"]["receita_monofasica"]

    antes = monofasica()
    assert put(cliente, contador, pid, cod_produto="V1", ncm_nota="84818099", monofasico=False).status_code == 204
    assert monofasica() == pytest.approx(antes - 300.0)
    d = revisao(cliente, contador, pid)
    v1 = produto(d, "V1", "84818099")
    assert (v1["pendente"], v1["revisado"], v1["revisado_por"]) == (False, True, "Contador Demonstração")


def test_lei_nao_e_contrariada_fora_dos_condicionais(cliente, contador, pid):
    assert put(cliente, contador, pid, cod_produto="B1", ncm_nota="85113020", monofasico=False).status_code == 204
    assert produto(revisao(cliente, contador, pid), "B1", "85113020")["monofasico"] is True


def test_corrigir_ncm_resolve_divergencia_e_vale_so_no_planejamento(cliente, contador, pid):
    assert put(cliente, contador, pid, cod_produto="D1", ncm_nota="73181500", ncm_corrigido="87083090").status_code == 204
    d = revisao(cliente, contador, pid)
    d1 = produto(d, "D1", "73181500")
    assert (d1["ncm"], d1["monofasico"], d1["enquadramento"]) == ("87083090", True, "MONOFASICO")
    assert "CODIGO_COM_VARIOS_NCM" not in tipos(d1)
    assert "CODIGO_COM_VARIOS_NCM" not in tipos(produto(d, "D1", "87083090"))
    assert d1["ncm_nota"] == "73181500"  # a nota não muda


def test_desfazer_volta_a_pendencia(cliente, contador, pid):
    d = revisao(cliente, contador, pid)
    r = cliente.delete(f"/api/planejamentos/{pid}/revisao/{produto(d, 'V1', '84818099')['id_revisao']}", headers=contador)
    assert r.status_code == 204
    assert produto(revisao(cliente, contador, pid), "V1", "84818099")["pendente"] is True


def test_exporta_lista_para_o_cliente(cliente, contador, pid):
    r = cliente.get(f"/api/planejamentos/{pid}/revisao/exportar", headers=contador)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "73181500;87083090" in r.text


def test_revisao_de_outra_empresa_nao_vaza(cliente, contador, pid):
    d = revisao(cliente, contador, pid)
    id_rev = produto(d, "D1", "73181500")["id_revisao"]
    outro = next(p["id"] for p in cliente.get("/api/planejamentos", headers=contador).json() if p["id"] != pid)
    assert cliente.delete(f"/api/planejamentos/{outro}/revisao/{id_rev}", headers=contador).status_code == 404


def test_base_legal_consulta(cliente, analista):
    r = cliente.get("/api/tabelas/lei-monofasico?ncm=40169990", headers=analista).json()
    assert r["consulta"]["enquadramento"] == "CONDICIONAL" and len(r["itens"]) == 66
