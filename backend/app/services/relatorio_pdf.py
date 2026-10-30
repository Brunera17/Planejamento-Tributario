"""Relatório do planejamento em PDF (A4), no mesmo sistema visual da aplicação.

Estrutura: ficha de identificação, veredito com a composição da carga, quadro-síntese 2026/2027/2033,
oportunidades, crescimento, pontos críticos, recomendação e anexos (regimes, base, despesas, memória,
histórico, fontes). Gerado com ReportLab (Python puro), sem dependências do sistema operacional.
"""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Bem,
    Documento,
    GrupoDespesa,
    HistoricoStatus,
    ItemDespesa,
    Levantamento,
    LevantamentoItem,
    OportunidadeRegistro,
    OutraDespesa,
    Planejamento,
    RelatorioPdf,
    Simulacao,
    TipoDocumento,
    Usuario,
)
from app.services import progresso

FUSO = ZoneInfo("America/Sao_Paulo")
REGIMES = {"SIMPLES_NACIONAL": "Simples Nacional", "LUCRO_PRESUMIDO": "Lucro Presumido", "LUCRO_REAL": "Lucro Real"}
TIPOS_BEM = {"VEICULOS": "Veículos", "MOVEIS_UTENSILIOS": "Móveis e utensílios",
             "MAQUINAS_EQUIPAMENTOS": "Máquinas e equipamentos", "IMOVEL": "Imóvel"}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
FONTES_LEGAIS = [
    "LC 123/2006 (Simples Nacional, Anexo I)",
    "Leis 9.249/1995, 9.430/1996 e 9.718/1998 (IRPJ, CSLL e PIS/COFINS cumulativos)",
    "Leis 10.637/2002 e 10.833/2003 (PIS/COFINS não cumulativos)",
    "Lei 10.485/2002 (PIS/COFINS monofásico de autopeças)",
    "LC 87/1996 (ICMS)",
    "LC 224/2025 e IN RFB 2.305/2025 (acréscimo da presunção)",
    "EC 132/2023 e LC 214/2025 (Reforma Tributária: CBS e IBS)",
    "RE 574.706 (Tema 69/STF)",
]

# ------------------------------------------------------------- identidade

COR = {
    "texto": colors.HexColor("#1F2933"),
    "apoio": colors.HexColor("#52606D"),
    "marca": colors.HexColor("#155E75"),
    "superficie": colors.HexColor("#E4E9EF"),
    "borda": colors.HexColor("#CBD2D9"),
    "sucesso": colors.HexColor("#22543D"),
    "sucesso_fundo": colors.HexColor("#E6F4EC"),
    "alerta": colors.HexColor("#C53030"),
    "aviso_fundo": colors.HexColor("#FBEFD9"),
    "aviso_texto": colors.HexColor("#744210"),
}
GRUPOS = [
    ("ICMS", ("ICMS",), colors.HexColor("#155E75")),
    ("PIS e COFINS", ("PIS", "COFINS", "PIS/COFINS"), colors.HexColor("#4F8FA4")),
    ("IRPJ e CSLL", ("IRPJ", "CSLL"), colors.HexColor("#9EC5D3")),
    ("CPP e INSS", ("CPP", "INSS patronal"), colors.HexColor("#52606D")),
]

PASTA_FONTES = Path(__file__).resolve().parents[1] / "assets" / "fonts"


def _registrar_fontes() -> tuple[str, str, bool]:
    """Usa a Archivo (a mesma da aplicação) se os TTF estiverem em app/assets/fonts; senão, Helvetica."""
    normal, forte = PASTA_FONTES / "Archivo-Regular.ttf", PASTA_FONTES / "Archivo-SemiBold.ttf"
    if normal.exists() and forte.exists():
        if "Archivo" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("Archivo", str(normal)))
            pdfmetrics.registerFont(TTFont("Archivo-SemiBold", str(forte)))
        return "Archivo", "Archivo-SemiBold", True
    return "Helvetica", "Helvetica-Bold", False


FONTE, FONTE_FORTE, FONTE_UNICODE = _registrar_fontes()

# As fontes padrão do PDF só cobrem o Latin-1: troca os símbolos que ficariam em branco.
_SUBSTITUI = {"−": "–", "Σ": "soma de", "≤": "<=", "≥": ">=", "≠": "<>", "→": "->", "⚠": "!", "✔": "", "★": ""}


def t(texto) -> str:
    s = "" if texto is None else str(texto)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if not FONTE_UNICODE:
        for a, b in _SUBSTITUI.items():
            s = s.replace(a, b)
    return s


def estilo(nome: str, **kw) -> ParagraphStyle:
    base = dict(fontName=FONTE, fontSize=9.5, leading=13.5, textColor=COR["texto"])
    base.update(kw)
    return ParagraphStyle(nome, **base)


