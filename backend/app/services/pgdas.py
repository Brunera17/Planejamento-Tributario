"""Leitura do extrato do PGDAS-D (PDF gerado pelo Portal do Simples Nacional): RBT12 e anexos declarados.

O extrato traz o período de apuração (PA), a receita bruta acumulada nos 12 meses anteriores (RBT12) e, por
estabelecimento, as atividades declaradas, que identificam o anexo. A leitura é por texto: se o layout mudar, o
extrato fica sem leitura e o RBT12 continua sendo informado à mão.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from decimal import Decimal

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Documento, Levantamento, Planejamento, TipoDocumento
from app.services import documentos

NUMERO = r"\d{1,3}(?:\.\d{3})*,\d{2}"
PA = re.compile(r"Per[ií]odo\s+de\s+Apura[çc][ãa]o(?:\s*\(PA\))?\s*:?\s*(\d{2})/(\d{4})", re.I)
RBT12 = re.compile(r"\(RBT12\)((?:\s+" + NUMERO + r")+)", re.I)
ANEXO = re.compile(r"\bAnexo\s+(I{1,3}|IV|V)\b")
# atividades do PGDAS-D que já dizem o anexo
ATIVIDADES = [
    (re.compile(r"Revenda\s+de\s+mercadorias", re.I), "I"),
    (re.compile(r"mercadorias\s+industrializadas\s+pelo\s+contribuinte", re.I), "II"),
]
SERVICO = re.compile(r"Presta[çc][ãa]o\s+de\s+Servi[çc]os", re.I)


@dataclass
class ExtratoPgdas:
    arquivo: str
    competencia: str | None = None  # AAAA-MM do período de apuração
    rbt12: Decimal | None = None
    anexos: set[str] = field(default_factory=set)
    servicos: bool = False  # declarou serviço sem o anexo explícito (III, IV ou V)

    @property
    def lido(self) -> bool:
        return self.rbt12 is not None


def _valor(texto: str) -> Decimal:
    return Decimal(texto.replace(".", "").replace(",", "."))


def ler(conteudo: bytes, arquivo: str = "") -> ExtratoPgdas:
    try:
        texto = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(conteudo)).pages)
    except Exception:  # PDF protegido ou corrompido: fica sem leitura
        return ExtratoPgdas(arquivo)
    texto = re.sub(r"[ \t]+", " ", texto)
    e = ExtratoPgdas(arquivo)
    if m := PA.search(texto):
        e.competencia = f"{m.group(2)}-{m.group(1)}"
    if m := RBT12.search(texto):
        # mercado interno, externo e total: o total é o último da linha
        e.rbt12 = _valor(re.findall(NUMERO, m.group(1))[-1])
    e.anexos = set(ANEXO.findall(texto))
    for padrao, anexo in ATIVIDADES:
        if padrao.search(texto):
            e.anexos.add(anexo)
    e.servicos = bool(SERVICO.search(texto)) and not e.anexos & {"III", "IV", "V"}
    return e


def do_planejamento(db: Session, p: Planejamento) -> ExtratoPgdas | None:
    """O extrato lido mais recente entre os enviados na aba Documentos (pelo período de apuração)."""
    linhas = db.execute(
        select(Documento.arquivo, Documento.arquivo_nome, Levantamento.competencia)
        .join(Levantamento, Levantamento.id == Documento.levantamento_id)
        .join(TipoDocumento, TipoDocumento.id == Documento.tipo_documento_id)
        .where(Levantamento.planejamento_id == p.id, TipoDocumento.nome.like("%PGDAS%"), Documento.arquivo.is_not(None))
    ).all()
    lidos = []
    for arquivo, nome, competencia in linhas:
        if not arquivo.lower().endswith(".pdf"):
            continue
        caminho = documentos.caminho(arquivo)
        if not caminho.exists():
            continue
        e = ler(caminho.read_bytes(), nome or arquivo)
        if e.lido:
            e.competencia = e.competencia or competencia
            lidos.append(e)
    return max(lidos, key=lambda x: x.competencia or "", default=None)
