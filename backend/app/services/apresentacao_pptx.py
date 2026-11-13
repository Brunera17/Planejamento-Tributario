"""Apresentação do planejamento para o cliente (.pptx), com gráficos nativos editáveis no PowerPoint.

Usa os mesmos dados do relatório PDF (relatorio_pdf.coletar), em linguagem de quem não é contador:
uma mensagem por slide, o título diz a conclusão e o gráfico mostra a diferença entre os regimes.
"""
from __future__ import annotations

import io
import re

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from app.services.relatorio_pdf import REGIMES, DadosRelatorio, enquadramento_simples, mes

# paleta do sistema (paleta A): petróleo domina, verde só para o regime de menor carga
ESCURO = RGBColor(0x0E, 0x3A, 0x49)
MARCA = RGBColor(0x15, 0x5E, 0x75)
TEXTO = RGBColor(0x1F, 0x29, 0x33)
APOIO = RGBColor(0x52, 0x60, 0x6D)
SUAVE = RGBColor(0x9A, 0xA5, 0xB1)
GRADE = RGBColor(0xE4, 0xE9, 0xEF)
FUNDO_CARTAO = RGBColor(0xF3, 0xF6, 0xF8)
MELHOR = RGBColor(0x2F, 0x85, 0x5A)
MELHOR_FUNDO = RGBColor(0xE6, 0xF4, 0xEC)
ALERTA = RGBColor(0xB7, 0x79, 0x1F)
ALERTA_FUNDO = RGBColor(0xFB, 0xEF, 0xD9)
BRANCO = RGBColor(0xFF, 0xFF, 0xFF)
CLARO = RGBColor(0xCF, 0xE3, 0xEA)  # texto de apoio sobre o fundo escuro

GRUPOS = [  # grupo de tributo, tributos do resultado, cor
    ("ICMS", ("ICMS", "IPI"), RGBColor(0x15, 0x5E, 0x75)),  # IPI só no DAS da indústria (Anexo II)
    ("PIS e COFINS", ("PIS", "COFINS", "PIS/COFINS"), RGBColor(0x4F, 0x8F, 0xA4)),
    ("IRPJ e CSLL", ("IRPJ", "CSLL"), RGBColor(0x9E, 0xC5, 0xD3)),
    ("INSS patronal", ("CPP", "INSS patronal"), RGBColor(0x52, 0x60, 0x6D)),
]
ORDEM = ("SIMPLES_NACIONAL", "LUCRO_PRESUMIDO", "LUCRO_REAL")
COR_REGIME = {"SIMPLES_NACIONAL": RGBColor(0x9E, 0xC5, 0xD3), "LUCRO_PRESUMIDO": MARCA, "LUCRO_REAL": APOIO}

FONTE = "Calibri"
LARGURA, ALTURA = Inches(13.333), Inches(7.5)
MARGEM = Inches(0.6)
MOEDA = '"R$" #,##0'


def brl(v: float | None) -> str:
    if v is None:
        return "–"
    s = f"{v:,.0f}".replace(",", ".")
    return f"R$ {s}"


def pct(v: float | None, casas: int = 1) -> str:
    return "–" if v is None else f"{v * 100:.{casas}f}%".replace(".", ",")


def _meses(n: int) -> str:
    return "1 mês" if n == 1 else f"{n} meses"


def milhoes(v: float) -> str:
    return f"R$ {v / 1e6:.1f} mi".replace(".", ",")


def frase(texto: str, limite: int = 170, ponto: bool = True) -> str:
    """Primeira frase, sem passar do limite: os slides levam a ideia, o detalhe fica no relatório.

    Só termina frase o ponto seguido de maiúscula, para "art. 3º" e "Lei 10.833/2003, art." não cortarem a ideia.
    """
    primeira = re.split(r"(?<=\.)\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", texto.strip(), maxsplit=1)[0]
    if len(primeira) > limite:
        primeira = primeira[:limite].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    if not ponto:
        return primeira.rstrip(".")
    return primeira if primeira.endswith((".", "…")) else primeira + "."


def _circulo(slide, x, y, diametro, texto, cor_fundo, cor_texto, tamanho, nome):
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, diametro, diametro)
    c.fill.solid()
    c.fill.fore_color.rgb = cor_fundo
    c.line.fill.background()
    c.shadow.inherit = False
    c.name = nome
    tf = c.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    pr = tf.paragraphs[0]
    pr.alignment = PP_ALIGN.CENTER
    run = pr.add_run()
    run.text = texto
    run.font.name, run.font.size, run.font.bold, run.font.color.rgb = FONTE, Pt(tamanho), True, cor_texto
    return c


# ------------------------------------------------------------- primitivas


def _texto(slide, x, y, w, h, paragrafos, tamanho=16, cor=TEXTO, negrito=False, alinhar=PP_ALIGN.LEFT,
           ancora=MSO_ANCHOR.TOP, espaco=0, nome=None):
    """`paragrafos`: texto, ou lista de parágrafos; cada parágrafo é texto ou lista de (texto, {opções do trecho})."""
    caixa = slide.shapes.add_textbox(x, y, w, h)
    if nome:
        caixa.name = nome
    tf = caixa.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = ancora
    if isinstance(paragrafos, str):
        paragrafos = [paragrafos]
    for i, par in enumerate(paragrafos):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = alinhar
        if espaco and i:
            p.space_before = Pt(espaco)
        trechos = [(par, {})] if isinstance(par, str) else par
        for t, o in trechos:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = FONTE
            f.size = Pt(o.get("tamanho", tamanho))
            f.bold = o.get("negrito", negrito)
            f.italic = o.get("italico", False)
            f.color.rgb = o.get("cor", cor)
    return caixa


