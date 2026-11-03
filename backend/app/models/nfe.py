"""Notas fiscais importadas (saídas e entradas)."""
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

from .comum import PK, Aliquota, Competencia, Dinheiro, Momento, Valor


class ImportacaoNfe(Base):
    __tablename__ = "importacao_nfe"

    id: Mapped[PK]
    planejamento_id: Mapped[int] = mapped_column(ForeignKey("planejamento.id", ondelete="CASCADE"))
    origem: Mapped[str] = mapped_column(String(10))  # XML, RELATORIO
    arquivo: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(15), default="PROCESSANDO")
    lidos: Mapped[int] = mapped_column(default=0)
    importados: Mapped[int] = mapped_column(default=0)
    ignorados: Mapped[int] = mapped_column(default=0)
    log: Mapped[str | None] = mapped_column(Text)
    importado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    importado_em: Mapped[Momento]


class NotaFiscal(Base):
    __tablename__ = "nota_fiscal"
    __table_args__ = (UniqueConstraint("planejamento_id", "chave_acesso", name="uq_nota_chave"),)

    id: Mapped[PK]
    planejamento_id: Mapped[int] = mapped_column(ForeignKey("planejamento.id", ondelete="CASCADE"))
    importacao_id: Mapped[int | None] = mapped_column(ForeignKey("importacao_nfe.id", ondelete="SET NULL"))
    chave_acesso: Mapped[str] = mapped_column(String(44))
    numero: Mapped[str] = mapped_column(String(12))
    data_emissao: Mapped[date] = mapped_column(Date)
    competencia: Mapped[Competencia]
    tipo: Mapped[str] = mapped_column(String(7))  # SAIDA, ENTRADA
    uf_emitente: Mapped[str | None] = mapped_column(String(2))
    uf_destinatario: Mapped[str | None] = mapped_column(String(2))
    crt_emitente: Mapped[str | None] = mapped_column(String(1))
    consumidor_final: Mapped[bool | None]
    dest_contribuinte: Mapped[bool | None]  # indIEDest 1 = contribuinte; 2 e 9 (ou CPF) = não contribuinte


class NotaItem(Base):
    __tablename__ = "nota_item"
    __table_args__ = (
        UniqueConstraint("nota_fiscal_id", "n_item", name="uq_nota_item"),
        Index("ix_nota_item_ncm_cfop", "ncm", "cfop"),
    )

    id: Mapped[PK]
    nota_fiscal_id: Mapped[int] = mapped_column(ForeignKey("nota_fiscal.id", ondelete="CASCADE"))
    n_item: Mapped[int]
    cod_produto: Mapped[str | None] = mapped_column(String(60))
    descricao: Mapped[str | None] = mapped_column(String(200))
    ncm: Mapped[str] = mapped_column(String(8))
    cfop: Mapped[int]
    quantidade: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    vl_unitario: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    vl_produtos: Mapped[Valor]
    vl_total: Mapped[Valor]
    vl_icms: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    cst_pis: Mapped[str | None] = mapped_column(String(2))
    orig_icms: Mapped[str | None] = mapped_column(String(1))
    cst_icms: Mapped[str | None] = mapped_column(String(3))
    aliq_icms: Mapped[Decimal | None] = mapped_column(Aliquota)
    bc_st: Mapped[Decimal | None] = mapped_column(Dinheiro)  # base da ST retida (vBCST ou vBCSTRet)
    vl_icms_st: Mapped[Decimal | None] = mapped_column(Dinheiro)
