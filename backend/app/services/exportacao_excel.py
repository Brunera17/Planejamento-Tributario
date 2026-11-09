"""Exportação da simulação para .xlsx, no layout das abas da planilha de planejamento."""
from __future__ import annotations

import io
import json

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from sqlalchemy.orm import Session

from app.models import Empresa, Planejamento, Simulacao
from app.services import memoria_calculo

NOMES = {"SIMPLES_NACIONAL": "Simples Nacional", "LUCRO_PRESUMIDO": "Lucro Presumido", "LUCRO_REAL": "Lucro Real"}
MOEDA = '#,##0.00'
PCT = '0.00%'
CAB = PatternFill("solid", fgColor="E4E9EF")
TITULO = Font(bold=True, size=13, color="155E75")


def _cabecalho(ws, titulo: str, emp: Empresa, p: Planejamento, linha_colunas: list[str]) -> int:
    ws["A1"] = "PLANEJADOR TRIBUTÁRIO"
    ws["A1"].font = Font(bold=True, color="155E75")
    ws["A2"] = titulo
    ws["A2"].font = TITULO
    ws["A3"] = f"{emp.razao_social}  •  CNPJ {emp.cnpj}  •  Período {p.competencia_inicial} a {p.competencia_final}"
    for i, c in enumerate(linha_colunas, start=1):
        cel = ws.cell(row=5, column=i, value=c)
        cel.font = Font(bold=True)
        cel.fill = CAB
        cel.alignment = Alignment(wrap_text=True, vertical="center")
    return 6


