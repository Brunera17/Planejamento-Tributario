"""Calculadora do Simples Nacional por nota: DAS aproximado sem abrir planejamento. Nada é gravado."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import Field
from starlette.datastructures import UploadFile as StarletteUploadFile

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
from app.services.nfe_xml import NotaLida, ler_arquivos
from app.services.nfse_xml import ServicoLido
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
async def ler_nfe(request: Request, db: DB, _: UsuarioAtual):
    """Notas do mês de uma vez (XML avulsos ou .zip), em "arquivos": as vendas da empresa viram linhas para conferir antes de
    calcular; as compras, opcionais, conferem o ST e o monofásico. Os eventos de cancelamento valem para o lote todo."""
    s = get_settings()
    # o padrão do Starlette é 1.000 arquivos por envio; um mês de NFC-e de uma farmácia passa disso
    form = await request.form(max_files=s.nfe_zip_max_arquivos, max_fields=50)
    arquivos = [a for a in form.getlist("arquivos") if isinstance(a, StarletteUploadFile)]
    if not arquivos:
        raise ErroNegocio("Envie ao menos um XML de NF-e ou um .zip com XMLs", 422, {"arquivos": "obrigatório"})
    try:
        empresa_id = int(str(form.get("empresa_id")))
    except ValueError as ex:
        raise ErroNegocio("Empresa inválida", 422, {"empresa_id": "inválido"}) from ex
    return await run_in_threadpool(_ler_nfe, db, empresa_id, arquivos)


def _ler_nfe(db, empresa_id: int, arquivos: list[StarletteUploadFile]) -> dict:
    e = _empresa(db, empresa_id)
    s = get_settings()
    notas: dict[str, object] = {}
    servicos: dict[str, ServicoLido] = {}
    erros: list[str] = []
    canceladas: set[str] = set()
    for arquivo in arquivos:
        nome = arquivo.filename or "arquivo"
        if not nome.lower().endswith((".xml", ".zip")):
            erros.append(f"{nome}: envie XML de NF-e ou NFS-e, ou .zip (RAR não é lido)")
            continue
        limite = s.nfe_zip_max_mb if nome.lower().endswith(".zip") else s.nfe_xml_max_mb
        lidas, erros_arquivo, cancel = ler_arquivos(nome, ler_limitado(arquivo, limite))
        # o mesmo XML repetido conta uma vez
        notas.update({n.chave_acesso: n for n in lidas if isinstance(n, NotaLida)})
        servicos.update({n.chave: n for n in lidas if isinstance(n, ServicoLido)})
        erros += erros_arquivo
        canceladas |= cancel
    validas = [n for k, n in notas.items() if k not in canceladas]
    leitura = servico.linhas_da_nfe(db, e, validas)
    canceladas_nfse = [n for n in servicos.values() if n.cancelada]
    servico.linhas_da_nfse(e, [n for n in servicos.values() if not n.cancelada], leitura)
    if canceladas_nfse:
        leitura.avisos.append(f"{len(canceladas_nfse)} NFS-e cancelada(s) ficaram fora do cálculo")
    if len(validas) < len(notas):
        leitura.avisos.append(f"{len(notas) - len(validas)} nota(s) cancelada(s) ficaram fora do cálculo")
    elif leitura.vendas and not canceladas:
        # a nota cancelada é idêntica a uma válida: só o XML do evento de cancelamento diz que ela não vale
        leitura.info.append(servico.SEM_CANCELAMENTOS)
    return {"linhas": para_json(leitura.linhas), "avisos": leitura.avisos, "info": leitura.info, "erros": erros,
            "vendas": leitura.vendas, "compras": leitura.compras, "servicos": leitura.servicos}


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