def _caixa(slide, x, y, w, h, cor, nome=None, arredondado=True):
    forma = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if arredondado else MSO_SHAPE.RECTANGLE, x, y, w, h)
    if arredondado:
        forma.adjustments[0] = 0.08
    forma.fill.solid()
    forma.fill.fore_color.rgb = cor
    forma.line.fill.background()
    forma.shadow.inherit = False
    if nome:
        forma.name = nome
    return forma


def _etiqueta(slide, x, y, texto, cor_texto, cor_fundo, tamanho=11):
    largura = Inches(0.13 * len(texto) * tamanho / 11 + 0.35)
    forma = _caixa(slide, x, y, largura, Inches(0.32), cor_fundo)
    forma.adjustments[0] = 0.5
    tf = forma.text_frame
    tf.margin_left = tf.margin_right = Inches(0.08)
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = texto
    r.font.name, r.font.size, r.font.bold, r.font.color.rgb = FONTE, Pt(tamanho), True, cor_texto
    return forma


class Deck:
    def __init__(self, d: DadosRelatorio):
        self.d = d
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = LARGURA, ALTURA
        self.prs.core_properties.title = f"Planejamento tributário – {d.razao_social}"
        self.prs.core_properties.author = d.escritorio
        self.periodo = f"{mes(d.competencias[0])} a {mes(d.competencias[-1])}"
        self.numero = 0

    def slide(self, titulo: str | None = None, escuro: bool = False, notas: str = ""):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.numero += 1
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = ESCURO if escuro else BRANCO
        if titulo:
            _texto(s, MARGEM, Inches(0.45), LARGURA - 2 * MARGEM, Inches(1.1), titulo, tamanho=30, negrito=True,
                   cor=BRANCO if escuro else TEXTO, ancora=MSO_ANCHOR.TOP, nome="Título")
        if not escuro:
            _texto(s, MARGEM, ALTURA - Inches(0.45), Inches(9), Inches(0.25),
                   f"{self.d.razao_social}, planejamento tributário de {self.periodo}", tamanho=10, cor=SUAVE, nome="Rodapé")
            _texto(s, LARGURA - MARGEM - Inches(1), ALTURA - Inches(0.45), Inches(1), Inches(0.25), str(self.numero),
                   tamanho=10, cor=SUAVE, alinhar=PP_ALIGN.RIGHT, nome="Número do slide")
        if notas:
            s.notes_slide.notes_text_frame.text = notas
        return s

    def grafico(self, s, tipo, dados, x, y, w, h, nome: str, legenda: bool = False):
        frame = s.shapes.add_chart(tipo, x, y, w, h, dados)
        frame.name = nome
        ch = frame.chart
        ch.font.name, ch.font.size, ch.font.color.rgb = FONTE, Pt(12), APOIO
        ch.has_title = False  # o título do slide diz a conclusão; o do gráfico só repetiria
        ch.has_legend = legenda
        if legenda:
            ch.legend.position = XL_LEGEND_POSITION.BOTTOM
            ch.legend.include_in_layout = False
            ch.legend.font.size = Pt(12)
        return ch


def _eixos_discretos(ch, valores_visiveis: bool = False, formato: str | None = None):
    va = ch.value_axis
    va.visible = valores_visiveis
    va.has_major_gridlines = valores_visiveis
    if valores_visiveis:
        va.major_gridlines.format.line.color.rgb = GRADE
        va.format.line.fill.background()
        va.tick_labels.font.size = Pt(11)
        va.tick_labels.font.color.rgb = SUAVE
        if formato:
            va.tick_labels.number_format = formato
            va.tick_labels.number_format_is_linked = False
    ca = ch.category_axis
    ca.format.line.color.rgb = GRADE
    ca.has_major_gridlines = False
    ca.tick_labels.font.size = Pt(12)
    ca.tick_labels.font.color.rgb = TEXTO
    ca.tick_label_position = XL_TICK_LABEL_POSITION.LOW


def _rotulos(plot, formato: str, posicao=XL_LABEL_POSITION.OUTSIDE_END, tamanho=12, cor=TEXTO, negrito=True):
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = formato
    dl.number_format_is_linked = False
    dl.position = posicao
    dl.font.size = Pt(tamanho)
    dl.font.bold = negrito
    dl.font.color.rgb = cor


# ------------------------------------------------------------- slides


def _valor(texto: str) -> float:
    return float(texto.replace("R$", "").replace(".", "").replace(",", ".").strip() or 0)


def _grupos(r: dict, regime: str) -> dict[str, float]:
    detalhe = {"SIMPLES_NACIONAL": r["simples"], "LUCRO_PRESUMIDO": r["presumido"], "LUCRO_REAL": r["real"]}[regime]
    return {nome: sum(t["valor"] for t in detalhe["tributos"] if t["competencia"] is None and t["tributo"] in tributos)
            for nome, tributos, _ in GRUPOS}


