"""Planejamento (cabeçalho do estudo), premissas e histórico de status."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

from .cadastro import Empresa
from .comum import PK, Competencia, Momento

STATUS_PLANEJAMENTO = ("EM_COLETA", "EM_CONFERENCIA", "PRONTO_PARA_SIMULAR", "SIMULADO", "APROVADO")


class Planejamento(Base):
    __tablename__ = "planejamento"
    __table_args__ = (
        UniqueConstraint("empresa_id", "competencia_inicial", name="uq_planejamento_empresa_inicio"),
        CheckConstraint("progresso BETWEEN 0 AND 100", name="ck_planejamento_progresso"),
        CheckConstraint("competencia_final >= competencia_inicial", name="ck_planejamento_periodo"),
    )

    id: Mapped[PK]
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    competencia_inicial: Mapped[Competencia]
    competencia_final: Mapped[Competencia]
    status: Mapped[str] = mapped_column(String(20), default="EM_COLETA")
    progresso: Mapped[int] = mapped_column(default=0)
    sem_bens: Mapped[bool] = mapped_column(default=False)
    observacoes_aceitas_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    observacoes_aceitas_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[Momento]

    empresa: Mapped[Empresa] = relationship(lazy="joined")

    def competencias(self) -> list[str]:
        ano, mes = map(int, self.competencia_inicial.split("-"))
        fim = self.competencia_final
        out = []
        while f"{ano:04d}-{mes:02d}" <= fim:
            out.append(f"{ano:04d}-{mes:02d}")
            mes += 1
            if mes > 12:
                ano, mes = ano + 1, 1
        return out


class PremissaPlanejamento(Base):
    __tablename__ = "premissa_planejamento"
    __table_args__ = (UniqueConstraint("planejamento_id", "chave", name="uq_premissa"),)

    id: Mapped[PK]
    planejamento_id: Mapped[int] = mapped_column(ForeignKey("planejamento.id", ondelete="CASCADE"))
    chave: Mapped[str] = mapped_column(String(60))
    valor: Mapped[str] = mapped_column(Text)  # JSON
    alterado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    alterado_em: Mapped[Momento]


class HistoricoStatus(Base):
    __tablename__ = "historico_status"

    id: Mapped[PK]
    planejamento_id: Mapped[int | None] = mapped_column(ForeignKey("planejamento.id", ondelete="CASCADE"))
    levantamento_id: Mapped[int | None] = mapped_column(ForeignKey("levantamento.id", ondelete="CASCADE"))
    status_de: Mapped[str | None] = mapped_column(String(20))
    status_para: Mapped[str] = mapped_column(String(20))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    motivo: Mapped[str | None] = mapped_column(Text)
    data: Mapped[Momento]
