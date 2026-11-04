"""Tabelas legais versionadas por vigência (mantidas pelo contador)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
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
    p_ipi: Mapped[Decimal] = mapped_column(Aliquota, default=Decimal("0"))  # só no Anexo II (indústria)


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
    fonte: Mapped[str | None] = mapped_column(String(300))  # norma ou ato que fixou os valores
    alterado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    alterado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReformaHistorico(Base):
    """Valores que um ano do cronograma tinha antes de cada alteração (a lei muda; o histórico explica as simulações antigas)."""

    __tablename__ = "reforma_historico"

    id: Mapped[PK]
    ano: Mapped[int]
    cbs: Mapped[Decimal] = mapped_column(Aliquota)
    ibs: Mapped[Decimal] = mapped_column(Aliquota)
    fator_icms: Mapped[Decimal] = mapped_column(Aliquota)
    fonte: Mapped[str | None] = mapped_column(String(300))
    substituido_por_fonte: Mapped[str] = mapped_column(String(300))
    alterado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    alterado_em: Mapped[Momento]


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


class Norma(Base):
    """Biblioteca de normas: o resumo, o link do texto oficial e onde a norma entra no cálculo."""

    __tablename__ = "norma"

    id: Mapped[PK]
    codigo: Mapped[str] = mapped_column(String(40), unique=True)  # chave estável usada pela carga e pelas regras
    titulo: Mapped[str] = mapped_column(String(160))  # "Lei Complementar 87/1996"
    apelido: Mapped[str | None] = mapped_column(String(80))  # "Lei Kandir"
    esfera: Mapped[str] = mapped_column(String(10))  # FEDERAL, ESTADUAL, CONVENIO
    uf: Mapped[str | None] = mapped_column(String(2))
    tributos: Mapped[str] = mapped_column(String(60))  # "ICMS" ou "PIS,COFINS"
    resumo: Mapped[str] = mapped_column(Text)
    uso_no_calculo: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(300))
    situacao: Mapped[str] = mapped_column(String(10), default="VIGENTE")  # VIGENTE, ALTERADA, REVOGADA
    alterado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    alterado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RegraSt(Base, Vigencia):
    """Mercadoria na substituição tributária do ICMS, por NCM (prefixo), com a vigência e a norma."""

    __tablename__ = "regra_st"
    __table_args__ = (Index("ix_regra_st_uf_ncm", "uf", "ncm"),)

    id: Mapped[PK]
    uf: Mapped[str] = mapped_column(String(2))
    ncm: Mapped[str] = mapped_column(String(8))  # posição, subposição ou código: vale para todo NCM que começa assim
    excecoes: Mapped[str | None] = mapped_column(String(200))  # códigos fora da regra, separados por vírgula
    cest: Mapped[str | None] = mapped_column(String(9))
    segmento: Mapped[str] = mapped_column(String(80))
    item: Mapped[str | None] = mapped_column(String(10))
    descricao: Mapped[str] = mapped_column(Text)
    norma_id: Mapped[int | None] = mapped_column(ForeignKey("norma.id"))  # onde a mercadoria está listada
    revogada_por_id: Mapped[int | None] = mapped_column(ForeignKey("norma.id"))
    alterado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    alterado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AliquotaUf(Base, Vigencia):
    """Alíquota interna geral (modal) do ICMS de cada estado, para o DIFAL das vendas a não contribuinte de outro estado."""

    __tablename__ = "aliquota_uf"
    __table_args__ = (UniqueConstraint("uf", "vigencia_inicio", name="uq_aliquota_uf"),)

    id: Mapped[PK]
    uf: Mapped[str] = mapped_column(String(2))
    aliquota: Mapped[Decimal] = mapped_column(Aliquota)  # sem o fundo de combate à pobreza
    fcp: Mapped[Decimal] = mapped_column(Aliquota, default=Decimal("0"))  # fundo de combate à pobreza na regra geral
    base_dupla: Mapped[bool] = mapped_column(default=True)  # base "por dentro" com a alíquota do destino (LC 190/2022)
    fonte: Mapped[str | None] = mapped_column(String(300))
    alterado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    alterado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RegraReforma(Base, Vigencia):
    """Redução de CBS e IBS por NCM nos anexos da LC 214/2025 (60% ou 100%, que é a alíquota zero)."""

    __tablename__ = "regra_reforma"
    __table_args__ = (Index("ix_regra_reforma_ncm", "ncm"),)

    id: Mapped[PK]
    ncm: Mapped[str] = mapped_column(String(8))  # capítulo, posição, subposição ou código: vale para todo NCM que começa assim
    excecoes: Mapped[str | None] = mapped_column(String(300))
    anexo: Mapped[str] = mapped_column(String(20))
    item: Mapped[str | None] = mapped_column(String(10))
    descricao: Mapped[str] = mapped_column(String(200))
    reducao: Mapped[Decimal] = mapped_column(Aliquota)  # 0,6 = 60%; 1 = alíquota zero
    condicao: Mapped[str | None] = mapped_column(Text)  # requisito que o NCM sozinho não mostra
    cst: Mapped[str] = mapped_column(String(3), default="200")
    cclass_trib: Mapped[str | None] = mapped_column(String(6))
    norma_id: Mapped[int | None] = mapped_column(ForeignKey("norma.id"))
    alterado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    alterado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