def _paleta(melhor: str, atual: str) -> dict[str, tuple[RGBColor, RGBColor]]:
    """Cor forte e tinta de cada regime, sempre três cores distintas.

    Verde = menor carga, petróleo = regime atual; os demais recebem azul-acinzentado e ardósia, nessa ordem.
    """
    out = {melhor: (MELHOR, RGBColor(0xD5, 0xEB, 0xDE))}
    if atual != melhor:
        out[atual] = (MARCA, RGBColor(0xD3, 0xE5, 0xEB))
    resto = iter([(RGBColor(0x4F, 0x8F, 0xA4), RGBColor(0xDB, 0xE9, 0xEE)), (APOIO, RGBColor(0xE1, 0xE5, 0xE9))])
    for k in ORDEM:
        if k not in out:
            out[k] = next(resto)
    return out


def _rosca(deck: "Deck", s, x, y, diametro, fracao: float, cor: RGBColor, tinta: RGBColor, nome: str) -> None:
    """Anel único e grosso, começando no topo, sem rótulos: o percentual vai num texto sobre o centro."""
    dados = CategoryChartData()
    dados.categories = ["Tributos", "Resto da receita"]
    dados.add_series(nome, [max(fracao, 0), max(1 - fracao, 0)])
    ch = deck.grafico(s, XL_CHART_TYPE.DOUGHNUT, dados, x, y, diametro, diametro, f"Gráfico: {nome}")
    plot = ch.plots[0]
    for j, c in enumerate((cor, tinta)):
        ponto = plot.series[0].points[j]
        ponto.format.fill.solid()
        ponto.format.fill.fore_color.rgb = c
        ponto.format.line.fill.background()
    furo = plot._element.find(qn("c:holeSize"))
    if furo is None:
        furo = plot._element.makeelement(qn("c:holeSize"), {})
        plot._element.append(furo)
    furo.set("val", "68")


def _passos(r: dict, atual: str, anual: float, oportunidades: list[dict]) -> list[str]:
    """Próximos passos em linguagem de cliente (o texto do relatório PDF é escrito para o contador)."""
    melhor = r["melhor_regime"]
    comp = {c["regime"]: c for c in r["comparativo"]}
    passos = []
    if melhor != atual:
        economia = (comp[atual]["total"] - comp[melhor]["total"]) * anual
        passos.append(f"Mudar do {REGIMES[atual]} para o {REGIMES[melhor]} em janeiro: economia estimada de {brl(economia)} por ano. "
                      "A opção vale para o ano inteiro.")
    else:
        passos.append(f"Manter o {REGIMES[atual]}: é o regime de menor carga com os números de hoje.")
    anos = [a for a in r["reforma"] if a["ano"] > 2026]
    if anos:
        if {a["melhor"] for a in anos} == {melhor}:
            passos.append(f"Com a Reforma Tributária ({anos[0]['ano']} a {anos[-1]['ano']}), o {REGIMES[melhor]} continua o melhor: "
                          "reavaliar a cada ano com os números novos.")
        else:
            passos.append("Com a Reforma Tributária o melhor regime muda ao longo dos anos: reavaliar a escolha a cada janeiro.")
    altas = sorted((o for o in oportunidades if o["prioridade"] == "ALTA" and o["impacto"]), key=lambda o: -float(o["impacto"]))[:3]
    if altas:
        passos.append("Começar pelas oportunidades de maior valor: "
                      + "; ".join(f"{frase(o['titulo'], 60, ponto=False)} ({brl(float(o['impacto']))})" for o in altas) + ".")
    if r["pontos_criticos"]:
        passos.append("Antes de formalizar, enviar ao escritório os dados que faltam (folha, estoque e o que aparece no slide anterior).")
    return passos[:4]


