"""Bens próprios e documentos do planejamento.

Nenhum dos dois entra no cálculo: alterar atualiza o progresso, mas não desatualiza as simulações.
"""
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DB, UsuarioAtual, obter_planejamento
from app.core.config import get_settings
from app.core.erros import ErroNegocio, NaoEncontrado
from app.models import Bem, Documento, Levantamento, Planejamento, TipoDocumento
from app.schemas.comum import Esquema
from app.services import documentos, progresso
from app.utils.upload import ler_limitado

router = APIRouter(prefix="/planejamentos", tags=["Bens e documentos"])

MES_FECHADO = "Este mês já foi enviado para conferência; devolva o levantamento para alterar os documentos"


class BemEntrada(Esquema):
    tipo: Literal["VEICULOS", "MOVEIS_UTENSILIOS", "MAQUINAS_EQUIPAMENTOS", "IMOVEL"]
    descricao: str = Field(min_length=2, max_length=200)
    data_aquisicao: date
    valor: Decimal = Field(gt=1200, max_digits=14, decimal_places=2)

    @field_validator("data_aquisicao")
    @classmethod
    def _data(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("A data de aquisição não pode ser futura")
        return v


class BemSaida(Esquema):
    id: int
    tipo: str
    descricao: str
    data_aquisicao: date
    valor: Decimal


class NaoSeAplica(Esquema):
    justificativa: str = Field(min_length=5, max_length=500)


def _progresso(db: Session, p: Planejamento) -> None:
    db.flush()
    progresso.atualizar(db, p)
    db.commit()


def _bem(db: Session, p: Planejamento, bem_id: int) -> Bem:
    b = db.get(Bem, bem_id)
    if b is None or b.empresa_id != p.empresa_id:
        raise NaoEncontrado("Bem")
    return b


@router.get("/{pid}/bens")
def listar_bens(pid: int, db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid)
    bens = db.scalars(select(Bem).where(Bem.empresa_id == p.empresa_id).order_by(Bem.data_aquisicao.desc())).all()
    return {"sem_bens": p.sem_bens, "bens": [BemSaida.model_validate(b) for b in bens]}


@router.post("/{pid}/bens", response_model=BemSaida, status_code=201)
def criar_bem(pid: int, dados: BemEntrada, db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid)
    b = Bem(empresa_id=p.empresa_id, **dados.model_dump())
    db.add(b)
    p.sem_bens = False
    _progresso(db, p)
    return b


@router.put("/{pid}/bens/{bem_id}", response_model=BemSaida)
def editar_bem(pid: int, bem_id: int, dados: BemEntrada, db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid)
    b = _bem(db, p, bem_id)
    for k, v in dados.model_dump().items():
        setattr(b, k, v)
    _progresso(db, p)
    return b


@router.delete("/{pid}/bens/{bem_id}", status_code=204)
def excluir_bem(pid: int, bem_id: int, db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid)
    db.delete(_bem(db, p, bem_id))
    _progresso(db, p)


@router.put("/{pid}/sem-bens", status_code=204)
def declarar_sem_bens(pid: int, sem_bens: bool, db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid)
    if sem_bens and db.scalar(select(Bem.id).where(Bem.empresa_id == p.empresa_id).limit(1)):
        raise ErroNegocio("Exclua os bens cadastrados antes de declarar que a empresa não possui bens", 409)
    p.sem_bens = sem_bens
    _progresso(db, p)


# ------------------------------------------------------------------ documentos


def _levantamento(db: Session, p: Planejamento, competencia: str, usuario_id: int) -> Levantamento:
    if competencia not in p.competencias():
        raise ErroNegocio(f"Competência {competencia} fora do período do planejamento", campos={"competencia": "fora do período"})
    lv = db.scalar(select(Levantamento).where(Levantamento.planejamento_id == p.id, Levantamento.competencia == competencia))
    if lv is None:
        lv = Levantamento(planejamento_id=p.id, competencia=competencia, criado_por=usuario_id)
        db.add(lv)
        db.flush()
    elif lv.status != "EM_PREENCHIMENTO":
        raise ErroNegocio(MES_FECHADO, 409)
    return lv


def _documento(db: Session, lv: Levantamento, tipo_id: int) -> Documento:
    if db.get(TipoDocumento, tipo_id) is None:
        raise NaoEncontrado("Tipo de documento")
    doc = db.scalar(select(Documento).where(Documento.levantamento_id == lv.id, Documento.tipo_documento_id == tipo_id))
    if doc is None:
        doc = Documento(levantamento_id=lv.id, tipo_documento_id=tipo_id)
        db.add(doc)
    return doc


def _doc_do_planejamento(db: Session, pid: int, doc_id: int) -> tuple[Documento, Levantamento]:
    doc = db.get(Documento, doc_id)
    lv = db.get(Levantamento, doc.levantamento_id) if doc else None
    if lv is None or lv.planejamento_id != pid:
        raise NaoEncontrado("Documento")
    return doc, lv


@router.get("/{pid}/documentos")
def listar_documentos(pid: int, db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid)
    levs = {lv.id: lv for lv in db.scalars(select(Levantamento).where(Levantamento.planejamento_id == pid))}
    docs = db.scalars(select(Documento).where(Documento.levantamento_id.in_(levs))).all() if levs else []
    fechados = {lv.competencia for lv in levs.values() if lv.status != "EM_PREENCHIMENTO"}
    return {
        "competencias": [{"competencia": c, "editavel": c not in fechados} for c in p.competencias()],
        "tipos": [{"id": t.id, "nome": t.nome} for t in db.scalars(select(TipoDocumento).order_by(TipoDocumento.ordem))],
        "documentos": [{"id": d.id, "competencia": levs[d.levantamento_id].competencia, "tipo_documento_id": d.tipo_documento_id,
                        "arquivo": d.arquivo_nome or d.arquivo, "nao_se_aplica": d.nao_se_aplica, "justificativa": d.justificativa,
                        "enviado_em": d.enviado_em} for d in docs],
    }


@router.post("/{pid}/documentos/{competencia}/{tipo_id}", status_code=201)
def enviar_documento(pid: int, competencia: str, tipo_id: int, arquivo: UploadFile, db: DB, u: UsuarioAtual):
    p = obter_planejamento(db, pid)
    nome = (arquivo.filename or "documento").replace("\\", "/").rsplit("/", 1)[-1][:200]
    conteudo = ler_limitado(arquivo, get_settings().upload_max_mb)
    ext = documentos.validar(nome, conteudo)
    doc = _documento(db, _levantamento(db, p, competencia, u.id), tipo_id)
    anterior = doc.arquivo
    doc.arquivo, doc.arquivo_nome = documentos.gravar(conteudo, ext), nome
    doc.nao_se_aplica, doc.justificativa, doc.enviado_em = False, None, datetime.now(UTC)
    _progresso(db, p)
    documentos.apagar(anterior)
    return {"id": doc.id, "arquivo": nome}


@router.put("/{pid}/documentos/{competencia}/{tipo_id}/nao-se-aplica", status_code=204)
def marcar_nao_se_aplica(pid: int, competencia: str, tipo_id: int, dados: NaoSeAplica, db: DB, u: UsuarioAtual):
    p = obter_planejamento(db, pid)
    doc = _documento(db, _levantamento(db, p, competencia, u.id), tipo_id)
    anterior = doc.arquivo
    doc.arquivo, doc.arquivo_nome = None, None
    doc.nao_se_aplica, doc.justificativa, doc.enviado_em = True, dados.justificativa.strip(), datetime.now(UTC)
    _progresso(db, p)
    documentos.apagar(anterior)


@router.delete("/{pid}/documentos/{doc_id}", status_code=204)
def excluir_documento(pid: int, doc_id: int, db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid)
    doc, lv = _doc_do_planejamento(db, pid, doc_id)
    if lv.status != "EM_PREENCHIMENTO":
        raise ErroNegocio(MES_FECHADO, 409)
    arquivo = doc.arquivo
    db.delete(doc)
    _progresso(db, p)
    documentos.apagar(arquivo)


@router.get("/{pid}/documentos/{doc_id}/download")
def baixar_documento(pid: int, doc_id: int, db: DB, _: UsuarioAtual):
    doc, _lv = _doc_do_planejamento(db, pid, doc_id)
    if not doc.arquivo or not documentos.caminho(doc.arquivo).exists():
        raise ErroNegocio("O arquivo deste documento não está no armazenamento; envie-o novamente", 410)
    return FileResponse(documentos.caminho(doc.arquivo), filename=doc.arquivo_nome or doc.arquivo,
                        media_type="application/octet-stream")
