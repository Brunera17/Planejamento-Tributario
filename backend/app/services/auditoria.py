"""Trilha de auditoria: registro, encadeamento por hash, verificação e expurgo por retenção.

Uso nas rotas: `auditar(...)` **depois** do commit da operação. Dentro de uma requisição o evento vai para a fila
do contexto e é gravado pelo middleware (ver app/core/contexto.py); fora dela (comandos, testes) grava na hora.

Linha de comando:
    python -m app.services.auditoria --verificar-tudo
    python -m app.services.auditoria --expurgar
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core import redis as redis_cliente
from app.core.config import get_settings
from app.core.contexto import contexto_atual
from app.db import session as db_session
from app.models import AuditoriaCheckpoint, EventoAuditoria

GENESE = "0" * 64
CHAVE_LOCK = 734_201  # pg_advisory_xact_lock: serializa a corrente entre processos
_trava_local = threading.Lock()  # e entre threads do mesmo processo (SQLite não tem advisory lock)

ACOES = frozenset({
    # acesso
    "LOGIN_OK", "LOGIN_FALHA", "LOGIN_BLOQUEADO", "MFA_OK", "MFA_FALHA", "MFA_ATIVADO", "MFA_RESETADO",
    "RECUPERACAO_USADA", "LOGOUT", "LOGOUT_TODOS", "REFRESH_REUSO", "SESSAO_EXPIRADA",
    # usuários
    "USUARIO_CRIADO", "USUARIO_EDITADO", "SENHA_ALTERADA", "PERFIL_ALTERADO", "USUARIO_DESATIVADO",
    "USUARIO_REATIVADO", "CARTEIRA_ALTERADA",
    # documentos e importações
    "DOCUMENTO_ENVIADO", "DOCUMENTO_BAIXADO", "DOCUMENTO_EXCLUIDO", "NFE_IMPORTADA", "DESPESAS_SIMULADAS", "RELATORIO_CONTABIL_IMPORTADO", "PLANILHA_MENSAL_IMPORTADA",
    # saídas
    "RELATORIO_GERADO", "RELATORIO_BAIXADO", "EXCEL_EXPORTADO", "APRESENTACAO_EXPORTADA", "REVISAO_EXPORTADA",
    # leitura
    "PLANEJAMENTO_ABERTO",
    # empresas
    "EMPRESA_CRIADA", "EMPRESA_EDITADA", "EMPRESA_REATIVADA", "EMPRESA_EXCLUIDA", "EMPRESAS_IMPORTADAS",
    # negações e a própria auditoria
    "ACESSO_NEGADO", "AUDITORIA_EXPORTADA", "AUDITORIA_EXPURGO",
})
# leitura/download: sem registro, o conteúdo não sai (503). As demais são alterações já commitadas.
LEITURA = frozenset({"DOCUMENTO_BAIXADO", "RELATORIO_BAIXADO", "EXCEL_EXPORTADO", "APRESENTACAO_EXPORTADA",
                     "REVISAO_EXPORTADA", "PLANEJAMENTO_ABERTO", "AUDITORIA_EXPORTADA"})
RESULTADOS = frozenset({"OK", "FALHA", "NEGADO"})
CAMPOS_HASH = ("acao", "resultado", "usuario_id", "usuario_login", "sessao_id", "ip", "user_agent", "empresa_id",
               "empresa_cnpj", "planejamento_id", "recurso_tipo", "recurso_id", "detalhes")


# ------------------------------------------------------------------ registro

def auditar(acao: str, *, resultado: str = "OK", usuario: Any = None, usuario_login: str | None = None,
            planejamento: Any = None, empresa: Any = None, recurso_tipo: str | None = None,
            recurso_id: int | None = None, detalhes: dict | None = None) -> None:
    """Registra um evento. `usuario`, `planejamento` e `empresa` são modelos (lidos aqui, já como valores)."""
    if acao not in ACOES:
        raise ValueError(f"Ação de auditoria desconhecida: {acao}")
    if resultado not in RESULTADOS:
        raise ValueError(f"Resultado de auditoria inválido: {resultado}")
    if empresa is None and planejamento is not None:
        empresa = planejamento.empresa
    ctx = contexto_atual.get()
    evento = {
        "acao": acao,
        "resultado": resultado,
        "usuario_id": getattr(usuario, "id", None),
        "usuario_login": (getattr(usuario, "usuario", None) or usuario_login or None),
        "sessao_id": ctx.sessao_id if ctx else None,
        "ip": ctx.ip if ctx else None,
        "user_agent": ctx.user_agent if ctx else None,
        "empresa_id": getattr(empresa, "id", None),
        "empresa_cnpj": getattr(empresa, "cnpj", None),
        "planejamento_id": getattr(planejamento, "id", None),
        "recurso_tipo": recurso_tipo,
        "recurso_id": recurso_id,
        # normaliza já: o que vai para o banco é exatamente o que entra no hash
        "detalhes": json.loads(json.dumps(detalhes, default=str, ensure_ascii=False)) if detalhes else None,
    }
    if evento["usuario_login"]:
        evento["usuario_login"] = evento["usuario_login"][:60]
    if ctx is not None:
        ctx.pendentes.append(evento)
    else:
        gravar([evento])


def auditar_uma_vez(chave: str, acao: str, **kwargs) -> None:
    """Grava só na primeira vez por sessão (ex.: PLANEJAMENTO_ABERTO). Sem Redis, grava assim mesmo:
    melhor um evento repetido do que um acesso sem registro."""
    ctx = contexto_atual.get()
    if ctx is not None and ctx.sessao_id:
        ttl = get_settings().auditoria_dedup_horas * 3600
        try:
            if not redis_cliente.executar(lambda r: r.set(f"aud_uma_vez:{ctx.sessao_id}:{chave}", 1, nx=True, ex=ttl)):
                return
        except redis_cliente.RedisIndisponivel:
            pass
    auditar(acao, **kwargs)


def _momento_txt(m: datetime) -> str:
    """Forma única do instante para o hash: UTC, sem fuso, microssegundos (SQLite devolve sem fuso)."""
    if m.tzinfo is not None:
        m = m.astimezone(UTC).replace(tzinfo=None)
    return m.isoformat(timespec="microseconds")


def calcular_hash(hash_anterior: str, momento: datetime, campos: dict) -> str:
    corpo = {k: campos.get(k) for k in CAMPOS_HASH}
    corpo["momento"] = _momento_txt(momento)
    texto = hash_anterior + json.dumps(corpo, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(texto.encode()).hexdigest()


def _travar(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": CHAVE_LOCK})


def _ultimo_hash(db: Session) -> str:
    return db.scalar(select(EventoAuditoria.hash).order_by(EventoAuditoria.id.desc()).limit(1)) or GENESE


def _inserir(db: Session, eventos: list[dict]) -> None:
    """Dentro do lock: encadeia e insere. Nada de lógica além disso aqui (o lock segura toda a corrente)."""
    anterior = _ultimo_hash(db)
    for ev in eventos:
        momento = datetime.now(UTC)
        h = calcular_hash(anterior, momento, ev)
        db.add(EventoAuditoria(momento=momento, hash_anterior=anterior, hash=h, **ev))
        anterior = h


def gravar(eventos: list[dict]) -> None:
    """Grava numa sessão própria, com commit imediato e transação curta.
    Leva junto o que estiver na contingência deste processo (e de processos que sumiram)."""
    with _trava_local:
        recuperados = _tomar_contingencia()
        todos = recuperados + list(eventos)
        if not todos:
            return
        try:
            with db_session.SessionLocal() as db:
                _travar(db)
                _inserir(db, todos)
                db.commit()
        except Exception:
            if recuperados:
                _anexar(_arquivo_proprio(), recuperados)  # devolve o que tinha tomado
            raise


# ------------------------------------------------------------------ contingência
# Um arquivo por processo: cada processo só acrescenta no seu, então dois workers nunca escrevem no mesmo.
# Arquivos de outros processos só são tomados quando parados há mais de CONTINGENCIA_ORFA_S (processo morto
# ou reiniciado), renomeados antes de lidos — se o rename falhar, outro processo já tomou.

CONTINGENCIA_ORFA_S = 300
log = logging.getLogger("planejador.auditoria")


def _pasta_contingencia() -> Path:
    p = Path(get_settings().upload_dir) / "auditoria"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _arquivo_proprio() -> Path:
    return _pasta_contingencia() / f"pendentes.{os.getpid()}.jsonl"


def _anexar(arquivo: Path, eventos: list[dict]) -> None:
    with arquivo.open("a", encoding="utf-8") as f:
        for ev in eventos:
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")


def guardar_contingencia(eventos: list[dict]) -> None:
    """Alteração já commitada cuja auditoria não gravou: guarda para o próximo `gravar` (com o horário real)."""
    agora = datetime.now(UTC).isoformat()
    marcados = [{**ev, "detalhes": {**(ev.get("detalhes") or {}), "_ocorrido_em": agora}} for ev in eventos]
    try:
        with _trava_local:
            _anexar(_arquivo_proprio(), marcados)
    except Exception:  # noqa: BLE001 – último recurso: o log
        log.critical("Auditoria perdida (contingência indisponível): %s", json.dumps(marcados, default=str))


def _tomar_contingencia() -> list[dict]:
    """Chamado com _trava_local. Renomeia e lê os arquivos que este processo pode tomar."""
    pasta = _pasta_contingencia()
    proprio = _arquivo_proprio().name
    agora = time.time()
    eventos: list[dict] = []
    for arq in sorted(pasta.glob("pendentes.*.jsonl")):
        try:
            if arq.name != proprio and agora - arq.stat().st_mtime < CONTINGENCIA_ORFA_S:
                continue  # de outro processo ativo: ele mesmo reprocessa
            tomado = arq.with_name(f"processando.{os.getpid()}.{uuid.uuid4().hex}.jsonl")
            os.replace(arq, tomado)
        except OSError:
            continue  # outro processo tomou antes
        with tomado.open(encoding="utf-8") as f:
            eventos += [json.loads(linha) for linha in f if linha.strip()]
        tomado.unlink()
    return eventos


def pendentes_na_contingencia() -> int:
    total = 0
    for arq in _pasta_contingencia().glob("*.jsonl"):
        try:
            with arq.open(encoding="utf-8") as f:
                total += sum(1 for linha in f if linha.strip())
        except OSError:
            pass
    return total


# ------------------------------------------------------------------ verificação

@dataclass
class Verificacao:
    ok: bool
    verificados: int
    ate_evento: int | None
    problema_evento: int | None = None
    problema: str | None = None

    def como_dict(self) -> dict:
        return {"ok": self.ok, "verificados": self.verificados, "ate_evento": self.ate_evento,
                "problema_evento": self.problema_evento, "problema": self.problema}


def _ancora(db: Session) -> str:
    """Início da corrente: o gênese, ou o hash_anterior guardado pelo último expurgo."""
    detalhes = db.scalar(select(EventoAuditoria.detalhes).where(EventoAuditoria.acao == "AUDITORIA_EXPURGO")
                         .order_by(EventoAuditoria.id.desc()).limit(1))
    return (detalhes or {}).get("ancora") or GENESE


def verificar(db: Session, completo: bool = False, lote: int = 1000) -> Verificacao:
    """Confere a corrente. Incremental (padrão) parte do último checkpoint; completo parte do início."""
    cp = None if completo else db.scalar(select(AuditoriaCheckpoint).order_by(AuditoriaCheckpoint.id.desc()).limit(1))
    anterior, depois_de = (cp.hash, cp.evento_id) if cp else (_ancora(db), 0)
    n, ultimo = 0, (cp.evento_id if cp else None)
    while True:
        linhas = db.scalars(select(EventoAuditoria).where(EventoAuditoria.id > depois_de)
                            .order_by(EventoAuditoria.id).limit(lote)).all()
        if not linhas:
            break
        for ev in linhas:
            if ev.hash_anterior != anterior:
                return Verificacao(False, n, ultimo, ev.id, "corrente interrompida: evento removido ou fora de ordem")
            campos = {k: getattr(ev, k) for k in CAMPOS_HASH}
            if calcular_hash(anterior, ev.momento, campos) != ev.hash:
                return Verificacao(False, n, ultimo, ev.id, "conteúdo do evento alterado")
            anterior, ultimo, n = ev.hash, ev.id, n + 1
        depois_de = linhas[-1].id
        db.expunge_all()  # não acumula 5 anos de eventos na memória
    if n:
        db.add(AuditoriaCheckpoint(evento_id=ultimo, hash=anterior, verificado_em=datetime.now(UTC)))
        db.commit()
    return Verificacao(True, n, ultimo)


# ------------------------------------------------------------------ retenção

def expurgar(agora: datetime | None = None) -> int:
    """Remove eventos além da retenção e registra o próprio expurgo com a âncora da nova corrente."""
    anos = get_settings().auditoria_retencao_anos
    limite = (agora or datetime.now(UTC)) - timedelta(days=365 * anos)
    with _trava_local, db_session.SessionLocal() as db:
        _travar(db)
        primeiro = db.scalar(select(EventoAuditoria).where(EventoAuditoria.momento >= limite)
                             .order_by(EventoAuditoria.id).limit(1))
        corte = primeiro.id if primeiro else None
        q = delete(EventoAuditoria) if corte is None else delete(EventoAuditoria).where(EventoAuditoria.id < corte)
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SET LOCAL planejador.expurgo = 'on'"))
        removidos = db.execute(q).rowcount or 0
        if removidos:
            # sem nenhum evento restante, a corrente recomeça do gênese
            ancora = primeiro.hash_anterior if primeiro else GENESE
            # checkpoint num trecho removido não serve mais de ponto de partida
            cps = delete(AuditoriaCheckpoint)
            db.execute(cps if corte is None else cps.where(AuditoriaCheckpoint.evento_id < corte))
            _inserir(db, [{"acao": "AUDITORIA_EXPURGO", "resultado": "OK", "usuario_id": None,
                           "usuario_login": "sistema", "sessao_id": None, "ip": None, "user_agent": None,
                           "empresa_id": None, "empresa_cnpj": None, "planejamento_id": None,
                           "recurso_tipo": None, "recurso_id": None,
                           "detalhes": {"ancora": ancora, "removidos": removidos, "anteriores_a": limite.isoformat(),
                                        "retencao_anos": anos}}])
        db.commit()
    return removidos


def _principal() -> None:
    p = argparse.ArgumentParser(description="Trilha de auditoria")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--verificar-tudo", action="store_true", help="confere a corrente inteira, do início")
    g.add_argument("--expurgar", action="store_true", help="remove eventos além da retenção")
    a = p.parse_args()
    if a.expurgar:
        print(f"{expurgar()} evento(s) removido(s)")
        return
    with db_session.SessionLocal() as db:
        r = verificar(db, completo=True)
    print(json.dumps(r.como_dict(), ensure_ascii=False))
    raise SystemExit(0 if r.ok else 1)


if __name__ == "__main__":
    _principal()
