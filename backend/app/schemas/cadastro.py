from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.utils.simples import ROMANOS, anexo_da_empresa
from app.utils.validacao import UFS, cnpj_valido, normalizar_cnpj, somente_digitos

from .comum import Esquema

Perfil = Literal["CONTADOR", "ANALISTA"]
RegimeStr = Literal["SIMPLES_NACIONAL", "LUCRO_PRESUMIDO", "LUCRO_REAL"]


class LoginEntrada(Esquema):
    usuario: str
    senha: str


class UsuarioSaida(Esquema):
    id: int
    nome: str
    usuario: str
    perfil: Perfil
    ativo: bool


class LoginSaida(Esquema):
    access: str  # JWT de 15 min; o front guarda só em memória
    expira_em: datetime
    sessao_expira_em: int  # epoch do fim absoluto da sessão (12 h após o login)
    usuario: UsuarioSaida


class UsuarioEntrada(Esquema):
    nome: str = Field(min_length=2, max_length=120)
    usuario: str = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9._-]+$")
    senha: str = Field(min_length=8, max_length=72)
    perfil: Perfil


class UsuarioEdicao(Esquema):
    nome: str = Field(min_length=2, max_length=120)
    perfil: Perfil
    ativo: bool
    senha: str | None = Field(default=None, min_length=8, max_length=72)  # vazio mantém a senha atual


class EmpresaEntrada(Esquema):
    razao_social: str = Field(min_length=2, max_length=200)
    cnpj: str
    regime_tributario: RegimeStr
    anexo_simples: str | None = None
    uf: str = "SP"
    cnae: str | None = None
    atividade: Literal["COMERCIO", "INDUSTRIA", "SERVICO"] = "COMERCIO"
    representante_legal: str | None = None
    telefone: str | None = None

    @field_validator("cnpj")
    @classmethod
    def _cnpj(cls, v: str) -> str:
        if not cnpj_valido(v):
            raise ValueError("CNPJ inválido")
        return normalizar_cnpj(v)

    @field_validator("uf")
    @classmethod
    def _uf(cls, v: str) -> str:
        if v.upper() not in UFS:
            raise ValueError("UF inválida")
        return v.upper()

    @field_validator("cnae")
    @classmethod
    def _cnae(cls, v: str | None) -> str | None:
        if not v:
            return None
        d = somente_digitos(v)
        if len(d) != 7:
            raise ValueError("CNAE deve ter 7 dígitos")
        return d

    @field_validator("anexo_simples")
    @classmethod
    def _anexo_valido(cls, v: str | None) -> str | None:
        if v and v not in ROMANOS:
            raise ValueError("O anexo do Simples vai de I a V")
        return v or None

    @model_validator(mode="after")
    def _anexo(self):
        # optante sem anexo informado: fica o sugerido pelo CNAE ou pela atividade
        if self.regime_tributario == "SIMPLES_NACIONAL" and not self.anexo_simples:
            self.anexo_simples = anexo_da_empresa(None, self.cnae, self.atividade)[0]
        return self

    @field_validator("telefone")
    @classmethod
    def _tel(cls, v: str | None) -> str | None:
        if not v:
            return None
        d = somente_digitos(v)
        if len(d) not in (10, 11):
            raise ValueError("Telefone deve ter DDD (10 ou 11 dígitos)")
        return d


class EmpresaSaida(Esquema):
    id: int
    razao_social: str
    cnpj: str
    regime_tributario: RegimeStr
    anexo_simples: str | None
    uf: str
    cnae: str | None
    atividade: str
    representante_legal: str | None
    telefone: str | None
    ativo: bool
    criado_em: datetime | None
