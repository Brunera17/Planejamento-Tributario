"""Tipos de entrada e saída do motor de cálculo.

O motor é composto apenas de funções puras: recebe uma `EntradaSimulacao` já
classificada (CFOP, NCM e âmbito resolvidos) e devolve um `ResultadoSimulacao`.
Nenhum módulo deste pacote acessa banco de dados, arquivos ou rede.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

ZERO = Decimal("0")
UM = Decimal("1")


class Regime(str, Enum):
    SIMPLES_NACIONAL = "SIMPLES_NACIONAL"
    LUCRO_PRESUMIDO = "LUCRO_PRESUMIDO"
    LUCRO_REAL = "LUCRO_REAL"


NOME_REGIME = {
    Regime.SIMPLES_NACIONAL: "Simples Nacional",
    Regime.LUCRO_PRESUMIDO: "Lucro Presumido",
    Regime.LUCRO_REAL: "Lucro Real",
}


class Ambito(str, Enum):
    INTERNA = "INTERNA"
    INTERESTADUAL = "INTERESTADUAL"


# ---------------------------------------------------------------- entradas


@dataclass(frozen=True)
class DestinoDifal:
    """Venda a consumidor final não contribuinte de outro estado: o remetente recolhe a diferença ao destino."""

    uf: str
    aliquota: Decimal  # alíquota interna do destino, sem FCP
    fcp: Decimal = Decimal("0")
    base_dupla: bool = True


@dataclass(frozen=True)
class ItemSaida:
    """Item de NF-e de saída (ou grupo de itens com as mesmas características)."""

    competencia: str  # AAAA-MM
    ncm: str
    cfop: int
    ambito: Ambito
    gera_receita: bool
    monofasico: bool
    sujeito_st: bool
    valor: Decimal  # valor total do item (vProd + acréscimos − descontos)
    ref: str | None = None  # id do nota_item, para rastreabilidade
    aliq_interestadual: Decimal | None = None  # 4%, 7% ou 12% pela origem e pelo destino; None usa o parâmetro
    difal: DestinoDifal | None = None


@dataclass(frozen=True)
class Despesa:
    competencia: str
    descricao: str
    valor: Decimal
    dedutivel: bool = True
    credito_pis_cofins: bool = False
    credito_ibs_cbs: bool = True


@dataclass(frozen=True)
class FaixaSimples:
    faixa: int
    rbt12_de: Decimal
    rbt12_ate: Decimal
    aliq_nominal: Decimal
    parcela_deduzir: Decimal
    p_irpj: Decimal
    p_csll: Decimal
    p_cofins: Decimal
    p_pis: Decimal
    p_cpp: Decimal
    p_icms: Decimal


@dataclass(frozen=True)
class AnoReforma:
    ano: int
    cbs: Decimal
    ibs: Decimal
    fator_icms: Decimal  # fração do ICMS mantida no ano (1 = integral, 0 = extinto)


@dataclass(frozen=True)
class Parametros:
    """Parâmetros legais vigentes (tabela parametro_tributario)."""

    pis_cumulativo: Decimal = Decimal("0.0065")
    cofins_cumulativo: Decimal = Decimal("0.03")
    pis_nao_cumulativo: Decimal = Decimal("0.0165")
    cofins_nao_cumulativo: Decimal = Decimal("0.076")
    irpj: Decimal = Decimal("0.15")
    irpj_adicional: Decimal = Decimal("0.10")
    irpj_limite_adicional_mensal: Decimal = Decimal("20000")
    csll: Decimal = Decimal("0.09")
    presuncao_irpj: Decimal = Decimal("0.08")
    presuncao_csll: Decimal = Decimal("0.12")
    acrescimo_presuncao: Decimal = Decimal("0.10")  # LC 224/2025
    limite_receita_anual_presuncao: Decimal = Decimal("5000000")  # LC 224/2025
    compensacao_prejuizo_limite: Decimal = Decimal("0.30")
    sublimite_simples: Decimal = Decimal("3600000")
    teto_simples: Decimal = Decimal("4800000")
    alerta_sublimite: Decimal = Decimal("0.70")
    encargos_folha: Decimal = Decimal("0.278")
    inss_pro_labore: Decimal = Decimal("0.20")
    aliq_icms_interna: Decimal = Decimal("0.18")
    aliq_icms_interestadual: Decimal = Decimal("0.12")


@dataclass(frozen=True)
class Premissas:
    """Premissas ajustáveis por planejamento (tabela premissa_planejamento)."""

    rbt12_informado: Decimal | None = None
    aplicar_st_vendas_internas: bool = False
    excluir_icms_base_pis_cofins: bool = False  # Tema 69/STF
    credito_frete_integral: bool = False  # False = proporcional aos não monofásicos
    pct_compras_credito_ibs_cbs: Decimal = UM
    # alíquota de ICMS da origem -> participação nas compras (soma = 1)
    composicao_compras: dict[Decimal, Decimal] = field(
        default_factory=lambda: {Decimal("0.18"): UM}
    )
    estoque_inicial: Decimal | None = None
    estoque_final: Decimal | None = None
    adicoes_lr: Decimal = ZERO
    exclusoes_lr: Decimal = ZERO
    prejuizo_fiscal_compensar: Decimal = ZERO
    regime_atual: Regime = Regime.SIMPLES_NACIONAL
    vendas_b2c: bool = True


@dataclass(frozen=True)
class InfoNcm:
    """Classificação e orientação do NCM (tabela ncm_regra), copiada para a simulação."""

    produto_exemplo: str | None = None
    confianca: str = "ALTA"
    indicio_ncm_incorreto: bool = False
    requer_revisao: bool = False
    acao_recomendada: str | None = None
    cst_ibs_cbs: str | None = None
    cclass_trib: str | None = None
    beneficio_reforma: str | None = None


@dataclass(frozen=True)
class CreditoEstoqueSt:
    """Crédito do ICMS-ST do estoque quando a mercadoria sai da substituição tributária (estimado pelas entradas)."""

    credito: Decimal
    corte: str  # dd/mm/aaaa: estoque levantado no fim deste dia
    inicio_uso: str  # AAAA-MM
    regime_rpa: bool
    norma: str | None


@dataclass(frozen=True)
class EntradaSimulacao:
    competencias: list[str]
    itens: list[ItemSaida]
    devolucoes: dict[str, Decimal]
    compras: dict[str, Decimal]
    despesas: list[Despesa]
    folha: dict[str, Decimal]
    pro_labore: dict[str, Decimal]
    faixas_simples: list[FaixaSimples]
    reforma: list[AnoReforma]
    parametros: Parametros = field(default_factory=Parametros)
    premissas: Premissas = field(default_factory=Premissas)
    # informações da coleta usadas pelas regras de oportunidade
    folha_informada: bool = False
    despesas_nao_informadas: list[str] = field(default_factory=list)
    ncms_indicio_incorreto: set[str] = field(default_factory=set)
    ncms_confianca_media: set[str] = field(default_factory=set)
    icms_entradas_real: dict[str, Decimal] | None = None  # ICMS destacado nos XML de entrada
    ncm_info: dict[str, InfoNcm] = field(default_factory=dict)
    composicao_informada: bool = False  # False = origem das compras assumida (100% internas)
    estoque_st: CreditoEstoqueSt | None = None


# ------------------------------------------------------------------ saídas


@dataclass
class PassoMemoria:
    secao: str
    descricao: str
    formula: str
    valor: Decimal
    competencia: str | None = None
    fundamento: str | None = None


@dataclass
class Memoria:
    passos: list[PassoMemoria] = field(default_factory=list)

    def registrar(
        self,
        secao: str,
        descricao: str,
        formula: str,
        valor: Decimal,
        competencia: str | None = None,
        fundamento: str | None = None,
    ) -> Decimal:
        self.passos.append(PassoMemoria(secao, descricao, formula, valor, competencia, fundamento))
        return valor


@dataclass
class TributoValor:
    tributo: str
    valor: Decimal
    competencia: str | None = None  # None = período inteiro


@dataclass
class ResultadoRegime:
    regime: Regime
    estadual: Decimal
    federal: Decimal
    tributos: list[TributoValor]
    detalhes: dict[str, Decimal] = field(default_factory=dict)
    elegivel: bool = True

    @property
    def total(self) -> Decimal:
        return self.estadual + self.federal


@dataclass
class LinhaComparativo:
    regime: Regime
    estadual: Decimal
    federal: Decimal
    total: Decimal
    aliquota_efetiva: Decimal
    diferenca_melhor: Decimal
    posicao: int


@dataclass
class LinhaReforma:
    ano: int
    cbs: Decimal
    ibs: Decimal
    fator_icms: Decimal
    cargas: dict[Regime, Decimal]
    aliquotas: dict[Regime, Decimal]
    melhor: Regime


@dataclass
class Oportunidade:
    codigo: str
    titulo: str
    impacto: Decimal | None  # None = qualitativa
    prioridade: str  # ALTA, MEDIA, BAIXA
    acao: str


@dataclass
class PontoCritico:
    codigo: str
    texto: str


@dataclass
class LinhaCrescimento:
    rbt12: Decimal
    aliquota_das: Decimal
    aliquota_simples: Decimal | None  # None = inelegível
    aliquota_lp: Decimal
    aliquota_lr: Decimal
    melhor: Regime
    observacao: str


@dataclass
class LinhaNcm:
    ncm: str
    receita: Decimal
    participacao: Decimal
    monofasico: bool
    sujeito_st: bool
    sem_regra: bool
    produto_exemplo: str | None
    confianca: str | None
    indicio_ncm_incorreto: bool
    requer_revisao: bool
    acao_recomendada: str | None
    cst_ibs_cbs: str | None
    cclass_trib: str | None
    beneficio_reforma: str | None


@dataclass
class ResultadoSimulacao:
    base: dict[str, dict[str, Decimal]]  # competência (ou "TOTAL") -> indicador -> valor
    simples: ResultadoRegime
    presumido: ResultadoRegime
    real: ResultadoRegime
    comparativo: list[LinhaComparativo]
    melhor_regime: Regime
    reforma: list[LinhaReforma]
    oportunidades: list[Oportunidade]
    pontos_criticos: list[PontoCritico]
    crescimento: list[LinhaCrescimento]
    margem_equilibrio_lr_lp: Decimal | None
    memoria: Memoria
    verificacao_ncm: list[LinhaNcm] = field(default_factory=list)
