"""Tabelas legais: leitura para todos; escrita só para o contador."""
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import select

from app.api.deps import DB, Contador, UsuarioAtual
from app.core.erros import NaoEncontrado
from app.models import CfopRegra, GrupoDespesa, ItemDespesa, NcmRegra, ParametroTributario, ReformaCronograma, SimplesFaixa
from app.schemas.comum import Esquema

router = APIRouter(prefix="/tabelas", tags=["Tabelas legais"])


class NcmEntrada(Esquema):
    ncm: str = Field(pattern=r"^\d{8}$")
    monofasico: bool
    confianca: str = Field(default="ALTA", pattern="^(ALTA|MEDIA)$")
    sujeito_st: bool = False
    indicio_ncm_incorreto: bool = False
    requer_revisao: bool = False
    acao_recomendada: str | None = None
    cst_ibs_cbs: str | None = Field(default=None, pattern=r"^\d{3}$")
    cclass_trib: str | None = Field(default=None, pattern=r"^\d{6}$")
    beneficio_reforma: str | None = None
    fundamento: str | None = None
    produto_exemplo: str | None = None
    observacao: str | None = None


class CfopEntrada(Esquema):
    cfop: int = Field(ge=1000, le=7999)
    natureza: str
    gera_receita: bool


class ItemDespesaEntrada(Esquema):
    dedutivel_irpj_csll: bool
    credito_pis_cofins: bool
    credito_ibs_cbs: bool
    natureza: str | None = None
    ativo: bool = True


def _linhas(objs) -> list[dict]:
    return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in objs]


@router.get("/simples-faixas")
def simples(db: DB, _: UsuarioAtual):
    return _linhas(db.scalars(select(SimplesFaixa).order_by(SimplesFaixa.anexo, SimplesFaixa.faixa)))


@router.get("/parametros")
def parametros(db: DB, _: UsuarioAtual):
    return _linhas(db.scalars(select(ParametroTributario).order_by(ParametroTributario.chave)))


@router.put("/parametros/{chave}")
def alterar_parametro(chave: str, valor: Decimal, db: DB, _: Contador):
    p = db.scalar(select(ParametroTributario).where(ParametroTributario.chave == chave,
                                                    ParametroTributario.vigencia_fim.is_(None)))
    if p is None:
        raise NaoEncontrado("Parâmetro")
    p.valor = valor
    db.commit()
    return _linhas([p])[0]


@router.get("/reforma")
def reforma(db: DB, _: UsuarioAtual):
    return _linhas(db.scalars(select(ReformaCronograma).order_by(ReformaCronograma.ano)))


@router.get("/cfop")
def cfops(db: DB, _: UsuarioAtual):
    return _linhas(db.scalars(select(CfopRegra).order_by(CfopRegra.cfop)))


@router.put("/cfop")
def salvar_cfop(dados: CfopEntrada, db: DB, _: Contador):
    r = db.get(CfopRegra, dados.cfop) or CfopRegra(cfop=dados.cfop)
    r.natureza, r.gera_receita = dados.natureza, dados.gera_receita
    db.add(r)
    db.commit()
    return _linhas([r])[0]


@router.get("/ncm")
def ncms(db: DB, _: UsuarioAtual):
    return _linhas(db.scalars(select(NcmRegra).order_by(NcmRegra.ncm)))


@router.put("/ncm")
def salvar_ncm(dados: NcmEntrada, db: DB, u: Contador):
    r = db.get(NcmRegra, dados.ncm) or NcmRegra(ncm=dados.ncm)
    for k, v in dados.model_dump().items():
        setattr(r, k, v)
    r.aprovado_por, r.aprovado_em = u.id, datetime.now(UTC)
    db.add(r)
    db.commit()
    return _linhas([r])[0]


@router.get("/catalogo-despesas")
def catalogo(db: DB, _: UsuarioAtual):
    grupos = db.scalars(select(GrupoDespesa).order_by(GrupoDespesa.ordem)).all()
    itens = db.scalars(select(ItemDespesa).order_by(ItemDespesa.ordem)).all()
    return [{"id": g.id, "nome": g.nome, "itens": _linhas(i for i in itens if i.grupo_id == g.id)} for g in grupos]


@router.put("/catalogo-despesas/{item_id}")
def classificar_item(item_id: int, dados: ItemDespesaEntrada, db: DB, _: Contador):
    it = db.get(ItemDespesa, item_id)
    if it is None:
        raise NaoEncontrado("Item de despesa")
    for k, v in dados.model_dump().items():
        setattr(it, k, v)
    db.commit()
    return _linhas([it])[0]
