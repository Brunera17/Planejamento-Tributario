"""Apresentação para o cliente (.pptx): download, slides, gráficos nativos e permissões."""
import io

import pytest
from pptx import Presentation


@pytest.fixture(scope="module")
def sim(cliente, contador):
    pid = next(p["id"] for p in cliente.get("/api/planejamentos", headers=contador).json() if p["cnpj"] == "11222333000181")
    return cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()


def test_analista_nao_baixa(cliente, analista, sim):
    assert cliente.get(f"/api/simulacoes/{sim['id']}/apresentacao", headers=analista).status_code == 403


def test_apresentacao_do_caso_de_referencia(cliente, contador, sim):
    r = cliente.get(f"/api/simulacoes/{sim['id']}/apresentacao", headers=contador)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.presentationml")
    assert ".pptx" in r.headers["content-disposition"]

    prs = Presentation(io.BytesIO(r.content))
    slides = list(prs.slides)
    assert len(slides) == 11
    textos = ["\n".join(s.text_frame.text for s in sl.shapes if s.has_text_frame) for sl in slides]

    # a resposta vem no segundo slide, com a economia anual do caso validado: (63.688,26 − 59.765,84) × 12 ÷ 3
    assert "O Lucro Presumido reduz os tributos em R$ 15.690 por ano" in textos[1]
    assert "Recomendação e próximos passos" in textos[-1]

    graficos = {s.name: s.chart for sl in slides for s in sl.shapes if s.has_chart}
    assert len(graficos) >= 9  # todos nativos, editáveis no PowerPoint
    comparativo = graficos["Gráfico: tributos do período por regime"].plots[0].series[0]
    assert [round(v, 2) for v in comparativo.values] == [63688.26, 59765.84, 61192.34]

    # uma rosca por regime no slide da resposta: o arco é a parte da receita que vai para tributos
    roscas = [s.chart for s in slides[1].shapes if s.has_chart]
    assert [round(ch.plots[0].series[0].values[0], 3) for ch in roscas] == [0.092, 0.094, 0.098]

    # cada slide tem roteiro para quem apresenta
    assert all(sl.has_notes_slide and sl.notes_slide.notes_text_frame.text for sl in slides)


@pytest.mark.parametrize("texto,esperado", [
    ("Folha e pró-labore não informados: LP e LR sem INSS. Cada R$ 1.000 acrescenta.", "Folha e pró-labore não informados: LP e LR sem INSS."),
    ("Tarifas são frete (Lei 10.833/2003, art. 3º, IX). Outra frase.", "Tarifas são frete (Lei 10.833/2003, art. 3º, IX)."),
])
def test_frase_nao_corta_a_ideia(texto, esperado):
    from app.services.apresentacao_pptx import frase

    assert frase(texto) == esperado
