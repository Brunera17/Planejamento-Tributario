"""Usuários e empresas."""

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

from .comum import PK, Momento


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (CheckConstraint("perfil IN ('CONTADOR', 'ANALISTA')", name="ck_usuario_perfil"),)

    id: Mapped[PK]
    nome: Mapped[str] = mapped_column(String(120))
    usuario: Mapped[str] = mapped_column(String(60), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(100))
    perfil: Mapped[str] = mapped_column(String(10))
    ativo: Mapped[bool] = mapped_column(default=True)


class Empresa(Base):
    __tablename__ = "empresa"
    __table_args__ = (
        CheckConstraint("regime_tributario IN ('SIMPLES_NACIONAL', 'LUCRO_PRESUMIDO', 'LUCRO_REAL')",
                        name="ck_empresa_regime"),
        CheckConstraint("atividade IN ('COMERCIO', 'INDUSTRIA', 'SERVICO')", name="ck_empresa_atividade"),
    )

    id: Mapped[PK]
    razao_social: Mapped[str] = mapped_column(String(200))
    cnpj: Mapped[str] = mapped_column(String(14), unique=True)
    regime_tributario: Mapped[str] = mapped_column(String(20))
    anexo_simples: Mapped[str | None] = mapped_column(String(5))
    uf: Mapped[str] = mapped_column(String(2), default="SP")
    cnae: Mapped[str | None] = mapped_column(String(10))
    atividade: Mapped[str] = mapped_column(String(10), default="COMERCIO")
    representante_legal: Mapped[str | None] = mapped_column(String(120))
    telefone: Mapped[str | None] = mapped_column(String(11))
    ativo: Mapped[bool] = mapped_column(default=True)


class ImportacaoEmpresa(Base):
    __tablename__ = "importacao_empresa"

    id: Mapped[PK]
    arquivo: Mapped[str] = mapped_column(String(255))
    importado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    data: Mapped[Momento]
    incluidas: Mapped[int] = mapped_column(default=0)
    atualizadas: Mapped[int] = mapped_column(default=0)
    rejeitadas: Mapped[int] = mapped_column(default=0)
