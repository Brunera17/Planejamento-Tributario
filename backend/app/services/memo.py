"""Memória por sessão de banco para os diagnósticos caros de um planejamento.

Uma gravação recalcula progresso, premissas e revisão de produtos, e várias dessas funções chamam umas às outras
(progresso → revisão + premissas → PGDAS; simulação → entrada → as mesmas). Dentro da mesma sessão de banco
(uma requisição), o resultado é reaproveitado enquanto nada for gravado: qualquer flush, commit, rollback ou
INSERT/UPDATE/DELETE em massa apaga a memória.

O resultado é compartilhado entre quem chama: trate-o como somente leitura.
"""
from __future__ import annotations

import functools
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy import event
from sqlalchemy.orm import Session

CHAVE = "_memo_planejamento"
T = TypeVar("T")


def limpar(db: Session) -> None:
    db.info.pop(CHAVE, None)


def por_planejamento(f: Callable[..., T]) -> Callable[..., T]:
    """Para funções f(db, p) sem outros argumentos; com argumentos extras, calcula sempre."""
    nome = f"{f.__module__}.{f.__qualname__}"

    @functools.wraps(f)
    def envolvida(db: Session, p, *args, **kwargs) -> T:
        if args or kwargs or p.id is None:
            return f(db, p, *args, **kwargs)
        memoria = db.info.setdefault(CHAVE, {})
        chave = (nome, p.id)
        if chave not in memoria:
            memoria[chave] = f(db, p)
        return memoria[chave]

    envolvida.sem_memo = f  # type: ignore[attr-defined]
    return envolvida


@event.listens_for(Session, "after_flush")
def _apos_flush(db: Session, _contexto) -> None:
    limpar(db)


@event.listens_for(Session, "after_commit")
def _apos_commit(db: Session) -> None:
    limpar(db)


@event.listens_for(Session, "after_soft_rollback")
def _apos_rollback(db: Session, _transacao) -> None:
    limpar(db)


@event.listens_for(Session, "do_orm_execute")
def _gravacao_em_massa(estado) -> None:
    if estado.is_insert or estado.is_update or estado.is_delete:
        limpar(estado.session)