E = {
    "corpo": estilo("corpo"),
    "apoio": estilo("apoio", textColor=COR["apoio"], fontSize=8.5, leading=12),
    "rotulo": estilo("rotulo", textColor=COR["apoio"], fontSize=7, leading=9),
    "campo": estilo("campo", fontName=FONTE_FORTE, fontSize=9.5, leading=12),
    "veredito": estilo("veredito", fontName=FONTE_FORTE, fontSize=24, leading=28, spaceAfter=6),
    "lead": estilo("lead", fontSize=11, leading=16, textColor=COR["apoio"]),
    "h2": estilo("h2", fontName=FONTE_FORTE, fontSize=12.5, leading=16, textColor=COR["marca"], spaceBefore=14, spaceAfter=6),
    "h3": estilo("h3", fontName=FONTE_FORTE, fontSize=10, leading=13, spaceBefore=8, spaceAfter=4),
    "celula": estilo("celula", fontSize=8, leading=10.5),
    "celula_forte": estilo("celula_forte", fontName=FONTE_FORTE, fontSize=8, leading=10.5),
    "celula_num": estilo("celula_num", fontSize=8, leading=10.5, alignment=TA_RIGHT),
    "aviso": estilo("aviso", textColor=COR["aviso_texto"], fontSize=8.5, leading=12),
}

# ------------------------------------------------------------- formatação


def brl(v) -> str:
    if v is None:
        return "–"
    s = f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def pct(v) -> str:
    return "–" if v is None else f"{float(v) * 100:.2f}%".replace(".", ",")


def mes(c: str) -> str:
    a, m = c.split("-")
    return f"{MESES[int(m) - 1]}/{a}"


def cnae_fmt(c: str | None) -> str:
    return f"{c[:4]}-{c[4]}/{c[5:]}" if c and len(c) == 7 else (c or "–")


def telefone_fmt(f: str | None) -> str:
    if not f:
        return "–"
    return f"({f[:2]}) {f[2:-4]}-{f[-4:]}" if len(f) in (10, 11) else f


def ncm_fmt(n: str) -> str:
    return f"{n[:4]}.{n[4:6]}.{n[6:]}" if len(n) == 8 else n


def acao_ncm(x: dict) -> str:
    acao = x["acao_recomendada"] or "–"
    if x["requer_revisao"] and not acao.lower().startswith(("revisar", "revise")):
        return f"Revisar: {acao}"
    return acao


def resumo_ncm(linhas: list[dict], receita: float) -> list[str]:
    """Frases de conclusão da verificação por NCM (equivalentes às notas da aba da planilha)."""
    if not linhas:
        return []
    revisar = [x for x in linhas if x["requer_revisao"]]
    frases = []
    if revisar:
        soma = sum(x["receita"] for x in revisar)
        frases.append(f"{len(revisar)} de {len(linhas)} NCMs precisam de revisão no cadastro, somando {brl(soma)} "
                      f"({pct(soma / receita if receita else 0)} da receita).")
    indicio = [ncm_fmt(x["ncm"]) for x in linhas if x["indicio_ncm_incorreto"]]
    if indicio:
        frases.append(f"Com indício de NCM incorreto que, reclassificados, passam a monofásicos: {', '.join(indicio)}.")
    if all(x["sujeito_st"] for x in linhas):
        frases.append("ICMS: todos os NCMs estavam sujeitos à substituição tributária; validar o CEST no cadastro.")
    ibs = {(x["cst_ibs_cbs"], x["cclass_trib"]) for x in linhas}
    beneficios = {x["beneficio_reforma"] for x in linhas}
    if len(ibs) == 1 and None not in next(iter(ibs)):
        cst, ccl = next(iter(ibs))
        extra = "."
        if len(beneficios) == 1 and None not in beneficios:
            b = next(iter(beneficios))
            extra = ", sem benefício na Reforma (alíquota padrão)." if b.startswith("Não") else f", com benefício na Reforma: {b}."
        frases.append(f"IBS/CBS: CST {cst} e cClassTrib {ccl} para todos os NCMs{extra}")
    return frases


def cnpj_fmt(c: str) -> str:
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else c


# ------------------------------------------------------------- dados


@dataclass
class DadosRelatorio:
    escritorio: str
    razao_social: str
    cnpj: str
    regime_atual: str
    cnae: str | None
    representante: str | None
    telefone: str | None
    competencias: list[str]
    versao: int
    tipo: str
    preliminar: bool
    motivos_preliminar: list[str]
    gerado_por: str
    gerado_em: datetime
    resultado: dict
    oportunidades: list[dict]
    recomendacao: list[str]
    progresso: int
    pendencias: list[str] = field(default_factory=list)
    despesas: list[tuple[str, list[tuple[str, list[float | None]]]]] = field(default_factory=list)
    historico: list[tuple[datetime, str, str | None, str, str | None]] = field(default_factory=list)
    bens: list[tuple[str, str, date, float]] = field(default_factory=list)
    sem_bens: bool = False
    documentos: list[tuple[str, list[str | None]]] = field(default_factory=list)  # None = pendente


