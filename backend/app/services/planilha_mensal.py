"""Planilha padrão do movimento mensal (.xlsx): compras, devoluções, folha e pró-labore por competência.

O faturamento não entra: vem das notas de saída. Célula vazia não altera o valor já informado.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

COLUNAS = ["Competência", "Compras", "Devoluções", "Folha", "Pró-labore"]
CAMPOS = ["compras", "devolucoes", "folha", "pro_labore"]
FORMATO_MOEDA = '#,##0.00'


class PlanilhaInvalida(ValueError):
    pass


def gerar_modelo(competencias: list[str], atuais: dict[str, dict[str, Decimal | None]]) -> bytes:
    """Uma linha por competência do planejamento, já com o que estiver informado."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Movimento mensal"
    ws.append(COLUNAS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for comp in competencias:
        v = atuais.get(comp, {})
        ws.append([f"{comp[5:]}/{comp[:4]}", *(v.get(k) for k in CAMPOS)])
    for linha in ws.iter_rows(min_row=2, min_col=2):
        for c in linha:
            c.number_format = FORMATO_MOEDA
    for col, largura in zip("ABCDE", (14, 16, 16, 16, 16)):
        ws.column_dimensions[col].width = largura
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _competencia(v) -> str:
    if isinstance(v, (date, datetime)):
        return f"{v:%Y-%m}"
    t = str(v or "").strip()
    if m := re.fullmatch(r"(\d{1,2})/(\d{4})", t):
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    if re.fullmatch(r"\d{4}-\d{2}", t):
        return t
    raise PlanilhaInvalida(f"Competência \"{t}\" inválida: use MM/AAAA")


def _valor(v, onde: str) -> Decimal | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        d = Decimal(repr(v)) if isinstance(v, float) else Decimal(str(v).replace(".", "").replace(",", ".")) \
            if isinstance(v, str) and "," in v else Decimal(str(v))
    except InvalidOperation as e:
        raise PlanilhaInvalida(f"{onde}: valor \"{v}\" não é um número") from e
    if d < 0:
        raise PlanilhaInvalida(f"{onde}: valor negativo")
    return d.quantize(Decimal("0.01"))


def ler(conteudo: bytes) -> dict[str, dict[str, Decimal | None]]:
    """competência -> {campo: valor}; só as células preenchidas."""
    try:
        ws = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True).worksheets[0]
    except Exception as e:  # openpyxl levanta vários tipos para arquivo que não é .xlsx
        raise PlanilhaInvalida("Não foi possível ler a planilha: envie o modelo em .xlsx") from e
    linhas = [list(r) for r in ws.iter_rows(values_only=True)]
    if not linhas or [str(c or "").strip() for c in linhas[0][:5]] != COLUNAS:
        raise PlanilhaInvalida("A planilha não segue o modelo: baixe o modelo e mantenha as colunas " + ", ".join(COLUNAS))
    out: dict[str, dict[str, Decimal | None]] = {}
    for n, r in enumerate(linhas[1:], start=2):
        r = (r + [None] * 5)[:5]
        if all(c is None or str(c).strip() == "" for c in r):
            continue
        comp = _competencia(r[0])
        out[comp] = {k: v for k, c in zip(CAMPOS, r[1:]) if (v := _valor(c, f"Linha {n}, {COLUNAS[CAMPOS.index(k) + 1]}")) is not None}
    if not out:
        raise PlanilhaInvalida("A planilha não tem nenhuma competência preenchida")
    return out
