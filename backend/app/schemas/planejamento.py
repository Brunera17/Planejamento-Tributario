from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from .comum import CompetenciaStr, Esquema, ValorMonetario


class PlanejamentoEntrada(Esquema):
    empresa_id: int
    competencia_inicial: CompetenciaStr
    competencia_final: CompetenciaStr

    @model_validator(mode="after")
    def _periodo(self):
        if self.competencia_final < self.competencia_inicial:
            raise ValueError("A competência final deve ser posterior à inicial")
        return self


class PlanejamentoSaida(Esquema):
    id: int
    empresa_id: int
    razao_social: str
    cnpj: str
    regime_tributario: str
    competencia_inicial: str
    competencia_final: str
    status: str
    progresso: int
    sem_bens: bool
    criado_em: datetime


class StatusEntrada(Esquema):
    status: str
    motivo: str | None = None


class ValorCompetencia(Esquema):
    competencia: CompetenciaStr
    valor: ValorMonetario


class FolhaCompetencia(Esquema):
    competencia: CompetenciaStr
    folha: ValorMonetario | None = None
    pro_labore: ValorMonetario | None = None


class OrigemCompra(Esquema):
    origem: str
    aliquota: Decimal = Field(ge=0, le=1)
    percentual: Decimal = Field(ge=0, le=1)


class DespesaItemEntrada(Esquema):
    item_despesa_id: int
    valor: ValorMonetario | None  # None = apagar (volta a "não informado")


class OutraDespesaEntrada(Esquema):
    grupo_id: int
    descricao: str = Field(min_length=2, max_length=200)
    valor: ValorMonetario


class LevantamentoEntrada(Esquema):
    itens: list[DespesaItemEntrada] = []
    grupos_sem_outras: list[int] = []
    outras: list[OutraDespesaEntrada] | None = None  # None = não altera


class BlocoProgresso(Esquema):
    codigo: str
    nome: str
    peso: int
    esperados: int
    preenchidos: int
    pendencias: list[dict]


class ProgressoSaida(Esquema):
    progresso: int
    blocos: list[BlocoProgresso]