def recomendacao_padrao(r: dict, regime_atual: str, meses: int) -> list[str]:
    """Texto-base da recomendação, montado a partir do resultado; o contador pode editar antes de emitir."""
    comp = sorted(r["comparativo"], key=lambda c: c["posicao"])
    melhor = r["melhor_regime"]
    linhas = []
    partes = [f"{REGIMES[c['regime']]} {pct(c['aliquota_efetiva'])}" for c in comp]
    ordem = ", ".join(partes[:-1]) + f" e {partes[-1]}"
    if melhor == regime_atual:
        linhas.append(f"Manter o {REGIMES[melhor]}: é o regime de menor carga no período analisado (carga sobre a receita: {ordem}).")
    else:
        totais = {c["regime"]: c["total"] for c in comp}
        economia = (totais[regime_atual] - totais[melhor]) * 12 / meses if regime_atual in totais else 0
        linhas.append(
            f"Avaliar a opção pelo {REGIMES[melhor]} para o próximo ano-calendário. Carga sobre a receita no período: {ordem}. "
            f"A economia estimada é de {brl(economia)} por ano em relação ao regime atual. "
            "A opção é formalizada em janeiro e vale para o ano inteiro."
        )
    anos = [a for a in r["reforma"] if a["ano"] > 2026]
    if anos:
        melhores = {a["melhor"] for a in anos}
        if melhores == {melhor}:
            linhas.append(f"Na transição da Reforma ({anos[0]['ano']} a {anos[-1]['ano']}), o {REGIMES[melhor]} mantém a menor carga em todos os anos simulados.")
        else:
            trocas = ", ".join(f"{a['ano']}: {REGIMES[a['melhor']]}" for a in anos)
            linhas.append(f"Na transição da Reforma o melhor regime muda ao longo dos anos ({trocas}); reavaliar a opção a cada ano.")
    altas = [o for o in r["oportunidades"] if o["prioridade"] == "ALTA" and o.get("impacto")]
    if altas:
        nomes = "; ".join(f"{o['titulo']} ({brl(o['impacto'])} no período)" for o in altas)
        linhas.append(f"Tratar primeiro as oportunidades de prioridade alta: {nomes}.")
    if r["pontos_criticos"]:
        linhas.append("Antes de decidir, validar as premissas listadas em Pontos críticos, em especial folha, estoque e classificação de NCM.")
    return linhas


def coletar(db: Session, sim: Simulacao, usuario: Usuario, recomendacao: list[str] | None) -> DadosRelatorio:
    p = db.get(Planejamento, sim.planejamento_id)
    emp = p.empresa
    r = json.loads(sim.resultado_json)
    comps = p.competencias()
    pct_prog, blocos = progresso.calcular(db, p)

    motivos = []
    if sim.tipo != "FINAL":
        motivos.append("a simulação tem pendências")
    if sim.desatualizada:
        motivos.append("os dados mudaram depois da simulação")
    if sim.aprovada_em is None:
        motivos.append("a simulação ainda não foi aprovada pelo contador")

    ops = db.scalars(select(OportunidadeRegistro).where(OportunidadeRegistro.simulacao_id == sim.id)).all()
    oportunidades = [{"titulo": o.titulo, "impacto": o.impacto, "prioridade": o.prioridade, "acao": o.acao, "situacao": o.situacao}
                     for o in ops if o.situacao != "DESCARTADA"]

    # despesas informadas, por grupo e competência
    levs = {lv.id: lv.competencia for lv in db.scalars(select(Levantamento).where(Levantamento.planejamento_id == p.id))}
    valores: dict[int, dict[str, float]] = {}
    for li in db.scalars(select(LevantamentoItem).where(LevantamentoItem.levantamento_id.in_(levs))):
        valores.setdefault(li.item_despesa_id, {})[levs[li.levantamento_id]] = float(li.valor)
    despesas = []
    for g in db.scalars(select(GrupoDespesa).order_by(GrupoDespesa.ordem)):
        linhas = [(i.nome, [valores[i.id].get(c) for c in comps])
                  for i in db.scalars(select(ItemDespesa).where(ItemDespesa.grupo_id == g.id).order_by(ItemDespesa.ordem))
                  if i.id in valores and any(valores[i.id].values())]
        outras: dict[str, list[float | None]] = {}  # mesma descrição em meses diferentes fica numa linha só
        for o in db.scalars(select(OutraDespesa).where(OutraDespesa.grupo_id == g.id, OutraDespesa.levantamento_id.in_(levs))):
            linha = outras.setdefault(o.descricao, [None] * len(comps))
            i = comps.index(levs[o.levantamento_id])
            linha[i] = (linha[i] or 0) + float(o.valor)
        linhas += [(f"Outras: {desc}", valores) for desc, valores in outras.items()]
        if linhas:
            despesas.append((g.nome, linhas))

    bens = [(TIPOS_BEM.get(b.tipo, b.tipo), b.descricao, b.data_aquisicao, float(b.valor))
             for b in db.scalars(select(Bem).where(Bem.empresa_id == emp.id).order_by(Bem.data_aquisicao.desc()))]

    # situação de cada documento em cada mês
    docs = {(levs[x.levantamento_id], x.tipo_documento_id): x
            for x in db.scalars(select(Documento).where(Documento.levantamento_id.in_(levs)))}

    def situacao(doc: Documento | None) -> str | None:
        if doc is None:
            return None
        if doc.nao_se_aplica:
            return f"Não se aplica: {doc.justificativa}"
        return doc.arquivo_nome or doc.arquivo

    documentos = [(t.nome, [situacao(docs.get((c, t.id))) for c in comps])
                  for t in db.scalars(select(TipoDocumento).order_by(TipoDocumento.ordem))]

    nomes = {u.id: u.nome for u in db.scalars(select(Usuario))}
    historico = [(h.data, nomes.get(h.usuario_id, "–"), h.status_de, h.status_para, h.motivo)
                 for h in db.scalars(select(HistoricoStatus).where(HistoricoStatus.planejamento_id == p.id).order_by(HistoricoStatus.data))]

    return DadosRelatorio(
        escritorio=get_settings().escritorio_nome,
        razao_social=emp.razao_social, cnpj=emp.cnpj, regime_atual=emp.regime_tributario, cnae=emp.cnae,
        representante=emp.representante_legal, telefone=emp.telefone, competencias=comps,
        versao=sim.versao, tipo=sim.tipo, preliminar=bool(motivos), motivos_preliminar=motivos,
        gerado_por=usuario.nome, gerado_em=datetime.now(FUSO), resultado=r, oportunidades=oportunidades,
        recomendacao=recomendacao or recomendacao_padrao(r, emp.regime_tributario, len(comps)),
        progresso=pct_prog,
        pendencias=[f"{b.esperados - b.preenchidos} em {progresso.NOMES[b.codigo].lower()}" for b in blocos if b.preenchidos < b.esperados],
        despesas=despesas, historico=historico, bens=bens, sem_bens=p.sem_bens, documentos=documentos,
    )


