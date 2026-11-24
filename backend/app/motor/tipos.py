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
    reducao_ibs_cbs: Decimal = Decimal("0")  # anexos da LC 214/2025: 0,6 = redução de 60%; 1 = alíquota zero


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
    p_ipi: Decimal = Decimal("0")  # só no Anexo II (indústria)
    p_iss: Decimal = Decimal("0")  # só nos Anexos III, IV e V (serviços)


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
    encargos_folha: Decimal = Decimal("0.278")  # referência: CPP 20% + RAT 2% + terceiros 5,8%
    cpp_patronal: Decimal = Decimal("0.20")  # Lei 8.212/1991, art. 22, I
    inss_pro_labore: Decimal = Decimal("0.20")
    aliq_icms_interna: Decimal = Decimal("0.18")
    aliq_icms_interestadual: Decimal = Decimal("0.12")
    presuncao_servico: Decimal = Decimal("0.32")  # Lei 9.249/1995, art. 15, § 1º, III, e art. 20
    aliq_iss_padrao: Decimal = Decimal("0.05")  # sem a alíquota do município: o teto da LC 116/2003, art. 8º
    fgts: Decimal = Decimal("0.08")  # entra na folha do Fator R (LC 123/2006, art. 18, § 24)


@dataclass(frozen=True)
class Premissas:
    """Premissas ajustáveis por planejamento (tabela premissa_planejamento)."""

    rbt12_informado: Decimal | None = None
    aplicar_st_vendas_internas: bool = False
    # regime especial de fornecimento de refeições (SP, Decreto 51.597/2007): ICMS = receita sem ST × alíquota, sem
    # créditos, no LP e no LR. Vazio = regime normal (débito − crédito)
    aliq_icms_refeicao: Decimal | None = None
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
    # encargos sobre a folha da empresa; vazios usam a referência de 27,8% dos parâmetros
    rat: Decimal | None = None  # 1%, 2% ou 3% pelo risco da atividade preponderante
    fap: Decimal | None = None  # Fator Acidentário de Prevenção: 0,5 a 2,0
    terceiros: Decimal | None = None  # outras entidades pelo FPAS (5,8% no comércio em geral)
    # empresa com serviço: anexo do Simples (III, IV, V ou R = pelo Fator R), ISS do município e presunção do IRPJ no LP
    anexo_servico: str | None = None
    aliq_iss: Decimal | None = None
    presuncao_servico: Decimal | None = None


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
    despesas_estimadas: Decimal = ZERO  # preenchidas por referência de mercado, ainda não substituídas
    ncms_indicio_incorreto: set[str] = field(default_factory=set)
    ncms_confianca_media: set[str] = field(default_factory=set)
    icms_entradas_real: dict[str, Decimal] | None = None  # ICMS destacado nos XML de entrada
    ncm_info: dict[str, InfoNcm] = field(default_factory=dict)
    composicao_informada: bool = False  # False = origem das compras assumida (100% internas)
    estoque_st: CreditoEstoqueSt | None = None
    anexo_simples: str = "I"  # anexo das faixas_simples (LC 123/2006)
    # receita de prestação de serviços por competência (NFS-e), fora dos itens de mercadoria
    servicos: dict[str, Decimal] = field(default_factory=dict)
    anexo_servico: str = "III"  # III, IV, V ou R (o Fator R decide entre III e V)
    faixas_servico: dict[str, list[FaixaSimples]] = field(default_factory=dict)  # Anexos III, IV e V
    # Anexos I e II: com os dois, cada item vai para o anexo do seu CFOP (revenda ou produção própria); vazio = anexo_simples
    faixas_mercadoria: dict[str, list[FaixaSimples]] = field(default_factory=dict)
    # receita bruta mês a mês declarada no PGDAS-D (AAAA-MM): dá a RBT12 de cada mês do planejamento
    receitas_declaradas: dict[str, Decimal] = field(default_factory=dict)


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
    municipal: Decimal = ZERO  # ISS

    @property
    def total(self) -> Decimal:
        return self.estadual + self.federal + self.municipal


@dataclass
class LinhaComparativo:
    regime: Regime
    estadual: Decimal
    federal: Decimal
    total: Decimal
    aliquota_efetiva: Decimal
    diferenca_melhor: Decimal
    posicao: int
    municipal: Decimal = ZERO


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