def _larguras(ws, larguras: list[int]) -> None:
    for i, w in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def gerar(sim: Simulacao, p: Planejamento) -> bytes:
    r = json.loads(sim.resultado_json)
    emp = p.empresa
    wb = Workbook()
    comps = [c for c in r["base"] if c != "TOTAL"]
    # receita líquida do período: linha 8, última coluna da aba Base da Operação
    receita = f"'Base da Operação'!${get_column_letter(len(comps) + 2)}$8"

    # Comparativo 3 Regimes
    ws = wb.active
    ws.title = "Comparativo 3 Regimes"
    lin = _cabecalho(ws, "COMPARATIVO DOS 3 REGIMES", emp, p,
                     ["Regime", "Tributos estaduais (ICMS)", "Tributos federais", "Carga total", "Alíquota efetiva",
                      "Diferença vs. melhor", "Posição"])
    inicio = lin
    for c in sorted(r["comparativo"], key=lambda x: x["posicao"]):
        ws.append([NOMES[c["regime"]], c["estadual"], c["federal"], None, None, None, f'{c["posicao"]}º'])
        ws.cell(row=lin, column=4, value=f"=B{lin}+C{lin}")
        ws.cell(row=lin, column=5, value=f"=D{lin}/{receita}")
        ws.cell(row=lin, column=6, value=f"=D{lin}-MIN($D${inicio}:$D${inicio + 2})")
        lin += 1
    ws.cell(row=lin + 1, column=1, value="REGIME MAIS VANTAJOSO").font = Font(bold=True)
    ws.cell(row=lin + 1, column=2, value=NOMES[r["melhor_regime"]]).font = Font(bold=True, color="155E75")
    if sim.tipo != "FINAL" or sim.desatualizada:
        ws.cell(row=lin + 3, column=1, value="PRELIMINAR – " + (sim.pendencias or "simulação desatualizada"))
    _formatar(ws, inicio, lin - 1, {2: MOEDA, 3: MOEDA, 4: MOEDA, 5: PCT, 6: MOEDA})
    _larguras(ws, [22, 18, 18, 16, 14, 18, 10])

    # Base da operação
    wb_base = wb.create_sheet("Base da Operação")
    lin = _cabecalho(wb_base, "BASE DA OPERAÇÃO", emp, p, ["Item", *comps, "Período"])
    rotulos = [("receita_bruta", "Faturamento bruto"), ("devolucoes", "(−) Devoluções"),
               ("receita_liquida", "(=) Receita líquida"), ("receita_monofasica", "Receita monofásica"),
               ("receita_nao_monofasica", "Receita não monofásica"), ("receita_interna", "Vendas internas"),
               ("receita_interestadual", "Vendas interestaduais"), ("remessas_sem_receita", "Remessas sem receita"),
               ("compras", "Compras de mercadorias"), ("despesas", "Despesas operacionais"),
               ("icms_debito", "ICMS débito (regime normal)"), ("icms_credito", "ICMS crédito"),
               ("icms_difal", "DIFAL e FCP (estados de destino)"), ("icms_a_recolher", "ICMS a recolher"), ("pis_cofins_lr_debito", "PIS/COFINS LR – débitos"),
               ("pis_cofins_lr_credito", "PIS/COFINS LR – créditos"),
               ("pis_cofins_lr_a_recolher", "PIS/COFINS LR – a recolher")]
    for chave, rot in rotulos:
        valores = [r["base"][c].get(chave, 0) for c in comps]  # simulações antigas não têm o DIFAL
        wb_base.append([rot, *valores])
        col_total = get_column_letter(len(comps) + 2)
        wb_base[f"{col_total}{lin}"] = f"=SUM(B{lin}:{get_column_letter(len(comps) + 1)}{lin})"
        lin += 1
    _formatar(wb_base, 6, lin - 1, {i: MOEDA for i in range(2, len(comps) + 3)})
    _larguras(wb_base, [32] + [16] * (len(comps) + 1))

    # Tributos por regime
    for chave, titulo in (("simples", "Simples Nacional"), ("presumido", "Lucro Presumido"), ("real", "Lucro Real")):
        reg = r[chave]
        ws = wb.create_sheet(titulo)
        lin = _cabecalho(ws, f"{titulo.upper()} – TRIBUTOS DO PERÍODO", emp, p, ["Tributo", "Valor", "% receita"])
        ini = lin
        for t in reg["tributos"]:
            if t["competencia"] is None:
                ws.append([t["tributo"], t["valor"]])
                ws.cell(row=lin, column=3, value=f"=B{lin}/{receita}")
                lin += 1
        ws.append(["TOTAL", f"=SUM(B{ini}:B{lin - 1})"])
        ws.cell(row=lin, column=3, value=f"=B{lin}/{receita}")
        ws.cell(row=lin, column=1).font = Font(bold=True)
        lin += 2
        for k, v in reg["detalhes"].items():
            ws.cell(row=lin, column=1, value=k.replace("_", " "))
            ws.cell(row=lin, column=2, value=v)
            lin += 1
        _formatar(ws, ini, ini + len(reg["tributos"]), {2: MOEDA, 3: PCT})
        _larguras(ws, [34, 18, 12])

    # Reforma
    ws = wb.create_sheet("Reforma 2026-2033")
    lin = _cabecalho(ws, "EVOLUÇÃO DA REFORMA TRIBUTÁRIA – MESMA BASE DO PERÍODO", emp, p,
                     ["Ano", "CBS", "IBS", "ICMS mantido", "Simples Nacional", "Lucro Presumido", "Lucro Real", "Melhor"])
    for a in r["reforma"]:
        ws.append([a["ano"], a["cbs"], a["ibs"], a["fator_icms"], a["cargas"]["SIMPLES_NACIONAL"],
                   a["cargas"]["LUCRO_PRESUMIDO"], a["cargas"]["LUCRO_REAL"], NOMES[a["melhor"]]])
    _formatar(ws, 6, 6 + len(r["reforma"]), {2: PCT, 3: PCT, 4: '0%', 5: MOEDA, 6: MOEDA, 7: MOEDA})
    _larguras(ws, [8, 9, 9, 12, 18, 18, 18, 18])

    # Oportunidades
    ws = wb.create_sheet("Oportunidades")
    _cabecalho(ws, "OPORTUNIDADES DE ECONOMIA TRIBUTÁRIA", emp, p, ["Oportunidade", "Impacto (período)", "Prioridade", "Ação"])
    for o in r["oportunidades"]:
        ws.append([o["titulo"], o["impacto"] if o["impacto"] is not None else "Qualitativo", o["prioridade"], o["acao"]])
    _formatar(ws, 6, 6 + len(r["oportunidades"]), {2: MOEDA})
    _larguras(ws, [48, 18, 11, 100])

    # Memória de cálculo
    ws = wb.create_sheet("Memória de Cálculo")
    _cabecalho(ws, "MEMÓRIA DE CÁLCULO", emp, p, ["Seção", "Competência", "Etapa", "Fórmula", "Resultado", "Fundamento"])
    for m in memoria_calculo.passos(Session.object_session(sim), sim):
        ws.append([m["secao"], m["competencia"], m["descricao"], m["formula"], m["valor"], m["fundamento"]])
    _larguras(ws, [16, 12, 44, 70, 18, 36])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _formatar(ws, de: int, ate: int, formatos: dict[int, str]) -> None:
    for linha in ws.iter_rows(min_row=de, max_row=ate):
        for cel in linha:
            fmt = formatos.get(cel.column)
            if fmt:
                cel.number_format = fmt
