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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Documento, Levantamento, Planejamento, TipoDocumento
from app.services import cripto, documentos
from app.services.memo import por_planejamento

NUMERO = r"\d{1,3}(?:\.\d{3})*,\d{2}"
# extrato: "PA: 06/2026"; declaração: "Período de Apuração: 01/08/2026 a 31/08/2026"
PA = re.compile(r"Per[ií]odo\s+de\s+Apura[çc][ãa]o(?:\s*\(PA\))?\s*:?\s*(?:\d{2}/)?(\d{2})/(\d{4})", re.I)
RBT12 = re.compile(r"\(RBT12\)((?:\s+" + NUMERO + r")+)", re.I)
ANEXO = re.compile(r"\bAnexo\s+(I{1,3}|IV|V)\b")
# atividades do PGDAS-D que já dizem o anexo
ATIVIDADES = [
    (re.compile(r"Revenda\s+de\s+mercadorias", re.I), "I"),
    (re.compile(r"mercadorias\s+industrializadas\s+pelo\s+contribuinte", re.I), "II"),
]
SERVICO = re.compile(r"Presta[çc][ãa]o\s+de\s+Servi[çc]os", re.I)
# quadro 2.2 da declaração: a receita de cada mês anterior ao PA (mercado interno e externo), até o quadro da folha
ANTERIORES = re.compile(r"Receitas\s+Brutas\s+Anteriores(.*?)(?:2\.3\)|Folha\s+de\s+Sal|2\.8\)|$)", re.I | re.S)
MES_VALOR = re.compile(r"(\d{2})/(\d{4})\s+(" + NUMERO + ")")
RPA = re.compile(r"Receita\s+Bruta\s+do\s+PA\s+\(RPA\)[^\d\n]*((?:\s+" + NUMERO + r")+)", re.I)


@dataclass
class ExtratoPgdas:
    arquivo: str
    competencia: str | None = None  # AAAA-MM do período de apuração
    rbt12: Decimal | None = None
    anexos: set[str] = field(default_factory=set)
    servicos: bool = False  # declarou serviço sem o anexo explícito (III, IV ou V)
    receitas: dict[str, Decimal] = field(default_factory=dict)  # AAAA-MM -> receita bruta declarada (meses anteriores e o PA)

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
    if m := ANTERIORES.search(texto):
        for mes, ano, valor in MES_VALOR.findall(m.group(1)):  # interno e externo somam no mesmo mês
            chave = f"{ano}-{mes}"
            e.receitas[chave] = e.receitas.get(chave, Decimal(0)) + _valor(valor)
    if e.competencia and (m := RPA.search(texto)):
        e.receitas[e.competencia] = _valor(re.findall(NUMERO, m.group(1))[-1])  # o total é o último da linha
    return e


def para_json(e: ExtratoPgdas) -> dict:
    """Forma gravada em Documento.pgdas_extrato (Decimal como texto, para não perder centavos)."""
    return {"lido": e.lido, "competencia": e.competencia, "rbt12": str(e.rbt12) if e.rbt12 is not None else None,
            "anexos": sorted(e.anexos), "servicos": e.servicos, "receitas": {k: str(v) for k, v in e.receitas.items()}}


def de_json(dados: dict, arquivo: str) -> ExtratoPgdas:
    return ExtratoPgdas(arquivo, competencia=dados.get("competencia"),
                        rbt12=Decimal(dados["rbt12"]) if dados.get("rbt12") else None,
                        anexos=set(dados.get("anexos") or []), servicos=bool(dados.get("servicos")),
                        receitas={k: Decimal(v) for k, v in (dados.get("receitas") or {}).items()})


# um só critério para "este tipo é o extrato do PGDAS-D", no envio, no cálculo e no preenchimento
# (upper: o LIKE do Postgres diferencia maiúsculas)
TIPO_PGDAS = func.upper(TipoDocumento.nome).like("%PGDAS%")


def eh_tipo_pgdas(db: Session, tipo_documento_id: int) -> bool:
    return db.scalar(select(TipoDocumento.id).where(TipoDocumento.id == tipo_documento_id, TIPO_PGDAS)) is not None


def leitura_no_envio(db: Session, tipo_documento_id: int, nome: str, conteudo: bytes) -> dict | None:
    """Chamada no upload, com os bytes já em memória: lê o extrato uma vez e devolve o que gravar no Documento."""
    if not nome.lower().endswith(".pdf") or not eh_tipo_pgdas(db, tipo_documento_id):
        return None
    return para_json(ler(conteudo, nome))


