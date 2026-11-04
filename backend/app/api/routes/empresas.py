import dataclasses

from fastapi import APIRouter, UploadFile
from sqlalchemy import delete, or_, select

from app.api.deps import DB, Contador, UsuarioAtual
from app.core.erros import ErroNegocio, NaoEncontrado
from app.models import Bem, Empresa, Planejamento
from app.schemas.cadastro import EmpresaEntrada, EmpresaSaida
from app.services import importacao_empresas
from app.services.simulacao import marcar_desatualizada
from app.utils.upload import ler_limitado

router = APIRouter(prefix="/empresas", tags=["Empresas"])


@router.get("", response_model=list[EmpresaSaida])
def listar(db: DB, _: UsuarioAtual, busca: str | None = None, ativas: bool = True):
    q = select(Empresa).order_by(Empresa.razao_social)
    if ativas:
        q = q.where(Empresa.ativo)
    if busca:
        q = q.where(or_(Empresa.razao_social.ilike(f"%{busca}%"), Empresa.cnpj.contains(busca)))
    return db.scalars(q).all()


@router.post("", response_model=EmpresaSaida, status_code=201)
def criar(dados: EmpresaEntrada, db: DB, _: Contador):
    if db.scalar(select(Empresa.id).where(Empresa.cnpj == dados.cnpj)):
        raise ErroNegocio("CNPJ já cadastrado", 409, {"cnpj": "já existe"})
    e = Empresa(**dados.model_dump())
    db.add(e)
    db.commit()
    return e


@router.put("/{empresa_id}", response_model=EmpresaSaida)
def editar(empresa_id: int, dados: EmpresaEntrada, db: DB, _: Contador):
    e = db.get(Empresa, empresa_id)
    if e is None:
        raise NaoEncontrado("Empresa")
    if db.scalar(select(Empresa.id).where(Empresa.cnpj == dados.cnpj, Empresa.id != e.id)):
        raise ErroNegocio("CNPJ já cadastrado em outra empresa", 409, {"cnpj": "já existe"})
    muda_calculo = (e.regime_tributario, e.uf, e.anexo_simples) != (dados.regime_tributario, dados.uf, dados.anexo_simples)
    for k, v in dados.model_dump().items():
        setattr(e, k, v)
    if muda_calculo:
        for pid in db.scalars(select(Planejamento.id).where(Planejamento.empresa_id == e.id)):
            marcar_desatualizada(db, pid)
    db.commit()
    return e


@router.post("/{empresa_id}/reativar", response_model=EmpresaSaida)
def reativar(empresa_id: int, db: DB, _: Contador):
    e = db.get(Empresa, empresa_id)
    if e is None:
        raise NaoEncontrado("Empresa")
    e.ativo = True
    db.commit()
    return e


@router.delete("/{empresa_id}", status_code=204)
def excluir(empresa_id: int, db: DB, _: Contador):
    """Empresa com planejamento é apenas inativada."""
    e = db.get(Empresa, empresa_id)
    if e is None:
        raise NaoEncontrado("Empresa")
    if db.scalar(select(Planejamento.id).where(Planejamento.empresa_id == e.id).limit(1)):
        e.ativo = False
    else:
        db.execute(delete(Bem).where(Bem.empresa_id == e.id))
        db.delete(e)
    db.commit()


@router.post("/importacao/previa")
def previa(arquivo: UploadFile, db: DB, _: Contador):
    conteudo = _ler(arquivo)
    try:
        return [dataclasses.asdict(l) for l in importacao_empresas.previa(db, arquivo.filename, conteudo)]
    except importacao_empresas.PlanilhaInvalida as e:
        raise ErroNegocio(str(e), 422) from e


@router.post("/importacao/confirmar")
def confirmar(arquivo: UploadFile, db: DB, u: Contador):
    conteudo = _ler(arquivo)
    try:
        imp = importacao_empresas.confirmar(db, arquivo.filename, conteudo, u.id)
    except importacao_empresas.PlanilhaInvalida as e:
        raise ErroNegocio(str(e), 422) from e
    return {"incluidas": imp.incluidas, "atualizadas": imp.atualizadas, "rejeitadas": imp.rejeitadas}


def _ler(arquivo: UploadFile) -> bytes:
    if not (arquivo.filename or "").lower().endswith((".xlsx", ".xls", ".csv")):
        raise ErroNegocio("Envie um arquivo .xlsx, .xls ou .csv", 415)
    return ler_limitado(arquivo, 10)
