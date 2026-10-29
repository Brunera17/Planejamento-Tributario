"""Coleta: levantamento de despesas (portal original), compras, devoluções, folha, bens e documentos."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

from .comum import PK, Aliquota, Competencia, Dinheiro, Momento, Valor


class GrupoDespesa(Base):
    __tablename__ = "grupo_despesa"

    id: Mapped[PK]
    nome: Mapped[str] = mapped_column(String(80), unique=True)
    ordem: Mapped[int]


class ItemDespesa(Base):
    __tablename__ = "item_despesa"

    id: Mapped[PK]
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupo_despesa.id"))
    nome: Mapped[str] = mapped_column(String(120))
    ordem: Mapped[int]
    ativo: Mapped[bool] = mapped_column(default=True)
    dedutivel_irpj_csll: Mapped[bool] = mapped_column(default=True)
    credito_pis_cofins: Mapped[bool] = mapped_column(default=False)
    credito_ibs_cbs: Mapped[bool] = mapped_column(default=True)
    natureza: Mapped[str | None] = mapped_column(Text)


class Levantamento(Base):
    __tablename__ = "levantamento"
    __table_args__ = (UniqueConstraint("planejamento_id", "competencia", name="uq_levantamento_competencia"),)

    id: Mapped[PK]
    planejamento_id: Mapped[int] = mapped_column(ForeignKey("planejamento.id", ondelete="CASCADE"))
    competencia: Mapped[Competencia]
    status: Mapped[str] = mapped_column(String(20), default="EM_PREENCHIMENTO")
    criado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[Momento]
    alterado_em: Mapped[Momento]
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LevantamentoItem(Base):
    """Linha ausente = não informado; valor 0 = informado ("não houve")."""

    __tablename__ = "levantamento_item"
    __table_args__ = (
        UniqueConstraint("levantamento_id", "item_despesa_id", name="uq_levantamento_item"),
        CheckConstraint("valor >= 0", name="ck_levantamento_item_valor"),
    )

    id: Mapped[PK]
    levantamento_id: Mapped[int] = mapped_column(ForeignKey("levantamento.id", ondelete="CASCADE"))
    item_despesa_id: Mapped[int] = mapped_column(ForeignKey("item_despesa.id"))
    valor: Mapped[Valor]


class LevantamentoGrupo(Base):
    __tablename__ = "levantamento_grupo"

    levantamento_id: Mapped[int] = mapped_column(ForeignKey("levantamento.id", ondelete="CASCADE"), primary_key=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupo_despesa.id"), primary_key=True)
    possui_outras: Mapped[bool]


class OutraDespesa(Base):
    __tablename__ = "outra_despesa"
    __table_args__ = (CheckConstraint("valor >= 0", name="ck_outra_despesa_valor"),)

    id: Mapped[PK]
    levantamento_id: Mapped[int] = mapped_column(ForeignKey("levantamento.id", ondelete="CASCADE"))
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupo_despesa.id"))
    descricao: Mapped[str] = mapped_column(String(200))
    valor: Mapped[Valor]


class ValorMensal:
    """Base para valores mensais informados por planejamento (vazio = não informado)."""

    id: Mapped[PK]
    competencia: Mapped[Competencia]


class CompraMensal(Base, ValorMensal):
    __tablename__ = "compra_mensal"
    __table_args__ = (UniqueConstraint("planejamento_id", "competencia", name="uq_compra_mensal"),
                      CheckConstraint("valor >= 0", name="ck_compra_valor"))
    planejamento_id: Mapped[int] = mapped_column(ForeignKey("planejamento.id", ondelete="CASCADE"))
    valor: Mapped[Valor]


class DevolucaoMensal(Base, ValorMensal):
    __tablename__ = "devolucao_mensal"
    __table_args__ = (UniqueConstraint("planejamento_id", "competencia", name="uq_devolucao_mensal"),
                      CheckConstraint("valor >= 0", name="ck_devolucao_valor"))
    planejamento_id: Mapped[int] = mapped_column(ForeignKey("planejamento.id", ondelete="CASCADE"))
    valor: Mapped[Valor]


class FolhaMensal(Base, ValorMensal):
    __tablename__ = "folha_mensal"
    __table_args__ = (UniqueConstraint("planejamento_id", "competencia", name="uq_folha_mensal"),)
    planejamento_id: Mapped[int] = mapped_column(ForeignKey("planejamento.id", ondelete="CASCADE"))
    folha: Mapped[Decimal | None] = mapped_column(Dinheiro)
    pro_labore: Mapped[Decimal | None] = mapped_column(Dinheiro)


class CompraOrigem(Base):
    __tablename__ = "compra_origem"
    __table_args__ = (UniqueConstraint("planejamento_id", "aliquota", name="uq_compra_origem"),)

    id: Mapped[PK]
    planejamento_id: Mapped[int] = mapped_column(ForeignKey("planejamento.id", ondelete="CASCADE"))
    origem: Mapped[str] = mapped_column(String(60))
    aliquota: Mapped[Decimal] = mapped_column(Aliquota)
    percentual: Mapped[Decimal] = mapped_column(Aliquota)


class Bem(Base):
    __tablename__ = "bem"
    __table_args__ = (
        CheckConstraint("valor > 1200", name="ck_bem_valor"),
        CheckConstraint("tipo IN ('VEICULOS', 'MOVEIS_UTENSILIOS', 'MAQUINAS_EQUIPAMENTOS', 'IMOVEL')", name="ck_bem_tipo"),
    )

    id: Mapped[PK]
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    tipo: Mapped[str] = mapped_column(String(25))
    descricao: Mapped[str] = mapped_column(String(200))
    data_aquisicao: Mapped[date] = mapped_column(Date)
    valor: Mapped[Valor]


class TipoDocumento(Base):
    __tablename__ = "tipo_documento"

    id: Mapped[PK]
    nome: Mapped[str] = mapped_column(String(120), unique=True)
    ordem: Mapped[int] = mapped_column(default=0)


class Documento(Base):
    __tablename__ = "documento"
    __table_args__ = (UniqueConstraint("levantamento_id", "tipo_documento_id", name="uq_documento"),)

    id: Mapped[PK]
    levantamento_id: Mapped[int] = mapped_column(ForeignKey("levantamento.id", ondelete="CASCADE"))
    tipo_documento_id: Mapped[int] = mapped_column(ForeignKey("tipo_documento.id"))
    arquivo: Mapped[str | None] = mapped_column(String(255))
    nao_se_aplica: Mapped[bool] = mapped_column(default=False)
    justificativa: Mapped[str | None] = mapped_column(Text)
    enviado_em: Mapped[Momento]


class PesoProgresso(Base):
    __tablename__ = "peso_progresso"

    bloco: Mapped[str] = mapped_column(String(30), primary_key=True)
    peso: Mapped[int]
    alterado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    alterado_em: Mapped[Momento]
