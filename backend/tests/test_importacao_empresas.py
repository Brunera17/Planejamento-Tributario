"""Importação de empresas por planilha nos formatos que o Excel grava."""
import io

import pytest
import xlwt
from openpyxl import Workbook

CAB = ["Empresa", "CNPJ", "Regime tributário", "Representante legal", "Telefone"]


def _xlsx(linhas):
    wb = Workbook()
    for l in linhas:
        wb.active.append(l)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _xls(linhas):
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Plan1")
    for i, l in enumerate(linhas):
        for j, v in enumerate(l):
            ws.write(i, j, v)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _csv(linhas, cod):
    return "\n".join(";".join(str(v) for v in l) for l in linhas).encode(cod)


@pytest.mark.parametrize("nome,conteudo", [
    ("cp1252.csv", _csv([CAB, ["Óptica Ação", "07.526.557/0001-00", "Simples Nacional", "João", "1133334444"]], "cp1252")),
    ("titulo.xlsx", _xlsx([["Clientes do escritório"], [], CAB, ["Óptica Ação", "07526557000100", "Lucro Presumido", "João", 1133334444]])),
    ("numerico.xls", _xls([CAB, ["Óptica Ação", 7526557000100.0, "Lucro Real", "João", 1133334444.0]])),
])
def test_formatos_do_excel(cliente, contador, nome, conteudo):
    arq = {"arquivo": (nome, conteudo)}
    previa = cliente.post("/api/empresas/importacao/previa", headers=contador, files=arq)
    assert previa.status_code == 200, previa.text
    [linha] = previa.json()
    assert linha["situacao"] != "ERRO", linha["erros"]
    assert linha["dados"]["cnpj"] == "07526557000100" and linha["dados"]["telefone"] == "1133334444"
    r = cliente.post("/api/empresas/importacao/confirmar", headers=contador, files=arq)
    assert r.json()["rejeitadas"] == 0 and r.json()["incluidas"] + r.json()["atualizadas"] == 1


def test_planilha_sem_cabecalho_explica_o_motivo(cliente, contador):
    r = cliente.post("/api/empresas/importacao/previa", headers=contador,
                     files={"arquivo": ("x.xlsx", _xlsx([["Nome", "Documento"], ["A", "1"]]))})
    assert r.status_code == 422 and "Empresa e CNPJ" in r.json()["erro"]
