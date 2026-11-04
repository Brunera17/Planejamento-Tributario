"""Consulta, exportação e verificação da trilha de auditoria (só Contador)."""
import csv
import io
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, select

from app.api.deps import DB, Contador
from app.core.erros import ErroNegocio
from app.db import session as db_session
from app.models import EventoAuditoria
from app.services import auditoria

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])

EXPORTACAO_MAX_DIAS = 366
COLUNAS = ("id", "momento", "acao", "resultado", "usuario_id", "usuario_login", "sessao_id", "ip", "user_agent",
           "empresa_id", "empresa_cnpj", "planejamento_id", "recurso_tipo", "recurso_id", "detalhes", "hash")


def _inicio(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


def _filtrar(q: Select, desde: date | None, ate: date | None, usuario_id: int | None, empresa_id: int | None,
             acao: str | None, resultado: str | None, ip: str | None) -> Select:
    if desde:
        q = q.where(EventoAuditoria.momento >= _inicio(desde))
    if ate:
        q = q.where(EventoAuditoria.momento < _inicio(ate + timedelta(days=1)))
    if usuario_id is not None:
        q = q.where(EventoAuditoria.usuario_id == usuario_id)
    if empresa_id is not None:
        q = q.where(EventoAuditoria.empresa_id == empresa_id)
    if acao:
        q = q.where(EventoAuditoria.acao == acao)
    if resultado:
        q = q.where(EventoAuditoria.resultado == resultado)
    if ip:
        q = q.where(EventoAuditoria.ip == ip)
    return q


def _saida(ev: EventoAuditoria) -> dict:
    return {c: getattr(ev, c) for c in COLUNAS}


@router.get("")
def listar(db: DB, _: Contador, desde: date | None = None, ate: date | None = None, usuario_id: int | None = None,
           empresa_id: int | None = None, acao: str | None = None, resultado: str | None = None,
           ip: str | None = None, antes_de: int | None = Query(None, description="paginação: id do último item recebido"),
           limite: int = Query(100, ge=1, le=200)):
    """Mais recentes primeiro; paginação por cursor (antes_de) — não conta o total, que pesaria em 5 anos."""
    q = _filtrar(select(EventoAuditoria), desde, ate, usuario_id, empresa_id, acao, resultado, ip)
    if antes_de:
        q = q.where(EventoAuditoria.id < antes_de)
    linhas = db.scalars(q.order_by(EventoAuditoria.id.desc()).limit(limite + 1)).all()
    itens = [_saida(e) for e in linhas[:limite]]
    return {"itens": itens, "proximo": itens[-1]["id"] if len(linhas) > limite else None}


@router.get("/acoes")
def acoes(_: Contador):
    return sorted(auditoria.ACOES)


@router.get("/exportar")
def exportar(u: Contador, desde: date, ate: date, usuario_id: int | None = None, empresa_id: int | None = None,
             acao: str | None = None, resultado: str | None = None, ip: str | None = None):
    """CSV transmitido aos poucos, com período obrigatório de até um ano."""
    if ate < desde:
        raise ErroNegocio("A data final é anterior à inicial", 422, {"ate": "anterior a desde"})
    if (ate - desde).days >= EXPORTACAO_MAX_DIAS:
        raise ErroNegocio(f"Exporte no máximo {EXPORTACAO_MAX_DIAS} dias por vez", 422, {"ate": "período longo demais"})
    q = _filtrar(select(EventoAuditoria), desde, ate, usuario_id, empresa_id, acao, resultado, ip)
    auditoria.auditar("AUDITORIA_EXPORTADA", usuario=u, detalhes={
        "desde": desde, "ate": ate, "filtros": {"usuario_id": usuario_id, "empresa_id": empresa_id, "acao": acao,
                                                "resultado": resultado, "ip": ip}})

    def linhas() -> Iterator[str]:
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")

        def saida() -> str:
            v = buf.getvalue()
            buf.seek(0)
            buf.truncate()
            return v

        buf.write("﻿")
        w.writerow(COLUNAS)
        yield saida()
        # sessão própria: a da requisição já foi fechada quando o corpo começa a ser enviado
        with db_session.SessionLocal() as s:
            for ev in s.scalars(q.order_by(EventoAuditoria.id).execution_options(yield_per=500)):
                w.writerow([_saida(ev)[c] for c in COLUNAS])
                yield saida()

    nome = f"AUDITORIA_{desde.isoformat()}_{ate.isoformat()}.csv"
    return StreamingResponse(linhas(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.get("/verificar")
def verificar(db: DB, _: Contador):
    """Confere a corrente a partir do último checkpoint. A verificação completa é pelo comando de shell."""
    return auditoria.verificar(db).como_dict()
