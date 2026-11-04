"""Trilha de auditoria: só inserção, encadeada por hash (cada linha cita o hash da anterior)."""
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# BIGINT no Postgres, INTEGER no SQLite (só INTEGER PRIMARY KEY vira autoincremento lá)
IdGrande = BigInteger().with_variant(Integer(), "sqlite")


class EventoAuditoria(Base):
    __tablename__ = "evento_auditoria"
    __table_args__ = (
        Index("ix_auditoria_momento", "momento"),
        Index("ix_auditoria_usuario", "usuario_id", "momento"),
        Index("ix_auditoria_empresa", "empresa_id", "momento"),
        Index("ix_auditoria_acao", "acao", "momento"),
    )

    id: Mapped[int] = mapped_column(IdGrande, primary_key=True)
    momento: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acao: Mapped[str] = mapped_column(String(40))
    resultado: Mapped[str] = mapped_column(String(10))  # OK / FALHA / NEGADO
    # sem chave estrangeira: excluir usuário, empresa ou planejamento não apaga o rastro
    usuario_id: Mapped[int | None]
    usuario_login: Mapped[str | None] = mapped_column(String(60))
    sessao_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    empresa_id: Mapped[int | None]
    empresa_cnpj: Mapped[str | None] = mapped_column(String(14))
    planejamento_id: Mapped[int | None]
    recurso_tipo: Mapped[str | None] = mapped_column(String(30))
    recurso_id: Mapped[int | None]
    detalhes: Mapped[dict | None] = mapped_column(JSON)
    hash_anterior: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class AuditoriaCheckpoint(Base):
    """Último trecho da corrente já conferido: a verificação seguinte começa daqui."""
    __tablename__ = "auditoria_checkpoint"

    id: Mapped[int] = mapped_column(primary_key=True)
    evento_id: Mapped[int] = mapped_column(IdGrande)
    hash: Mapped[str] = mapped_column(String(64))
    verificado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
