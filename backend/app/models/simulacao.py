"""Simulações (imutáveis), resultados, memória de cálculo, oportunidades e relatórios."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

from .comum import PK, Dinheiro, Momento


class Simulacao(Base):
    __tablename__ = "simulacao"
    __table_args__ = (UniqueConstraint("planejamento_id", "versao", name="uq_simulacao_versao"),)

    id: Mapped[PK]
    planejamento_id: Mapped[int] = mapped_column(ForeignKey("planejamento.id", ondelete="CASCADE"))
    versao: Mapped[int]
    tipo: Mapped[str] = mapped_column(String(12))  # PRELIMINAR, FINAL
    hash_entrada: Mapped[str] = mapped_column(String(64))
    entrada_json: Mapped[str] = mapped_column(Text)  # premissas, parâmetros e tabelas usadas
    resultado_json: Mapped[str] = mapped_column(Text)
    regime_recomendado: Mapped[str] = mapped_column(String(20))
    pendencias: Mapped[str | None] = mapped_column(Text)
    executada_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    executada_em: Mapped[Momento]
    desatualizada: Mapped[bool] = mapped_column(default=False)
    aprovada_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    aprovada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SimulacaoResultado(Base):
    __tablename__ = "simulacao_resultado"

    id: Mapped[PK]
    simulacao_id: Mapped[int] = mapped_column(ForeignKey("simulacao.id", ondelete="CASCADE"), index=True)
    regime: Mapped[str] = mapped_column(String(20))
    ano: Mapped[int]
    competencia: Mapped[str | None] = mapped_column(String(7))
    tributo: Mapped[str] = mapped_column(String(30))
    valor: Mapped[Decimal] = mapped_column(Dinheiro)


class MemoriaCalculo(Base):
    __tablename__ = "memoria_calculo"

    id: Mapped[PK]
    simulacao_id: Mapped[int] = mapped_column(ForeignKey("simulacao.id", ondelete="CASCADE"), index=True)
    ordem: Mapped[int]
    secao: Mapped[str] = mapped_column(String(40))
    competencia: Mapped[str | None] = mapped_column(String(7))
    descricao: Mapped[str] = mapped_column(String(200))
    formula: Mapped[str] = mapped_column(Text)
    resultado: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    fundamento: Mapped[str | None] = mapped_column(String(200))


class OportunidadeRegistro(Base):
    __tablename__ = "oportunidade"

    id: Mapped[PK]
    simulacao_id: Mapped[int] = mapped_column(ForeignKey("simulacao.id", ondelete="CASCADE"), index=True)
    codigo: Mapped[str] = mapped_column(String(40))
    titulo: Mapped[str] = mapped_column(String(200))
    impacto: Mapped[Decimal | None] = mapped_column(Dinheiro)
    prioridade: Mapped[str] = mapped_column(String(5))
    acao: Mapped[str] = mapped_column(Text)
    situacao: Mapped[str] = mapped_column(String(12), default="ABERTA")  # ABERTA, CONFIRMADA, DESCARTADA
    motivo: Mapped[str | None] = mapped_column(Text)


class RelatorioPdf(Base):
    __tablename__ = "relatorio_pdf"

    id: Mapped[PK]
    planejamento_id: Mapped[int] = mapped_column(ForeignKey("planejamento.id", ondelete="CASCADE"))
    simulacao_id: Mapped[int] = mapped_column(ForeignKey("simulacao.id"))
    arquivo: Mapped[str] = mapped_column(String(255))
    hash_sha256: Mapped[str] = mapped_column(String(64))
    preliminar: Mapped[bool]
    gerado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    gerado_em: Mapped[Momento]
