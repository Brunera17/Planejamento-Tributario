"""Importação de empresas (.xlsx ou .csv): prévia linha a linha e gravação das linhas válidas."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Empresa, ImportacaoEmpresa
from app.utils.validacao import (
    UFS,
    cnpj_valido,
    normalizar_cnpj,
    normalizar_regime,
    sem_acentos,
    somente_digitos,
    telefone_valido,
)

COLUNAS = {
    "EMPRESA": "razao_social", "RAZAO SOCIAL": "razao_social", "CNPJ": "cnpj",
    "REGIME TRIBUTARIO": "regime", "REGIME": "regime", "REPRESENTANTE LEGAL": "representante_legal",
    "REPRESENTANTE": "representante_legal", "TELEFONE": "telefone", "UF": "uf", "CNAE": "cnae",
}


@dataclass
class LinhaPrevia:
    linha: int
    dados: dict
    situacao: str  # VALIDA, ERRO, EXISTENTE
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _ler_linhas(nome: str, conteudo: bytes) -> list[dict]:
    if nome.lower().endswith(".csv"):
        texto = conteudo.decode("utf-8-sig", errors="replace")
        dialeto = csv.Sniffer().sniff(texto.splitlines()[0], delimiters=";,")
        linhas = list(csv.reader(io.StringIO(texto), dialeto))
    else:
        ws = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True).active
        linhas = [["" if v is None else str(v) for v in r] for r in ws.iter_rows(values_only=True)]
    if not linhas:
        return []
    cab = [COLUNAS.get(sem_acentos(c).upper().strip()) for c in linhas[0]]
    return [{k: v.strip() for k, v in zip(cab, r) if k} for r in linhas[1:] if any(str(x).strip() for x in r)]


def previa(db: Session, nome: str, conteudo: bytes) -> list[LinhaPrevia]:
    out = []
    for i, d in enumerate(_ler_linhas(nome, conteudo), start=2):
        lp = LinhaPrevia(i, d, "VALIDA")
        cnpj = normalizar_cnpj(d.get("cnpj"))
        d["cnpj"] = cnpj
        if not d.get("razao_social"):
            lp.erros.append("Empresa (razão social) é obrigatória")
        if not cnpj_valido(cnpj):
            lp.erros.append("CNPJ inválido")
        regime = normalizar_regime(d.get("regime"))
        if not regime:
            lp.erros.append("Regime deve ser Simples Nacional, Lucro Presumido ou Lucro Real")
        d["regime"] = regime
        if d.get("uf") and d["uf"].upper() not in UFS:
            lp.erros.append("UF inválida")
        if not d.get("representante_legal"):
            lp.avisos.append("Representante legal não informado")
        if not telefone_valido(d.get("telefone")):
            lp.avisos.append("Telefone ausente ou sem DDD (10 ou 11 dígitos)")
            d["telefone"] = None
        else:
            d["telefone"] = somente_digitos(d["telefone"])
        if lp.erros:
            lp.situacao = "ERRO"
        elif db.scalar(select(Empresa.id).where(Empresa.cnpj == cnpj)):
            lp.situacao = "EXISTENTE"
        out.append(lp)
    return out


def confirmar(db: Session, nome: str, conteudo: bytes, usuario_id: int) -> ImportacaoEmpresa:
    linhas = previa(db, nome, conteudo)
    imp = ImportacaoEmpresa(arquivo=nome, importado_por=usuario_id, incluidas=0, atualizadas=0, rejeitadas=0)
    for lp in linhas:
        if lp.situacao == "ERRO":
            imp.rejeitadas += 1
            continue
        d = lp.dados
        emp = db.scalar(select(Empresa).where(Empresa.cnpj == d["cnpj"]))
        if emp is None:
            emp = Empresa(cnpj=d["cnpj"])
            db.add(emp)
            imp.incluidas += 1
        else:
            imp.atualizadas += 1
        emp.razao_social = d["razao_social"]
        emp.regime_tributario = d["regime"]
        emp.representante_legal = d.get("representante_legal") or None
        emp.telefone = d["telefone"]
        emp.uf = (d.get("uf") or emp.uf or "SP").upper()
        emp.cnae = d.get("cnae") or emp.cnae
        if emp.regime_tributario == "SIMPLES_NACIONAL" and not emp.anexo_simples:
            emp.anexo_simples = "I"
    db.add(imp)
    db.commit()
    return imp