# ------------------------------------------------------------- componentes


class BarrasComposicao(Flowable):
    """Composição da carga de cada regime por grupo de tributo, na mesma escala."""

    def __init__(self, r: dict, largura: float, regime_atual: str):
        super().__init__()
        self.r, self.largura, self.regime_atual = r, largura, regime_atual
        self.linhas = sorted(r["comparativo"], key=lambda c: c["posicao"])
        self.altura_linha = 9 * mm
        self.height = self.altura_linha * len(self.linhas) + 8 * mm

    def wrap(self, *_):
        return self.largura, self.height

    def draw(self):
        c = self.canv
        detalhe = {"SIMPLES_NACIONAL": self.r["simples"], "LUCRO_PRESUMIDO": self.r["presumido"], "LUCRO_REAL": self.r["real"]}
        maior = max(x["total"] for x in self.linhas)
        x_barra, col_valor = 38 * mm, 52 * mm
        larg_barra = self.largura - x_barra - col_valor - 4 * mm
        for i, linha in enumerate(self.linhas):
            y = self.height - (i + 1) * self.altura_linha
            melhor = linha["regime"] == self.r["melhor_regime"]
            c.setFillColor(COR["texto"])
            c.setFont(FONTE_FORTE if melhor else FONTE, 9.5)
            c.drawString(0, y + 2.6 * mm, REGIMES[linha["regime"]])
            if linha["regime"] == self.regime_atual:
                c.setFont(FONTE, 7.5)
                c.setFillColor(COR["apoio"])
                c.drawString(0, y - 0.6 * mm, "regime atual")
            x = x_barra
            total_barra = larg_barra * linha["total"] / maior
            for _, tributos, cor in GRUPOS:
                v = sum(tt["valor"] for tt in detalhe[linha["regime"]]["tributos"] if tt["competencia"] is None and tt["tributo"] in tributos)
                if v <= 0:
                    continue
                w = total_barra * v / linha["total"]
                c.setFillColor(cor)
                c.rect(x, y + 1.2 * mm, w, 5.4 * mm, stroke=0, fill=1)
                c.setFillColor(colors.white)
                c.rect(x + w - 0.4, y + 1.2 * mm, 0.8, 5.4 * mm, stroke=0, fill=1)
                x += w
            c.setFont(FONTE_FORTE, 9.5)
            c.setFillColor(COR["sucesso"] if melhor else COR["texto"])
            c.drawRightString(self.largura - 26 * mm, y + 2.6 * mm, brl(linha["total"]))
            c.setFont(FONTE, 8.5)
            c.setFillColor(COR["sucesso"] if melhor else COR["apoio"])
            c.drawRightString(self.largura, y + 2.6 * mm, "menor carga" if melhor else f"+{brl(linha['diferenca_melhor'])}")
            c.setFillColor(COR["apoio"])
            c.drawRightString(self.largura - 26 * mm, y - 0.6 * mm, pct(linha["aliquota_efetiva"]))
        # legenda
        x = 0
        c.setFont(FONTE, 7.5)
        for nome, _, cor in GRUPOS:
            c.setFillColor(cor)
            c.rect(x, 1.2 * mm, 2.4 * mm, 2.4 * mm, stroke=0, fill=1)
            c.setFillColor(COR["apoio"])
            c.drawString(x + 3.6 * mm, 1.5 * mm, nome)
            x += 4 * mm + pdfmetrics.stringWidth(nome, FONTE, 7.5) + 5 * mm


def ficha(campos: list[tuple[str, str]], largura: float, colunas: int = 4) -> Table:
    """Caixas encostadas com rótulo pequeno no canto, como os campos de um DANFE."""
    linhas, atual = [], []
    for rot, val in campos:
        atual.append([Paragraph(t(rot), E["rotulo"]), Paragraph(t(val), E["campo"])])
        if len(atual) == colunas:
            linhas.append(atual)
            atual = []
    if atual:
        atual += [""] * (colunas - len(atual))
        linhas.append(atual)
    tab = Table(linhas, colWidths=[largura / colunas] * colunas)
    tab.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, COR["borda"]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tab


