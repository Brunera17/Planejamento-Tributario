from typing import Literal

from pydantic import Field, field_validator

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
    token: str
    usuario: UsuarioSaida


class UsuarioEntrada(Esquema):
    nome: str = Field(min_length=2, max_length=120)
    usuario: str = Field(min_length=3, max_length=60)
    senha: str = Field(min_length=6)
    perfil: Perfil


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

    @field_validator("telefone")
    @classmethod
    def _tel(cls, v: str | None) -> str | None:
        if not v:
            return None
        d = somente_digitos(v)
        if len(d) not in (10, 11):
            raise ValueError("Telefone deve ter DDD (10 ou 11 dígitos)")
        return d


class EmpresaSaida(EmpresaEntrada):
    id: int
    ativo: bool

    @field_validator("cnpj")
    @classmethod
    def _cnpj(cls, v: str) -> str:  # já validado na gravação
        return v