MARCA_CIFRADO = cripto.MARCA  # uma definição só, em cripto.py (uma versão nova do formato não passa despercebida)


def _ler_arquivo(arquivo: str, nome: str) -> ExtratoPgdas | None:
    """Documento enviado antes da leitura no upload: lê o arquivo, decifrando (sem gravar — o GET não escreve).
    None = não deu para tentar (arquivo sumido, ou cifrado e impossível de decifrar: chave ausente/errada,
    adulterado): fica NULL e é tentado de novo depois. Um PDF que abre mas não é extrato devolve "não lido"
    de verdade, e isso pode ser gravado."""
    if not documentos.existe(arquivo):
        return None
    try:
        conteudo = documentos.ler(arquivo)
    except cripto.ErroCripto:
        return None  # "ilegível" seria falso — e marcaria o documento como não lido para sempre
    return ler(conteudo, nome)


@por_planejamento
def do_planejamento(db: Session, p: Planejamento) -> ExtratoPgdas | None:
    """O extrato lido mais recente entre os enviados na aba Documentos (pelo período de apuração).
    Vem da leitura gravada no envio; o PDF só é aberto para documentos antigos ainda sem ela."""
    return _mais_recente(db, Levantamento.planejamento_id == p.id)


def da_empresa(db: Session, empresa_id: int) -> ExtratoPgdas | None:
    """O extrato lido mais recente entre todos os planejamentos da empresa."""
    return _mais_recente(db, Levantamento.planejamento_id.in_(
        select(Planejamento.id).where(Planejamento.empresa_id == empresa_id)))


def receitas_do_planejamento(db: Session, p: Planejamento) -> dict[str, Decimal]:
    """Receita mês a mês declarada nos PGDAS-D enviados; no mês que aparece em mais de um, vale o de PA mais recente."""
    out: dict[str, Decimal] = {}
    for e in sorted(_lidos(db, Levantamento.planejamento_id == p.id), key=lambda x: x.competencia or ""):
        out.update(e.receitas)
    return out


def _mais_recente(db: Session, condicao) -> ExtratoPgdas | None:
    return max(_lidos(db, condicao), key=lambda x: x.competencia or "", default=None)


def _lidos(db: Session, condicao) -> list[ExtratoPgdas]:
    linhas = db.execute(
        select(Documento.arquivo, Documento.arquivo_nome, Documento.pgdas_extrato, Levantamento.competencia)
        .join(Levantamento, Levantamento.id == Documento.levantamento_id)
        .join(TipoDocumento, TipoDocumento.id == Documento.tipo_documento_id)
        .where(condicao, TIPO_PGDAS, Documento.arquivo.is_not(None))
    ).all()
    lidos = []
    for arquivo, nome, gravado, competencia in linhas:
        if not arquivo.lower().endswith(".pdf"):
            continue
        # lido antes de o sistema guardar a receita mês a mês: lê o arquivo de novo
        atual = gravado is not None and ("receitas" in gravado or not gravado.get("lido"))
        e = de_json(gravado, nome or arquivo) if atual else _ler_arquivo(arquivo, nome or arquivo)
        if e is not None and e.lido:
            e.competencia = e.competencia or competencia
            lidos.append(e)
    return lidos


def preencher(db: Session) -> int:
    """Grava a leitura dos extratos enviados antes desta versão. Idempotente.
    Grava o resultado sempre que o arquivo pôde ser lido — inclusive "não lido" (PDF que não é extrato), como no
    envio, para não reabri-lo a cada cálculo. Arquivo sumido ou cifrado fica NULL e é tentado na próxima vez."""
    linhas = db.execute(
        select(Documento).join(TipoDocumento, TipoDocumento.id == Documento.tipo_documento_id)
        .where(TIPO_PGDAS, Documento.arquivo.is_not(None), Documento.pgdas_extrato.is_(None))
    ).scalars().all()
    n = 0
    for doc in linhas:
        if not doc.arquivo.lower().endswith(".pdf"):
            continue
        e = _ler_arquivo(doc.arquivo, doc.arquivo_nome or doc.arquivo)
        if e is not None:
            doc.pgdas_extrato = para_json(e)
            n += 1
    db.commit()
    return n


if __name__ == "__main__":
    import argparse

    from app.db.session import SessionLocal

    argparse.ArgumentParser(description="Grava a leitura dos extratos do PGDAS-D já enviados").parse_args()
    with SessionLocal() as sessao:
        print(f"{preencher(sessao)} extrato(s) lido(s) e gravado(s)")
