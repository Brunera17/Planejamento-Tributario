"""Calculadora do Simples Nacional por nota: DAS aproximado sem abrir planejamento. Nada é gravado."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Form, UploadFile
from pydantic import Field
from sqlalchemy import select

from app.api.deps import DB, UsuarioAtual
from app.core.config import get_settings
from app.core.erros import ErroNegocio, NaoEncontrado
from app.models import Empresa, ParametroTributario
from app.motor import calculadora_simples as motor
from app.schemas.comum import CompetenciaStr, Esquema, ValorMonetario
from app.seeds import tabelas
from app.services import calculadora_simples as servico
from app.services import pgdas
from app.services.entrada import _vigentes, faixas_vigentes
from app.services.nfe_xml import ler_arquivos
from app.services.serializacao import para_json
from app.utils.simples import anexo_da_empresa
from app.utils.upload import ler_limitado

router = APIRouter(prefix="/calculadora-simples", tags=["Calculadora do Simples"])

Anexo = Literal["I", "II", "III", "IV", "V"]


class Linha(Esquema):
    descricao: str = Field("Valor digitado", max_length=150)
    valor: ValorMonetario
    anexo: Anexo = "I"
    competencia: CompetenciaStr | None = None
    st: bool = False
    monofasico: bool = False
    iss_fora_do_das: Literal["RETIDO", "FIXO", "ISENTO"] | None = None
    fator_r: bool = False


class Pedido(Esquema):
    rbt12: ValorMonetario
    folha_12m: ValorMonetario | None = None
    receita_12m: ValorMonetario | None = None
    aliq_iss_municipio: Annotated[Decimal, Field(ge=0, le=Decimal("0.05"))] | None = None  # 2% a 5% (LC 116/2003)
    linhas: Annotated[list[Linha], Field(min_length=1, max_length=5000)]


def _empresa(db, empresa_id: int) -> Empresa:
    e = db.get(Empresa, empresa_id)
    if e is None:
        raise NaoEncontrado("Empresa")
    return e


@router.get("/empresas/{empresa_id}")
def dados_da_empresa(empresa_id: int, db: DB, _: UsuarioAtual):
    """Anexo do cadastro e RBT12 do extrato do PGDAS-D mais recente, para preencher a calculadora."""
    e = _empresa(db, empresa_id)
    anexo, origem = anexo_da_empresa(e.anexo_simples, e.cnae, e.atividade)
    extrato = pgdas.da_empresa(db, e.id)
    return {"anexo": anexo, "anexo_origem": origem, "regime_tributario": e.regime_tributario,
            "rbt12": para_json(extrato.rbt12) if extrato else None,
            "rbt12_competencia": extrato.competencia if extrato else None}


@router.post("/nfe")
def ler_nfe(arquivo: UploadFile, db: DB, _: UsuarioAtual, empresa_id: Annotated[int, Form()]):
    """XML de NF-e avulso ou .zip: devolve as linhas com ST e monofásico marcados, para conferir antes de calcular."""
    e = _empresa(db, empresa_id)
    nome = arquivo.filename or "arquivo"
    if not nome.lower().endswith((".xml", ".zip")):
        raise ErroNegocio("Envie um XML de NF-e ou um .zip com XMLs", 415)
    s = get_settings()
    limite = s.nfe_zip_max_mb if nome.lower().endswith(".zip") else s.nfe_xml_max_mb
    notas, erros, canceladas = ler_arquivos(nome, ler_limitado(arquivo, limite))
    validas = [n for n in notas if n.chave_acesso not in canceladas]
    linhas, avisos = servico.linhas_da_nfe(db, e, validas)
    if len(validas) < len(notas):
        avisos.append(f"{len(notas) - len(validas)} nota(s) cancelada(s) no lote ficaram fora do cálculo")
    return {"linhas": para_json(linhas), "avisos": avisos, "erros": erros}


@router.post("")
def calcular(dados: Pedido, db: DB, _: UsuarioAtual):
    hoje = date.today()
    parametros = tabelas.parametros({x.chave: x.valor for x in _vigentes(db, ParametroTributario, hoje)})
    linhas = [motor.LinhaNota(**l.model_dump()) for l in dados.linhas]
    try:
        r = motor.calcular(linhas, dados.rbt12, faixas_vigentes(db, hoje), parametros,
                           dados.folha_12m, dados.receita_12m, dados.aliq_iss_municipio)
    except ValueError as ex:
        raise ErroNegocio(str(ex), 422) from ex
    return para_json(r) | {"aliquota_media": para_json(r.aliquota_media)}
