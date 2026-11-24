"""Planilha de despesas do cliente: cada valor vai para o mês da data no título da coluna, ligado ao catálogo pelo nome."""
import io
from datetime import datetime
from decimal import Decimal

import pytest
from openpyxl import Workbook

CNPJ = "62173985000104"
MESES = [datetime(2026, 7, 1), datetime(2026, 8, 1), datetime(2026, 9, 1)]


def _planilha(fretes=(100, 110, "N/A"), outras=(0, 50, 0)) -> bytes:
    """Como a do cliente: aba antiga primeiro, rótulo na coluna A, meses em colunas alternadas, comentário à direita."""
    wb = Workbook()
    wb.active.title = "05_2023"
    wb.active.append(["DESPESAS COM VENDAS", "__/2023"])
    aba = wb.create_sheet("2026")

    def bloco(titulo, linhas):
        aba.append([titulo, MESES[0], None, MESES[1], None, MESES[2]])
        for rotulo, valores, *obs in linhas:
            aba.append([rotulo, valores[0], None, valores[1], None, valores[2], None, None, *obs])
        aba.append([])

    aba.append(["DESPESAS PLANEJAMENTO TRIBUTÁRIO PARA 2026"])
    bloco("DESPESAS COM VENDAS", [
        ("Brindes", ("N/A", "N/A", "N/A")),
        ("Fretes", fretes),
        ("Publicidade e Propaganda (ADS Mercado Livre)", (300.5, "1.200,00", 0)),
        ("Outras despesas de vendas (descrever quais):", ("Está na imagem ao lado",) * 3),
    ])
    bloco("DESPESAS ADMINISTRATIVAS", [
        ("Serviços de terceiros  - Honorários Contábeis", (800, 800, 800)),
        ("Outras despesas administrativas (descrever quais):", outras),
        ("Folha de pagamento", (5000, 5000, 5000)),
        ("Pró-labore", (2000, "N/A", None)),
    ])
    bloco("DESPESAS GERAIS", [("Percas mercadorias", (10, None, 30)), ("Copa e cozinha (consumo de funcionarios)", ("N/A",) * 3)])
    bloco("OUTRAS DESPESAS OPERACIONAIS", [("Despesas Bancárias (taxas, tarifas)", (45, 45, 45), "Pacote do banco")])
    aba.append(["BENS PRÓPRIOS (ACIMA DE R$ 1.200,00)", None])
    aba.append(["Veiculos", 90000, None, 90000, None, 90000])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "PLANILHA DESPESAS LTDA", "cnpj": CNPJ, "regime_tributario": "LUCRO_PRESUMIDO"}).json()
    return cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-07", "competencia_final": "2026-08"}).json()["id"]


def _enviar(cliente, h, pid, conteudo, previa=False):
    return cliente.post(f"/api/planejamentos/{pid}/despesas/planilha", headers=h, params={"previa": previa},
                        files={"arquivo": ("despesas.xlsx", conteudo)})


def _mes(cliente, h, pid, comp):
    lv = cliente.get(f"/api/planejamentos/{pid}/levantamentos/{comp}", headers=h).json()
    nomes = {i["id"]: i["nome"] for g in cliente.get("/api/tabelas/catalogo-despesas", headers=h).json() for i in g["itens"]}
    return {nomes[int(k)]: Decimal(str(v)) for k, v in lv["itens"].items()}, lv["outras"]


def test_previa_nao_grava(cliente, contador, pid):
    r = _enviar(cliente, contador, pid, _planilha(), previa=True)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["meses"] == ["2026-07", "2026-08"]  # setembro está fora do período do planejamento
    assert any("Está na imagem ao lado" in a for a in p["avisos"])
    assert p["folha"] == 4  # folha em jul. e ago.; pró-labore em jul. (2.000) e ago. (N/A = 0)
    assert _mes(cliente, contador, pid, "2026-07")[0] == {}


def test_importa_cada_coluna_no_seu_mes(cliente, contador, pid):
    r = _enviar(cliente, contador, pid, _planilha())
    assert r.status_code == 200, r.text
    jul, outras_jul = _mes(cliente, contador, pid, "2026-07")
    ago, outras_ago = _mes(cliente, contador, pid, "2026-08")
    assert jul["Fretes"] == 100 and ago["Fretes"] == 110
    assert jul["Brindes"] == 0  # N/A = não houve
    assert jul["Publicidade e Propaganda"] == Decimal("300.50") and ago["Publicidade e Propaganda"] == 1200
    assert jul["Honorários Contábeis"] == 800
    assert jul["Perdas de Mercadorias"] == 10 and "Perdas de Mercadorias" not in ago  # vazio = não informado
    assert jul["Copa e Cozinha"] == 0
    assert jul["Despesas Bancárias (taxas, tarifas)"] == 45
    assert "Campanhas de Publicidade (marketplace)" not in jul
    assert outras_jul == [] and [o["descricao"] for o in outras_ago] == ["Planilha: Outras despesas administrativas"]
    coleta = cliente.get(f"/api/planejamentos/{pid}/coleta", headers=contador).json()
    folha = coleta["folha"]
    assert Decimal(str(folha["2026-07"]["folha"])) == 5000 and Decimal(str(folha["2026-07"]["pro_labore"])) == 2000
    assert Decimal(str(folha["2026-08"]["pro_labore"])) == 0


def test_reimportar_substitui_sem_duplicar(cliente, contador, pid):
    # valor digitado à mão: a prévia avisa que a planilha vai substituir
    nomes = {i["nome"]: i["id"] for g in cliente.get("/api/tabelas/catalogo-despesas", headers=contador).json() for i in g["itens"]}
    cliente.put(f"/api/planejamentos/{pid}/levantamentos/2026-07", headers=contador,
                json={"itens": [{"item_despesa_id": nomes["Fretes"], "valor": "999.00"}]})
    nova = _planilha(fretes=(120, 130, 0), outras=(0, 70, 0))
    # julho digitado à mão e agosto da importação anterior mudam; o resto é igual
    assert _enviar(cliente, contador, pid, nova, previa=True).json()["substitui_digitados"] == 2
    assert _enviar(cliente, contador, pid, nova).status_code == 200
    jul, _ = _mes(cliente, contador, pid, "2026-07")
    ago, outras_ago = _mes(cliente, contador, pid, "2026-08")
    assert jul["Fretes"] == 120 and ago["Fretes"] == 130
    assert [(o["descricao"], Decimal(str(o["valor"]))) for o in outras_ago] == [("Planilha: Outras despesas administrativas", 70)]


def test_planilha_sem_meses_do_periodo_e_recusada(cliente, contador, pid):
    wb = Workbook()
    wb.active.append(["DESPESAS COM VENDAS", datetime(2025, 1, 1)])
    wb.active.append(["Fretes", 10])
    buf = io.BytesIO()
    wb.save(buf)
    r = _enviar(cliente, contador, pid, buf.getvalue())
    assert r.status_code == 422 and "Nenhum mês" in r.json()["erro"]