def tabela(cabecalho: list[str], linhas: list[list], larguras: list[float], numericas: set[int] = frozenset(),
           destaque_ultima: bool = False) -> Table:
    def cel(v, i, forte=False):
        if isinstance(v, Flowable):
            return v
        st = E["celula_num"] if i in numericas else (E["celula_forte"] if forte else E["celula"])
        return Paragraph(t(v), st)

    dados = [[Paragraph(t(c), estilo("cab", fontSize=7.5, leading=10, textColor=COR["apoio"],
                                     alignment=TA_RIGHT if i in numericas else 0)) for i, c in enumerate(cabecalho)]]
    for n, l in enumerate(linhas):
        forte = destaque_ultima and n == len(linhas) - 1
        dados.append([cel(v, i, forte) for i, v in enumerate(l)])
    tab = Table(dados, colWidths=larguras, repeatRows=1)
    estilos = [
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, COR["borda"]),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, COR["superficie"]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if destaque_ultima:
        estilos.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, COR["texto"]))
    tab.setStyle(TableStyle(estilos))
    return tab


class CanvasNumerado(rl_canvas.Canvas):
    """Canvas que conhece o total de páginas, para o rodapé 'Página X de Y'."""

    def __init__(self, *args, rodape=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas, self._rodape = [], rodape

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self._rodape(self, total)
            super().showPage()
        super().save()


# ------------------------------------------------------------- documento


def montar_pdf(d: DadosRelatorio) -> bytes:
    buf = io.BytesIO()
    margem = 16 * mm
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=margem, rightMargin=margem, topMargin=20 * mm,
                            bottomMargin=18 * mm, title=f"Planejamento tributário – {d.razao_social}",
                            author=d.escritorio, subject="Comparativo Simples Nacional, Lucro Presumido e Lucro Real")
    L = doc.width
    r = d.resultado
    periodo = f"{mes(d.competencias[0])} a {mes(d.competencias[-1])}"
    receita = r["base"]["TOTAL"]["receita_liquida"]
    meses = len(d.competencias)
    gerado = d.gerado_em.strftime("%d/%m/%Y às %H:%M")

    def cabecalho_rodape(c: rl_canvas.Canvas, total: int):
        w, h = A4
        c.saveState()
        if d.preliminar:
            c.setFillColor(COR["alerta"])
            c.setFillAlpha(0.08)
            c.setFont(FONTE_FORTE, 92)
            c.translate(w / 2, h / 2)
            c.rotate(40)
            c.drawCentredString(0, -30, "PRELIMINAR")
            c.rotate(-40)
            c.translate(-w / 2, -h / 2)
            c.setFillAlpha(1)
        c.setStrokeColor(COR["marca"])
        c.setLineWidth(1.2)
        c.line(margem, h - 12 * mm, w - margem, h - 12 * mm)
        c.setFont(FONTE_FORTE, 8)
        c.setFillColor(COR["marca"])
        c.drawString(margem, h - 10.5 * mm, d.escritorio)
        c.setFont(FONTE, 8)
        c.setFillColor(COR["apoio"])
        c.drawRightString(w - margem, h - 10.5 * mm, f"{d.razao_social}, planejamento tributário {periodo}")
        c.setStrokeColor(COR["borda"])
        c.setLineWidth(0.5)
        c.line(margem, 12 * mm, w - margem, 12 * mm)
        c.drawString(margem, 8.5 * mm, f"Gerado em {gerado} por {d.gerado_por}. Simulação {d.versao}" + (", preliminar" if d.preliminar else ""))
        c.drawRightString(w - margem, 8.5 * mm, f"Página {c.getPageNumber()} de {total}")
        c.restoreState()

    s: list = []

    # 1. identificação
    s.append(ficha([
        ("Empresa", d.razao_social), ("CNPJ", cnpj_fmt(d.cnpj)), ("Regime atual", REGIMES[d.regime_atual]),
        ("Período analisado", periodo), ("CNAE", cnae_fmt(d.cnae)), ("Representante legal", d.representante or "–"),
        ("Telefone", telefone_fmt(d.telefone)), ("Dados coletados", f"{d.progresso}%"),
    ], L))
    s.append(Spacer(1, 7 * mm))

    if d.preliminar:
        aviso = Table([[Paragraph(t("Relatório preliminar: " + "; ".join(d.motivos_preliminar) + ". Os valores podem mudar até a aprovação."), E["aviso"])]],
                      colWidths=[L])
        aviso.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), COR["aviso_fundo"]), ("LEFTPADDING", (0, 0), (-1, -1), 7),
                                   ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        s += [aviso, Spacer(1, 6 * mm)]

    # 2. veredito
    melhor = r["melhor_regime"]
    totais = {c["regime"]: c["total"] for c in r["comparativo"]}
    base = f"Base: {t(brl(receita))} de receita líquida em {meses} meses."
    if melhor == d.regime_atual:
        s.append(Paragraph(t(f"{REGIMES[melhor]} continua com a menor carga"), E["veredito"]))
        s.append(Paragraph(f"Mudar de regime não reduziria a carga no período. {base}", E["lead"]))
    else:
        economia = (totais[d.regime_atual] - totais[melhor]) * 12 / meses
        s.append(Paragraph(t(f"{REGIMES[melhor]} tem a menor carga"), E["veredito"]))
        s.append(Paragraph(f"Economia estimada de <font name='{FONTE_FORTE}' color='#22543D'>{t(brl(economia))} por ano</font> "
                           f"em relação ao {t(REGIMES[d.regime_atual])}, regime atual da empresa. {base}", E["lead"]))
    s.append(Spacer(1, 6 * mm))
    s.append(BarrasComposicao(r, L, d.regime_atual))
    s.append(Paragraph(t(f"Carga do período por regime; percentuais sobre a receita líquida de {brl(receita)}."), E["apoio"]))

    # 3. quadro-síntese
    s.append(Paragraph("Carga por regime hoje e na Reforma", E["h2"]))
    anos = {a["ano"]: a for a in r["reforma"]}
    marcos = [a for a in (2026, 2027, 2033) if a in anos]
    linhas = []
    for reg in ("SIMPLES_NACIONAL", "LUCRO_PRESUMIDO", "LUCRO_REAL"):
        linha = [REGIMES[reg]]
        for a in marcos:
            linha += [brl(anos[a]["cargas"][reg]), pct(anos[a]["aliquotas"][reg])]
        linhas.append(linha)
    linhas.append(["Menor carga"] + sum(([REGIMES[anos[a]["melhor"]], ""] for a in marcos), []))
    cab = ["Regime"] + sum(([f"{a}", "alíquota"] for a in marcos), [])
    quadro = tabela(cab, linhas, [34 * mm] + [(L - 34 * mm) / (2 * len(marcos))] * 2 * len(marcos),
                    numericas=set(range(1, 1 + 2 * len(marcos))), destaque_ultima=True)
    quadro.setStyle(TableStyle([("SPAN", (1 + 2 * i, -1), (2 + 2 * i, -1)) for i in range(len(marcos))]))
    s.append(quadro)
    s.append(Paragraph(t("2026: regras atuais. 2027: CBS substitui PIS/COFINS. 2033: IBS pleno e ICMS extinto. "
                         "Mesma base de operação do período analisado; alíquotas de CBS e IBS são projeções oficiais."), E["apoio"]))

    # 4. oportunidades
    if d.oportunidades:
        s.append(CondPageBreak(50 * mm))
        s.append(Paragraph("Oportunidades identificadas", E["h2"]))
        prio = {"ALTA": "Alta", "MEDIA": "Média", "BAIXA": "Baixa"}
        s.append(tabela(["Oportunidade", "Impacto no período", "Prioridade", "O que fazer"],
                        [[o["titulo"], brl(o["impacto"]) if o["impacto"] is not None else "qualitativo", prio.get(o["prioridade"], o["prioridade"]), o["acao"]]
                         for o in d.oportunidades],
                        [50 * mm, 26 * mm, 17 * mm, L - 93 * mm], numericas={1}))

    # 5. crescimento
    s.append(CondPageBreak(45 * mm))
    s.append(Paragraph("Se o faturamento crescer", E["h2"]))
    s.append(tabela(["Receita de 12 meses", "Simples", "Presumido", "Real", "Menor carga", "Observação"],
                    [[brl(c["rbt12"]), "inelegível" if c["aliquota_simples"] is None else pct(c["aliquota_simples"]), pct(c["aliquota_lp"]),
                      pct(c["aliquota_lr"]), REGIMES[c["melhor"]], c["observacao"]] for c in r["crescimento"]],
                    [30 * mm, 18 * mm, 18 * mm, 16 * mm, 28 * mm, L - 110 * mm], numericas={0, 1, 2, 3}))
    if r.get("margem_equilibrio_lr_lp") is not None:
        s.append(Paragraph(t(f"Margem de equilíbrio entre Lucro Real e Presumido: {pct(r['margem_equilibrio_lr_lp'])} de lucro antes dos tributos "
                             f"sobre a receita (atual: {pct(r['real']['detalhes']['margem_lair'])}). Abaixo dela, o Lucro Real fica mais barato."), E["apoio"]))

    # 6. pontos críticos
    s.append(CondPageBreak(40 * mm))
    s.append(Paragraph("Pontos críticos e premissas a validar", E["h2"]))
    for p in r["pontos_criticos"]:
        s.append(Paragraph(t(p["texto"]), estilo("item", leftIndent=10, bulletIndent=0, spaceAfter=3), bulletText="•"))
    if d.pendencias:
        s.append(Paragraph(t("Itens ainda não informados no levantamento: " + "; ".join(d.pendencias) + "."), E["apoio"]))

    # 7. recomendação
    s.append(CondPageBreak(45 * mm))
    s.append(Paragraph("Recomendação e próximos passos", E["h2"]))
    for i, linha in enumerate(d.recomendacao, start=1):
        s.append(Paragraph(t(linha), estilo("rec", leftIndent=14, bulletIndent=0, spaceAfter=4), bulletText=f"{i}."))

    # 8. anexos (numerados na ordem em que aparecem; os sem dados são omitidos)
    numero = iter(range(1, 20))

    def anexo(titulo: str) -> Paragraph:
        return Paragraph(t(f"Anexo {next(numero)}. {titulo}"), E["h2"])

    s.append(PageBreak())
    s.append(anexo("Tributos por regime"))
    for chave in ("simples", "presumido", "real"):
        reg = r[chave]
        linhas = [[tt["tributo"], brl(tt["valor"]), pct(tt["valor"] / receita)] for tt in reg["tributos"]
                  if tt["competencia"] is None and tt["valor"]]
        linhas.append(["Total", brl(reg["total"]), pct(reg["total"] / receita)])
        s.append(KeepTogether([Paragraph(REGIMES[reg["regime"]], E["h3"]),
                               tabela(["Tributo", "Valor", "% da receita"], linhas, [60 * mm, 40 * mm, 30 * mm], {1, 2}, True)]))
    det = r["real"]["detalhes"]
    s.append(KeepTogether([Paragraph("Lucro Real: apuração do lucro", E["h3"]), tabela(["Etapa", "Valor"], [
        ["Receita líquida", brl(receita)], ["(–) ICMS a recolher", brl(r["base"]["TOTAL"]["icms_a_recolher"])],
        ["(–) PIS/COFINS a recolher", brl(r["base"]["TOTAL"]["pis_cofins_lr_a_recolher"])], ["(–) Custo das mercadorias", brl(det["cmv"])],
        ["(–) Despesas dedutíveis", brl(det["despesas_dedutiveis"])], ["(–) Pessoal", brl(det["despesas_pessoal"])],
        ["Lucro antes de IRPJ e CSLL", brl(det["lair"])], ["Lucro real (base de IRPJ e CSLL)", brl(det["lucro_real"])]],
        [100 * mm, 40 * mm], {1}, True)]))

    s.append(CondPageBreak(60 * mm))
    s.append(anexo("Base da operação"))
    rotulos = [("receita_bruta", "Faturamento bruto"), ("devolucoes", "(–) Devoluções"), ("receita_liquida", "Receita líquida"),
               ("receita_monofasica", "Receita monofásica"), ("receita_interna", "Vendas internas"),
               ("receita_interestadual", "Vendas interestaduais"), ("remessas_sem_receita", "Remessas sem receita"),
               ("compras", "Compras"), ("despesas", "Despesas"), ("icms_debito", "ICMS débito"), ("icms_credito", "ICMS crédito"),
               ("icms_a_recolher", "ICMS a recolher")]
    cols = d.competencias + ["TOTAL"]
    larg = (L - 44 * mm) / len(cols)
    s.append(tabela(["Item"] + [mes(c) for c in d.competencias] + ["Período"],
                    [[rot] + [brl(r["base"][c][k]) for c in cols] for k, rot in rotulos],
                    [44 * mm] + [larg] * len(cols), numericas=set(range(1, len(cols) + 1))))

    ncms = r.get("verificacao_ncm") or []
    if ncms:
        s.append(CondPageBreak(70 * mm))
        s.append(anexo("Verificação por NCM"))
        for frase in resumo_ncm(ncms, receita):
            s.append(Paragraph(t(frase), estilo("ncm_resumo", leftIndent=10, bulletIndent=0, spaceAfter=2), bulletText="•"))
        s.append(Spacer(1, 3 * mm))
        conf = {"ALTA": "Alta", "MEDIA": "Média", None: "–"}
        dados = [[ncm_fmt(x["ncm"]), x["produto_exemplo"] or "–", brl(x["receita"]), pct(x["participacao"]),
                  "Monofásico" if x["monofasico"] else "Tributado", conf.get(x["confianca"], x["confianca"]),
                  acao_ncm(x)] for x in ncms]
        quadro = tabela(["NCM", "Produto de exemplo", "Receita", "% total", "PIS/COFINS", "Confiança", "Ação recomendada"], dados,
                        [18 * mm, 29 * mm, 22 * mm, 13 * mm, 19 * mm, 15 * mm, L - 116 * mm], numericas={2, 3})
        quadro.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), COR["aviso_fundo"])
                                    for i, x in enumerate(ncms) if x["requer_revisao"]]))
        s.append(quadro)
        s.append(Paragraph(t("Linhas destacadas: NCMs com ação pendente no cadastro. Monofásico: revenda com alíquota zero de "
                             "PIS/COFINS (Lei 10.485/2002); deixa de existir com a CBS em 2027."), E["apoio"]))

    if d.despesas:
        s.append(CondPageBreak(60 * mm))
        s.append(anexo("Despesas informadas"))
        for grupo, itens in d.despesas:
            subtotal = [sum(v[i] or 0 for _, v in itens) for i in range(len(d.competencias))]
            linhas = [[n] + ["–" if x is None else brl(x) for x in v] for n, v in itens]
            linhas.append(["Subtotal"] + [brl(x) for x in subtotal])
            larg = (L - 70 * mm) / len(d.competencias)
            s.append(KeepTogether([Paragraph(t(grupo), E["h3"]),
                                   tabela(["Item"] + [mes(c) for c in d.competencias], linhas, [70 * mm] + [larg] * len(d.competencias),
                                          set(range(1, len(d.competencias) + 1)), True)]))

    s.append(CondPageBreak(45 * mm))
    s.append(anexo("Bens próprios"))
    if d.bens:
        s.append(tabela(["Tipo", "Descrição", "Data de aquisição", "Valor"],
                        [[tipo, desc, dia.strftime("%d/%m/%Y"), brl(valor)] for tipo, desc, dia, valor in d.bens] +
                        [["Total", "", "", brl(sum(b[3] for b in d.bens))]],
                        [44 * mm, L - 104 * mm, 30 * mm, 30 * mm], {3}, True))
    else:
        s.append(Paragraph(t("A empresa declarou não possuir bens acima de R$ 1.200,00." if d.sem_bens
                             else "Nenhum bem informado no levantamento."), E["corpo"]))

    if d.documentos:
        s.append(CondPageBreak(60 * mm))
        s.append(anexo("Documentos"))
        pendentes = sum(x is None for _, sit in d.documentos for x in sit)
        total_docs = sum(len(sit) for _, sit in d.documentos)
        s.append(Paragraph(t(f"{pendentes} de {total_docs} documentos pendentes." if pendentes
                             else f"Todos os {total_docs} documentos foram enviados ou justificados."), E["apoio"]))
        s.append(Spacer(1, 2 * mm))
        larg = (L - 56 * mm) / len(d.competencias)
        quadro = tabela(["Documento"] + [mes(c) for c in d.competencias],
                        [[nome] + ["Pendente" if x is None else x for x in sit] for nome, sit in d.documentos],
                        [56 * mm] + [larg] * len(d.competencias))
        quadro.setStyle(TableStyle([("BACKGROUND", (j + 1, i + 1), (j + 1, i + 1), COR["aviso_fundo"])
                                    for i, (_, sit) in enumerate(d.documentos) for j, x in enumerate(sit) if x is None]))
        s.append(quadro)

    s.append(PageBreak())
    s.append(anexo("Memória de cálculo"))
    passos = r["memoria"]["passos"]
    s.append(tabela(["Seção", "Mês", "Etapa", "Fórmula", "Resultado", "Fundamento"],
                    [[p["secao"], mes(p["competencia"]) if p["competencia"] else "período", p["descricao"], p["formula"],
                      pct(p["valor"]) if abs(p["valor"]) < 1 and p["valor"] else brl(p["valor"]), p["fundamento"] or ""] for p in passos],
                    [17 * mm, 14 * mm, 34 * mm, 52 * mm, 25 * mm, L - 142 * mm], numericas={4}))

    if d.historico:
        s.append(CondPageBreak(40 * mm))
        s.append(anexo("Histórico do planejamento"))
        st = {"EM_COLETA": "Em coleta", "EM_CONFERENCIA": "Em conferência", "PRONTO_PARA_SIMULAR": "Pronto para simular",
              "SIMULADO": "Simulado", "APROVADO": "Aprovado"}
        s.append(tabela(["Data", "Usuário", "De", "Para", "Motivo"],
                        [[(dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(FUSO).strftime("%d/%m/%Y %H:%M"), u, st.get(de or "", "–"), st.get(para, para), m or ""]
                         for dt, u, de, para, m in d.historico],
                        [28 * mm, 38 * mm, 28 * mm, 28 * mm, L - 122 * mm]))

    s.append(CondPageBreak(40 * mm))
    s.append(Paragraph("Fontes legais", E["h2"]))
    for f in FONTES_LEGAIS:
        s.append(Paragraph(t(f), estilo("fonte", leftIndent=10, bulletIndent=0, fontSize=8.5, leading=12), bulletText="•"))
    s.append(Spacer(1, 4 * mm))
    s.append(Paragraph(t("Este relatório é uma simulação feita com os dados e premissas informados. A decisão de regime "
                         "deve ser confirmada pelo contador responsável."), E["apoio"]))

    doc.build(s, canvasmaker=lambda *a, **k: CanvasNumerado(*a, rodape=cabecalho_rodape, **k))
    return buf.getvalue()


# ------------------------------------------------------------- arquivamento


def gerar(db: Session, sim: Simulacao, usuario: Usuario, recomendacao: list[str] | None = None) -> RelatorioPdf:
    dados = coletar(db, sim, usuario, recomendacao)
    conteudo = montar_pdf(dados)
    pasta = Path(get_settings().upload_dir) / "relatorios"
    pasta.mkdir(parents=True, exist_ok=True)
    periodo = f"{dados.competencias[0].replace('-', '')}-{dados.competencias[-1].replace('-', '')}"
    nome = f"PLANEJAMENTO_{dados.cnpj}_{periodo}_{dados.gerado_em:%Y%m%d-%H%M%S}.pdf"
    (pasta / nome).write_bytes(conteudo)
    rel = RelatorioPdf(planejamento_id=sim.planejamento_id, simulacao_id=sim.id, arquivo=nome,
                       hash_sha256=hashlib.sha256(conteudo).hexdigest(), preliminar=dados.preliminar, gerado_por=usuario.id)
    db.add(rel)
    db.commit()
    return rel


def caminho(rel: RelatorioPdf) -> Path:
    return Path(get_settings().upload_dir) / "relatorios" / rel.arquivo