def montar(d: DadosRelatorio) -> bytes:
    deck = Deck(d)
    r = d.resultado
    meses = len(d.competencias)
    anual = 12 / meses
    receita = r["base"]["TOTAL"]["receita_liquida"]
    comp = {c["regime"]: c for c in r["comparativo"]}
    melhor, atual = r["melhor_regime"], d.regime_atual
    ordenados = sorted(r["comparativo"], key=lambda c: c["posicao"])
    economia = (comp[atual]["total"] - comp[melhor]["total"]) * anual if atual in comp else 0
    muda = melhor != atual

    # 1. capa ------------------------------------------------------------------
    s = deck.slide(escuro=True, notas=(
        f"Apresentação do planejamento tributário da {d.razao_social}. Período analisado: {deck.periodo} "
        f"({_meses(meses)}). Objetivo: comparar quanto a empresa pagaria de tributos em cada regime e indicar o de menor carga."))
    _texto(s, MARGEM, Inches(1.6), Inches(11), Inches(0.4), "Planejamento tributário", tamanho=20, cor=CLARO)
    _texto(s, MARGEM, Inches(2.1), Inches(12), Inches(1.6), d.razao_social, tamanho=44, negrito=True, cor=BRANCO,
           ancora=MSO_ANCHOR.TOP, nome="Empresa")
    _texto(s, MARGEM, Inches(3.55), LARGURA - 2 * MARGEM, Inches(0.9),
           [f"Simples Nacional, Lucro Presumido e Lucro Real comparados com os dados de {deck.periodo}"], tamanho=20, cor=CLARO)
    _texto(s, MARGEM, Inches(6.3), Inches(8), Inches(0.6),
           [[(d.escritorio, {"negrito": True, "cor": BRANCO})], f"{d.gerado_em:%d/%m/%Y}"], tamanho=14, cor=CLARO)
    if d.preliminar:
        _etiqueta(s, MARGEM, Inches(1.05), "Versão preliminar", ESCURO, ALERTA_FUNDO, tamanho=12)

    # 2. a resposta ------------------------------------------------------------
    if muda:
        titulo = f"O {REGIMES[melhor]} reduz os tributos em {brl(economia)} por ano"
        destaque, legenda = brl(economia), f"de economia estimada por ano, saindo do {REGIMES[atual]} para o {REGIMES[melhor]}"
    else:
        segundo = ordenados[1]
        folga = segundo["diferenca_melhor"] * anual
        titulo = f"O {REGIMES[atual]} continua sendo o regime de menor carga"
        destaque, legenda = brl(folga), f"por ano a mais seria pago no {REGIMES[segundo['regime']]}, o segundo colocado"
    s = deck.slide(titulo, notas=(
        f"Mensagem principal. Com a receita líquida de {brl(receita)} em {_meses(meses)}, a carga em cada regime foi: "
        + "; ".join(f"{REGIMES[c['regime']]} {brl(c['total'])} ({pct(c['aliquota_efetiva'])} da receita)" for c in ordenados)
        + ". Valores anuais são a média do período multiplicada por 12."))
    _texto(s, MARGEM, Inches(2.0), Inches(4.3), Inches(1.1), destaque, tamanho=54, negrito=True, cor=MELHOR, nome="Número em destaque")
    _texto(s, MARGEM, Inches(3.15), Inches(4.0), Inches(1.2), legenda, tamanho=17, cor=APOIO)
    _texto(s, MARGEM, Inches(5.45), Inches(4.0), Inches(1.3),
           f"Base: {brl(receita)} de receita líquida em {_meses(meses)} ({deck.periodo}). {enquadramento_simples(r['simples'], receita)}",
           tamanho=12, cor=SUAVE)
    # uma rosca por regime: o arco é a parte da receita que vai para tributos
    coluna = Inches(2.62)
    x_col = LARGURA - MARGEM - 3 * coluna
    diametro = Inches(2.15)
    paleta = _paleta(melhor, atual)
    for i, c in enumerate(ordenados):
        cor, tinta = paleta[c["regime"]]
        x = x_col + i * coluna
        cx = x + (coluna - diametro) // 2
        _rosca(deck, s, cx, Inches(1.8), diametro, c["aliquota_efetiva"], cor, tinta, f"Rosca {REGIMES[c['regime']]}")
        _texto(s, cx, Inches(1.8) + diametro // 2 - Inches(0.36), diametro, Inches(0.72), [
            [(pct(c["aliquota_efetiva"]), {"tamanho": 28, "negrito": True, "cor": TEXTO})],
            [("da receita", {"tamanho": 11, "cor": APOIO})],
        ], alinhar=PP_ALIGN.CENTER, nome=f"Percentual {REGIMES[c['regime']]}")
        etiqueta = _caixa(s, x + Inches(0.16), Inches(4.2), coluna - Inches(0.32), Inches(0.42), cor, nome=f"Etiqueta {REGIMES[c['regime']]}")
        etiqueta.adjustments[0] = 0.25
        tf = etiqueta.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        pr = tf.paragraphs[0]
        pr.alignment = PP_ALIGN.CENTER
        run = pr.add_run()
        run.text = REGIMES[c["regime"]]
        run.font.name, run.font.size, run.font.bold, run.font.color.rgb = FONTE, Pt(15), True, BRANCO
        detalhe = "menor carga" if c["regime"] == melhor else f"+ {brl(c['diferenca_melhor'])}"
        _texto(s, x, Inches(4.8), coluna, Inches(1.2), [
            [(brl(c["total"]), {"tamanho": 20, "negrito": True, "cor": MELHOR if c["regime"] == melhor else TEXTO})],
            [(detalhe, {"tamanho": 13, "cor": MELHOR if c["regime"] == melhor else APOIO})],
            *([[("regime atual", {"tamanho": 13, "negrito": True, "cor": MARCA})]] if c["regime"] == atual else []),
        ], alinhar=PP_ALIGN.CENTER, espaco=2)

    # 3. quanto se paga em cada regime -----------------------------------------
    maior, menor = ordenados[-1], ordenados[0]
    s = deck.slide(f"No período, a diferença entre o regime mais caro e o mais barato foi de {brl(maior['total'] - menor['total'])}", notas=(
        "Total de tributos do período em cada regime: ICMS, PIS, COFINS, IRPJ, CSLL e INSS patronal (no Simples, a CPP dentro do DAS). "
        f"Em um ano, a diferença entre {REGIMES[maior['regime']]} e {REGIMES[menor['regime']]} chega a {brl((maior['total'] - menor['total']) * anual)}."))
    dados = CategoryChartData()
    dados.categories = [REGIMES[k] for k in ORDEM]
    dados.add_series("Tributos no período", [comp[k]["total"] for k in ORDEM])
    ch = deck.grafico(s, XL_CHART_TYPE.COLUMN_CLUSTERED, dados, MARGEM, Inches(1.65), Inches(7.6), Inches(5.1),
                      "Gráfico: tributos do período por regime")
    _eixos_discretos(ch)
    plot = ch.plots[0]
    plot.gap_width = 70
    _rotulos(plot, MOEDA, tamanho=14)
    for i, k in enumerate(ORDEM):
        ponto = plot.series[0].points[i]
        ponto.format.fill.solid()
        ponto.format.fill.fore_color.rgb = MELHOR if k == melhor else (MARCA if k == atual else SUAVE)
    xc = Inches(8.7)
    _texto(s, xc, Inches(1.9), Inches(4.0), Inches(0.4), "Carga sobre a receita", tamanho=14, cor=APOIO)
    yy = Inches(2.35)
    for c in ordenados:
        _texto(s, xc, yy, Inches(2.6), Inches(0.5), REGIMES[c["regime"]], tamanho=18, cor=TEXTO, negrito=c["regime"] == melhor)
        _texto(s, xc + Inches(2.6), yy, Inches(1.4), Inches(0.5), pct(c["aliquota_efetiva"]), tamanho=18, negrito=True,
               cor=MELHOR if c["regime"] == melhor else TEXTO, alinhar=PP_ALIGN.RIGHT)
        yy += Inches(0.55)
    _texto(s, xc, Inches(4.3), Inches(4.0), Inches(1.6), [
        [("Em 12 meses", {"negrito": True, "cor": TEXTO})],
        f"{REGIMES[maior['regime']]} custaria {brl((maior['total'] - menor['total']) * anual)} a mais que o {REGIMES[menor['regime']]}.",
    ], tamanho=16, cor=APOIO, espaco=4)
    _texto(s, xc, Inches(6.05), Inches(4.0), Inches(0.5), "Verde: menor carga. Azul-petróleo: regime atual.", tamanho=11, cor=SUAVE)

    # 4. de onde vem a diferença -----------------------------------------------
    grupos = {k: _grupos(r, k) for k in ORDEM}
    if muda:
        difs = sorted(((g, grupos[atual][g] - grupos[melhor][g]) for g, _, _ in GRUPOS), key=lambda x: -abs(x[1]))
        principal = difs[0]
        titulo = (f"A maior diferença está no {principal[0]}: {brl(abs(principal[1]))} a "
                  f"{'menos' if principal[1] > 0 else 'mais'} no {REGIMES[melhor]}")
    else:
        titulo = "Cada regime cobra os tributos de um jeito diferente"
    s = deck.slide(titulo, notas=(
        "Composição da carga. No Simples tudo vem num boleto só (DAS), inclusive a CPP, que substitui o INSS patronal e é calculada "
        "sobre o faturamento. No Presumido e no Real, o INSS incide só sobre folha e pró-labore, o ICMS é apurado com débito e "
        "crédito e o IRPJ/CSLL dependem do lucro presumido ou do lucro real."))
    dados = CategoryChartData()
    dados.categories = [REGIMES[k] for k in ORDEM]
    for nome, _, _ in GRUPOS:
        dados.add_series(nome, [grupos[k][nome] for k in ORDEM])
    ch = deck.grafico(s, XL_CHART_TYPE.BAR_STACKED, dados, MARGEM, Inches(1.65), Inches(7.4), Inches(4.9),
                      "Gráfico: composição dos tributos por regime", legenda=True)
    _eixos_discretos(ch, valores_visiveis=True, formato=MOEDA)
    ch.category_axis.reverse_order = True
    plot = ch.plots[0]
    plot.gap_width = 55
    plot.overlap = 100
    for serie, (_, _, cor) in zip(plot.series, GRUPOS):
        serie.format.fill.solid()
        serie.format.fill.fore_color.rgb = cor
    # quadro da diferença: regime atual contra o de menor carga (ou o segundo colocado)
    outro = melhor if muda else ordenados[1]["regime"]
    xt, wt = Inches(8.4), Inches(4.33)
    tab = s.shapes.add_table(len(GRUPOS) + 2, 3, xt, Inches(1.8), wt, Inches(3.6))
    tab.name = "Quadro: diferença por tributo"
    t = tab.table
    t.columns[0].width, t.columns[1].width, t.columns[2].width = Inches(1.73), Inches(1.3), Inches(1.3)
    cab = ["Tributo", REGIMES[atual].replace("Lucro ", "L. "), REGIMES[outro].replace("Lucro ", "L. ")]
    linhas = [[g, brl(grupos[atual][g]), brl(grupos[outro][g])] for g, _, _ in GRUPOS]
    linhas.append(["Total", brl(comp[atual]["total"]), brl(comp[outro]["total"])])
    for i, linha in enumerate([cab] + linhas):
        for j, v in enumerate(linha):
            cel = t.cell(i, j)
            cel.fill.solid()
            cel.fill.fore_color.rgb = GRADE if i == 0 else (FUNDO_CARTAO if i == len(linhas) else BRANCO)
            cel.margin_left = cel.margin_right = Inches(0.08)
            tf = cel.text_frame
            tf.paragraphs[0].alignment = PP_ALIGN.RIGHT if j else PP_ALIGN.LEFT
            run = tf.paragraphs[0].add_run()
            run.text = v
            f = run.font
            f.name, f.size = FONTE, Pt(13)
            f.bold = i == 0 or i == len(linhas)
            menor = i > 0 and j == 2 and _valor(linhas[i - 1][2]) < _valor(linhas[i - 1][1])
            f.color.rgb = MELHOR if menor else TEXTO
    _texto(s, xt, Inches(5.6), wt, Inches(0.9),
           "Em verde, onde o outro regime paga menos. No Simples, a CPP dentro do DAS faz o papel do INSS patronal, "
           "mas é paga sobre o faturamento, com ou sem empregados.", tamanho=12, cor=APOIO)

    # 5. a operação mês a mês --------------------------------------------------
    base = r["base"]
    s = deck.slide("A operação no período: faturamento, compras e despesas", notas=(
        "Base de todo o cálculo. Receita líquida = faturamento menos devoluções. Compras de mercadorias e despesas informadas "
        "pela empresa no levantamento. Remessas sem venda (consignação, fulfillment) não entram na receita."))
    dados = CategoryChartData()
    dados.categories = [mes(c) for c in d.competencias]
    dados.add_series("Receita líquida", [base[c]["receita_liquida"] for c in d.competencias])
    dados.add_series("Compras", [base[c]["compras"] for c in d.competencias])
    dados.add_series("Despesas", [base[c]["despesas"] for c in d.competencias])
    ch = deck.grafico(s, XL_CHART_TYPE.COLUMN_CLUSTERED, dados, MARGEM, Inches(1.65), Inches(8.2), Inches(5.0),
                      "Gráfico: receita, compras e despesas por mês", legenda=True)
    _eixos_discretos(ch, valores_visiveis=True, formato=MOEDA)
    plot = ch.plots[0]
    plot.gap_width = 80
    plot.overlap = -10
    for serie, cor in zip(plot.series, (MARCA, RGBColor(0x9E, 0xC5, 0xD3), SUAVE)):
        serie.format.fill.solid()
        serie.format.fill.fore_color.rgb = cor
    tot = base["TOTAL"]
    yy = Inches(1.85)
    for rotulo, valor, nota in (
        ("Receita líquida", brl(tot["receita_liquida"]), f"média de {brl(tot['receita_liquida'] / meses)} por mês"),
        ("Compras", brl(tot["compras"]), f"{pct(tot['compras'] / receita, 0)} da receita" if receita else ""),
        ("Despesas", brl(tot["despesas"]), f"{pct(tot['despesas'] / receita, 0)} da receita" if receita else ""),
    ):
        _texto(s, Inches(9.3), yy, Inches(3.4), Inches(1.4), [
            [(rotulo, {"tamanho": 14, "cor": APOIO})],
            [(valor, {"tamanho": 28, "negrito": True, "cor": TEXTO})],
            [(nota, {"tamanho": 12, "cor": SUAVE})],
        ])
        yy += Inches(1.55)

    # 6. como é formada a receita ----------------------------------------------
    mono = tot.get("receita_monofasica", 0) or 0
    interest = tot.get("receita_interestadual", 0) or 0
    s = deck.slide(f"{pct(mono / receita, 0)} da receita vem de produtos com PIS e COFINS já pagos na fábrica" if receita else
                   "Como é formada a receita", notas=(
        "Produtos monofásicos (autopeças, Lei 10.485/2002; bebidas frias, Lei 13.097/2015): o PIS e a COFINS são cobrados uma vez só, no fabricante ou importador. "
        "Na revenda, essa parte da receita não paga PIS/COFINS de novo, em nenhum regime; no Simples, precisa ser segregada no PGDAS-D. "
        "Vendas para outros estados usam alíquota interestadual de ICMS."))
    for i, (titulo_g, fatias, cores, texto_apoio) in enumerate((
        ("PIS e COFINS", [("Monofásicos", mono), ("Tributação normal", receita - mono)], (MARCA, GRADE),
         "A parte monofásica não paga PIS e COFINS de novo na revenda."),
        ("ICMS", [("Para outros estados", interest), ("Dentro do estado", receita - interest)], (RGBColor(0x4F, 0x8F, 0xA4), GRADE),
         "Vendas para outros estados usam a alíquota interestadual: 4% para importados, 7% ou 12% conforme o destino."),
    )):
        x = MARGEM + i * Inches(6.2)
        dados = CategoryChartData()
        dados.categories = [f[0] for f in fatias]
        dados.add_series(titulo_g, [max(f[1], 0) for f in fatias])
        ch = deck.grafico(s, XL_CHART_TYPE.DOUGHNUT, dados, x, Inches(1.75), Inches(3.4), Inches(3.4), f"Gráfico: receita por {titulo_g}")
        plot = ch.plots[0]
        for j, cor in enumerate(cores):
            ponto = plot.series[0].points[j]
            ponto.format.fill.solid()
            ponto.format.fill.fore_color.rgb = cor
        _texto(s, x + Inches(3.6), Inches(2.2), Inches(2.4), Inches(2.8), [
            [(titulo_g, {"tamanho": 14, "cor": APOIO})],
            [(pct(fatias[0][1] / receita, 0) if receita else "–", {"tamanho": 40, "negrito": True, "cor": cores[0]})],
            [(fatias[0][0].lower(), {"tamanho": 16, "cor": TEXTO})],
            [(brl(fatias[0][1]), {"tamanho": 14, "cor": APOIO})],
        ])
        _texto(s, x, Inches(5.45), Inches(5.6), Inches(0.9), texto_apoio, tamanho=14, cor=APOIO)

    # 7. reforma tributária ----------------------------------------------------
    anos = r["reforma"]
    ultimo = anos[-1]
    melhores = {a["melhor"] for a in anos}
    titulo = (f"Na Reforma Tributária, o {REGIMES[ultimo['melhor']]} segue com a menor carga até {ultimo['ano']}" if len(melhores) == 1 else
              f"Na Reforma Tributária o melhor regime muda: {REGIMES[ultimo['melhor']]} em {ultimo['ano']}")
    s = deck.slide(titulo, notas=(
        "Projeção com a mesma operação do período analisado. 2027: CBS substitui PIS/COFINS. De 2029 a 2032 o ICMS diminui aos poucos "
        "e o IBS cresce; em 2033 o ICMS acaba. As alíquotas de CBS e IBS são as projeções oficiais e ainda podem mudar. "
        "A opção de regime é anual: reavaliar a cada janeiro. Em reais por ano: "
        + "; ".join(f"{a['ano']}: " + ", ".join(f"{REGIMES[k]} {brl(a['cargas'][k] * anual)}" for k in ORDEM) for a in (anos[0], anos[-1]))
        + "."))
    # em percentual da receita (alíquota efetiva): compara regimes e anos sem depender do tamanho da empresa
    dados = CategoryChartData(number_format="0.0%")
    dados.categories = [str(a["ano"]) for a in anos]
    for k in ORDEM:
        dados.add_series(REGIMES[k], [a["aliquotas"][k] for a in anos])
    ch = deck.grafico(s, XL_CHART_TYPE.LINE_MARKERS, dados, MARGEM, Inches(1.65), Inches(8.4), Inches(5.0),
                      "Gráfico: alíquota efetiva por regime de 2026 a 2033", legenda=True)
    _eixos_discretos(ch, valores_visiveis=True, formato="0%")
    # pontas com rótulo só quando as linhas estão afastadas (abaixo de 1,5 ponto os números se sobrepõem)
    pontas = [j for j in (0, len(anos) - 1)
              if min(abs(anos[j]["aliquotas"][a] - anos[j]["aliquotas"][b]) for a in ORDEM for b in ORDEM if a < b) >= 0.015]
    for serie, k in zip(ch.plots[0].series, ORDEM):
        cor = _paleta(ultimo["melhor"], atual)[k][0]
        serie.smooth = False
        serie.format.line.color.rgb = cor
        serie.format.line.width = Pt(3.5 if k == ultimo["melhor"] else 2.25)
        serie.marker.style = XL_MARKER_STYLE.CIRCLE
        serie.marker.size = 7
        serie.marker.format.fill.solid()
        serie.marker.format.fill.fore_color.rgb = cor
        serie.marker.format.line.color.rgb = cor
        # o valor só nas pontas (hoje e fim da transição): no meio, a linha já conta a história
        for j in pontas:
            rotulo = serie.points[j].data_label
            rotulo.number_format, rotulo.number_format_is_linked = "0.0%", False
            rotulo.position = XL_LABEL_POSITION.ABOVE
            rotulo.show_value = True
            rotulo.font.size, rotulo.font.bold, rotulo.font.color.rgb = Pt(11), True, cor
    primeiro = anos[0]
    _texto(s, Inches(9.5), Inches(1.9), Inches(3.2), Inches(4.4), [
        [("Carga sobre a receita", {"tamanho": 14, "cor": APOIO})],
        [(f"{primeiro['ano']} (regras atuais)", {"tamanho": 14, "negrito": True, "cor": TEXTO})],
        *[[(f"{REGIMES[k]}: {pct(primeiro['aliquotas'][k])}", {"tamanho": 14, "cor": APOIO})] for k in ORDEM],
        [(f"{ultimo['ano']} (Reforma completa)", {"tamanho": 14, "negrito": True, "cor": TEXTO})],
        *[[(f"{REGIMES[k]}: {pct(ultimo['aliquotas'][k])}", {"tamanho": 14, "cor": MELHOR if k == ultimo["melhor"] else APOIO,
                                                              "negrito": k == ultimo["melhor"]})] for k in ORDEM],
    ], espaco=6)

    # 8. se o faturamento crescer ----------------------------------------------
    cen = r["crescimento"]
    rotulos, vistos = [], set()
    for i, c in enumerate(cen):
        valor = milhoes(c["rbt12"])
        # R$ 3.600.000,00 e R$ 3.600.000,01 arredondam igual: o segundo é o primeiro centavo acima do sublimite
        rotulos.append(f"{valor} (hoje)" if i == 0 else (f"acima de {valor}" if valor in vistos else valor))
        vistos.add(valor)
    virada = next((c for c in cen[1:] if c["melhor"] != cen[0]["melhor"]), None)
    titulo = (f"Se o faturamento crescer, o {REGIMES[cen[0]['melhor']]} continua mais vantajoso" if virada is None else
              f"Com faturamento de {milhoes(virada['rbt12'])} por ano, o melhor regime passa a ser o {REGIMES[virada['melhor']]}")
    s = deck.slide(titulo, notas=(
        "Simulação de crescimento: mesma estrutura de custos, receita de 12 meses maior. No Simples, a alíquota sobe por faixa; "
        "acima de R$ 3,6 milhões o ICMS sai do DAS (sublimite) e acima de R$ 4,8 milhões a empresa não pode ficar no Simples."))
    dados = CategoryChartData(number_format="0.0%")
    dados.categories = rotulos
    for k, chave in zip(ORDEM, ("aliquota_simples", "aliquota_lp", "aliquota_lr")):
        dados.add_series(REGIMES[k], [c[chave] for c in cen])
    ch = deck.grafico(s, XL_CHART_TYPE.COLUMN_CLUSTERED, dados, MARGEM, Inches(1.65), Inches(8.9), Inches(5.0),
                      "Gráfico: carga sobre a receita por cenário de faturamento", legenda=True)
    _eixos_discretos(ch, valores_visiveis=True, formato="0%")
    plot = ch.plots[0]
    plot.gap_width = 70
    plot.overlap = -5
    for serie, k in zip(plot.series, ORDEM):
        serie.format.fill.solid()
        serie.format.fill.fore_color.rgb = MELHOR if k == cen[0]["melhor"] else COR_REGIME[k]
    _rotulos(plot, "0.0%", tamanho=10, negrito=False, cor=APOIO)
    _texto(s, Inches(9.9), Inches(1.9), Inches(2.83), Inches(4.4), [
        [("Faturamento de 12 meses", {"tamanho": 14, "cor": APOIO})],
        [(milhoes(cen[0]["rbt12"]), {"tamanho": 30, "negrito": True})],
        [("hoje", {"tamanho": 14, "cor": APOIO})],
        [("Até R$ 3,6 mi o ICMS fica dentro do DAS. Acima de R$ 4,8 mi, o Simples deixa de ser permitido.", {"tamanho": 14, "cor": TEXTO})],
    ], espaco=8)

    # 9. oportunidades ---------------------------------------------------------
    com_valor = sorted((o for o in d.oportunidades if o["impacto"]), key=lambda o: -float(o["impacto"]))[:4]
    sem_valor = [o for o in d.oportunidades if not o["impacto"]]
    if com_valor:
        soma = sum(float(o["impacto"]) for o in com_valor)
        s = deck.slide(f"Oportunidades que somam {brl(soma)} no período", notas=(
            "Ações que reduzem a carga ou recuperam valores pagos a mais, com o impacto calculado no período. "
            + ("Outras oportunidades sem valor calculado: " + "; ".join(o["titulo"] for o in sem_valor) + "." if sem_valor else "")))
        cw, chh = Inches(5.92), Inches(2.3)
        for i, o in enumerate(com_valor):
            x = MARGEM + (i % 2) * (cw + Inches(0.3))
            y = Inches(1.7) + (i // 2) * (chh + Inches(0.3))
            _caixa(s, x, y, cw, chh, FUNDO_CARTAO, nome=f"Oportunidade {i + 1}")
            _texto(s, x + Inches(0.3), y + Inches(0.25), cw - Inches(0.6), Inches(0.6), brl(float(o["impacto"])), tamanho=28, negrito=True, cor=MELHOR)
            _texto(s, x + Inches(0.3), y + Inches(0.85), cw - Inches(0.6), Inches(0.55), frase(o["titulo"], 62, ponto=False),
                   tamanho=16, negrito=True, ancora=MSO_ANCHOR.TOP)
            _texto(s, x + Inches(0.3), y + Inches(1.45), cw - Inches(0.6), Inches(0.75), frase(o["acao"], 125), tamanho=13, cor=APOIO)

    # 10. pontos de atenção ----------------------------------------------------
    pontos = [frase(p["texto"], 200) for p in r["pontos_criticos"]][:5]
    if pontos:
        s = deck.slide("O que ainda precisa ser confirmado antes da decisão", notas=(
            "Premissas que podem mudar o resultado. Pedir à empresa os dados que faltam antes de formalizar a troca de regime."
            + (" Itens ainda não informados no levantamento: " + "; ".join(d.pendencias) + "." if d.pendencias else "")))
        y = Inches(1.75)
        for i, p in enumerate(pontos):
            _circulo(s, MARGEM, y + Inches(0.2), Inches(0.45), "!", ALERTA_FUNDO, ALERTA, 16, f"Marcador {i + 1}")
            _texto(s, MARGEM + Inches(0.75), y, Inches(11.3), Inches(0.85), p, tamanho=17, ancora=MSO_ANCHOR.MIDDLE)
            y += Inches(0.95)

    # 11. recomendação e próximos passos ---------------------------------------
    s = deck.slide("Recomendação e próximos passos", escuro=True, notas=(
        "Recomendação do escritório. A troca de regime é feita em janeiro e vale para o ano inteiro; "
        "antes disso, confirmar as premissas do slide anterior."))
    y = Inches(1.75)
    for i, linha in enumerate(_passos(r, atual, anual, d.oportunidades), start=1):
        _circulo(s, MARGEM, y, Inches(0.5), str(i), MARCA, BRANCO, 18, f"Passo {i}")
        linhas_texto = -(-len(linha) // 115)  # ~115 caracteres por linha a 17pt nessa largura
        _texto(s, MARGEM + Inches(0.85), y + Inches(0.08), Inches(11.2), Inches(0.32 * linhas_texto + 0.1), linha, tamanho=17, cor=BRANCO)
        y += Inches(max(0.75, 0.32 * linhas_texto + 0.45))
    _texto(s, MARGEM, Inches(6.75), Inches(12), Inches(0.4),
           f"{d.escritorio}. Valores calculados com os dados de {deck.periodo}; anuais = média do período × 12.", tamanho=11, cor=CLARO)

    buf = io.BytesIO()
    deck.prs.save(buf)
    return buf.getvalue()


def gerar(db, sim, usuario) -> bytes:
    from app.services.relatorio_pdf import coletar

    return montar(coletar(db, sim, usuario, None))
