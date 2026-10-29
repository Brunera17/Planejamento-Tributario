"""Tabelas legais versionadas por vigência (mantidas pelo contador)."""
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

from .comum import PK, Aliquota, Dinheiro, Momento


class Vigencia:
    vigencia_inicio: Mapped[date] = mapped_column(Date, default=date(2000, 1, 1))
    vigencia_fim: Mapped[date | None] = mapped_column(Date)


class SimplesFaixa(Base, Vigencia):
    __tablename__ = "simples_faixa"
    __table_args__ = (UniqueConstraint("anexo", "faixa", "vigencia_inicio", name="uq_simples_faixa"),)

    id: Mapped[PK]
    anexo: Mapped[str] = mapped_column(String(5))
    faixa: Mapped[int]
    rbt12_de: Mapped[Decimal] = mapped_column(Dinheiro)
    rbt12_ate: Mapped[Decimal] = mapped_column(Dinheiro)
    aliq_nominal: Mapped[Decimal] = mapped_column(Aliquota)
    parcela_deduzir: Mapped[Decimal] = mapped_column(Dinheiro)
    p_irpj: Mapped[Decimal] = mapped_column(Aliquota)
    p_csll: Mapped[Decimal] = mapped_column(Aliquota)
    p_cofins: Mapped[Decimal] = mapped_column(Aliquota)
    p_pis: Mapped[Decimal] = mapped_column(Aliquota)
    p_cpp: Mapped[Decimal] = mapped_column(Aliquota)
    p_icms: Mapped[Decimal] = mapped_column(Aliquota)


class ParametroTributario(Base, Vigencia):
    __tablename__ = "parametro_tributario"
    __table_args__ = (UniqueConstraint("chave", "vigencia_inicio", name="uq_parametro"),)

    id: Mapped[PK]
    chave: Mapped[str] = mapped_column(String(60))
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    descricao: Mapped[str] = mapped_column(String(200))
    fundamento: Mapped[str | None] = mapped_column(String(200))


class ReformaCronograma(Base):
    __tablename__ = "reforma_cronograma"

    ano: Mapped[int] = mapped_column(primary_key=True)
    cbs: Mapped[Decimal] = mapped_column(Aliquota)
    ibs: Mapped[Decimal] = mapped_column(Aliquota)
    fator_icms: Mapped[Decimal] = mapped_column(Aliquota)
    situacao: Mapped[str | None] = mapped_column(String(200))


class CfopRegra(Base):
    __tablename__ = "cfop_regra"

    cfop: Mapped[int] = mapped_column(primary_key=True)
    natureza: Mapped[str] = mapped_column(String(200))
    gera_receita: Mapped[bool]


class NcmRegra(Base):
    __tablename__ = "ncm_regra"

    ncm: Mapped[str] = mapped_column(String(8), primary_key=True)
    monofasico: Mapped[bool]
    confianca: Mapped[str] = mapped_column(String(5), default="ALTA")  # ALTA, MEDIA
    sujeito_st: Mapped[bool] = mapped_column(default=False)
    indicio_ncm_incorreto: Mapped[bool] = mapped_column(default=False)  # reclassificação pode torná-lo monofásico
    requer_revisao: Mapped[bool] = mapped_column(default=False)  # há ação a tomar no cadastro do produto
    acao_recomendada: Mapped[str | None] = mapped_column(Text)
    cst_ibs_cbs: Mapped[str | None] = mapped_column(String(3))
    cclass_trib: Mapped[str | None] = mapped_column(String(6))
    beneficio_reforma: Mapped[str | None] = mapped_column(String(120))
    fundamento: Mapped[str | None] = mapped_column(String(200))
    produto_exemplo: Mapped[str | None] = mapped_column(String(200))
    observacao: Mapped[str | None] = mapped_column(Text)
    aprovado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    aprovado_em: Mapped[Momento]
