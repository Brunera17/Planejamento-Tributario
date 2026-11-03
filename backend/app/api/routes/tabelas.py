"""Tabelas legais: leitura para todos; escrita só para o contador."""
from datetime import UTC, date, datetime
from typing import Literal
from decimal import Decimal

from fastapi import APIRouter
from pydantic import Field, field_validator, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import DB, Contador, UsuarioAtual
from app.core.erros import NaoEncontrado
from app.models import (
    CfopRegra,
    GrupoDespesa,
    ItemDespesa,
    Norma,
    NotaFiscal,
    NotaItem,
    ParametroTributario,
    Planejamento,
    ReformaCronograma,
    ReformaHistorico,
    RegraSt,
    Simulacao,
    SimplesFaixa,
    Usuario,
)
from app.motor.lei_monofasico import avaliar
from app.schemas.comum import Esquema
from app.seeds import tabelas
from app.seeds.tabelas import ler
from app.services import progresso, substituicao
from app.services.simulacao import marcar_desatualizada

router = APIRouter(prefix="/tabelas", tags=["Tabelas legais"])


class ReformaEntrada(Esquema):
    cbs: Decimal = Field(ge=0, le=Decimal("0.5"), description="Alíquota da CBS no ano (0,112 = 11,2%)")
    ibs: Decimal = Field(ge=0, le=Decimal("0.5"))
    fator_icms: Decimal = Field(ge=0, le=1, description="Parcela do ICMS que ainda existe no ano (1 = integral, 0 = extinto)")
    situacao: str | None = Field(default=None, max_length=200)
    fonte: str = Field(min_length=5, max_length=300, description="Norma ou ato que fixou os valores")


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


class NormaEntrada(Esquema):
    titulo: str = Field(min_length=3, max_length=160)
    apelido: str | None = Field(default=None, max_length=80)
    esfera: Literal["FEDERAL", "ESTADUAL", "CONVENIO"]
    uf: str | None = Field(default=None, min_length=2, max_length=2)
    tributos: list[Literal["ICMS", "PIS", "COFINS", "CBS", "IBS"]] = Field(min_length=1)
    resumo: str = Field(min_length=10)
    uso_no_calculo: str | None = None
    url: str = Field(pattern=r"^https?://", max_length=300)
    situacao: Literal["VIGENTE", "ALTERADA", "REVOGADA"] = "VIGENTE"


class RegraStEntrada(Esquema):
    uf: str = Field(default="SP", min_length=2, max_length=2)
    ncm: str
    excecoes: list[str] = []
    cest: str | None = Field(default=None, max_length=9)
    segmento: str = Field(min_length=3, max_length=80)
    item: str | None = Field(default=None, max_length=10)
    descricao: str = Field(min_length=3)
    vigencia_inicio: date = date(2000, 1, 1)
    vigencia_fim: date | None = None
    norma_id: int | None = None
    revogada_por_id: int | None = None

    @field_validator("ncm")
    @classmethod
    def _ncm(cls, v: str) -> str:
        d = "".join(c for c in v if c.isdigit())
        if not 4 <= len(d) <= 8:
            raise ValueError("Informe a posição (4 dígitos), a subposição ou o NCM completo (8 dígitos)")
        return d

    @field_validator("excecoes")
    @classmethod
    def _excecoes(cls, v: list[str]) -> list[str]:
        return [d for d in ("".join(c for c in x if c.isdigit()) for x in v) if d]

    @model_validator(mode="after")
    def _vigencia(self):
        if self.vigencia_fim and self.vigencia_fim < self.vigencia_inicio:
            raise ValueError("O fim da vigência não pode ser antes do início")
        return self


def _reavaliar_planejamentos(db: Session, coluna, valor) -> None:
    """A regra mudou: os planejamentos que usam o código recalculam o progresso e suas simulações ficam desatualizadas."""
    ids = db.scalars(select(NotaFiscal.planejamento_id).join(NotaItem, NotaItem.nota_fiscal_id == NotaFiscal.id)
                     .where(coluna == valor).distinct()).all()
    for pid in ids:
        progresso.atualizar(db, db.get(Planejamento, pid))
        marcar_desatualizada(db, pid)


def _pendentes(db: Session, coluna, regra) -> list[dict]:
    """Códigos usados em notas de saída que ainda não têm regra, com a receita afetada."""
    return [{"codigo": c, "produto_exemplo": d, "valor": v, "planejamentos": n} for c, d, v, n in db.execute(
        select(coluna, func.max(NotaItem.descricao), func.sum(NotaItem.vl_total), func.count(func.distinct(NotaFiscal.planejamento_id)))
        .join(NotaFiscal, NotaFiscal.id == NotaItem.nota_fiscal_id)
        .where(NotaFiscal.tipo == "SAIDA", coluna.not_in(select(regra)))
        .group_by(coluna).order_by(func.sum(NotaItem.vl_total).desc()))]


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
    nomes = {u.id: u.nome for u in db.scalars(select(Usuario))}
    return [{**l, "alterado_por_nome": nomes.get(l["alterado_por"])}
            for l in _linhas(db.scalars(select(ReformaCronograma).order_by(ReformaCronograma.ano)))]


@router.put("/reforma/{ano}")
def alterar_reforma(ano: int, dados: ReformaEntrada, db: DB, u: Contador):
    """A lei muda (resolução do Senado, novo cálculo do TCU): o contador atualiza o ano e informa a fonte.

    O valor anterior vai para o histórico, e todas as simulações ficam desatualizadas: foram calculadas com a alíquota antiga.
    """
    r = db.get(ReformaCronograma, ano)
    if r is None:
        raise NaoEncontrado("Ano do cronograma")
    novos = (dados.cbs, dados.ibs, dados.fator_icms)
    if novos != (r.cbs, r.ibs, r.fator_icms):
        db.add(ReformaHistorico(ano=ano, cbs=r.cbs, ibs=r.ibs, fator_icms=r.fator_icms, fonte=r.fonte,
                                substituido_por_fonte=dados.fonte.strip(), alterado_por=u.id))
        db.execute(update(Simulacao).values(desatualizada=True))
    r.cbs, r.ibs, r.fator_icms = novos
    r.situacao = (dados.situacao or "").strip() or r.situacao
    r.fonte, r.alterado_por, r.alterado_em = dados.fonte.strip(), u.id, datetime.now(UTC)
    db.commit()
    return reforma(db, u)


@router.get("/reforma/historico")
def historico_reforma(db: DB, _: UsuarioAtual):
    nomes = {u.id: u.nome for u in db.scalars(select(Usuario))}
    return [{**l, "alterado_por_nome": nomes.get(l["alterado_por"])}
            for l in _linhas(db.scalars(select(ReformaHistorico).order_by(ReformaHistorico.alterado_em.desc(), ReformaHistorico.ano)))]


@router.get("/cfop")
def cfops(db: DB, _: UsuarioAtual):
    return _linhas(db.scalars(select(CfopRegra).order_by(CfopRegra.cfop)))


@router.put("/cfop")
def salvar_cfop(dados: CfopEntrada, db: DB, _: Contador):
    r = db.get(CfopRegra, dados.cfop) or CfopRegra(cfop=dados.cfop)
    r.natureza, r.gera_receita = dados.natureza, dados.gera_receita
    db.add(r)
    db.flush()
    _reavaliar_planejamentos(db, NotaItem.cfop, dados.cfop)
    db.commit()
    return _linhas([r])[0]


@router.get("/lei-monofasico")
def lei_monofasico(_: UsuarioAtual, ncm: str | None = None):
    """Base legal, somente leitura. Com `ncm`, informa também o enquadramento do código."""
    base = ler("lei_10485.json")
    if ncm:
        a = avaliar(ncm, tabelas.lei_monofasico())
        base = {**base, "consulta": {"ncm": ncm, "enquadramento": a.enquadramento.value, "motivo": a.motivo, "fundamento": a.fundamento}}
    return base


@router.get("/cfop/pendentes")
def cfops_pendentes(db: DB, _: UsuarioAtual):
    return _pendentes(db, NotaItem.cfop, CfopRegra.cfop)


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


@router.get("/normas")
def normas(db: DB, _: UsuarioAtual):
    nomes = {u.id: u.nome for u in db.scalars(select(Usuario))}
    usos = dict(db.execute(select(RegraSt.norma_id, func.count()).group_by(RegraSt.norma_id)).all())
    revogacoes = dict(db.execute(select(RegraSt.revogada_por_id, func.count()).group_by(RegraSt.revogada_por_id)).all())
    return [{**l, "tributos": l["tributos"].split(","), "alterado_por_nome": nomes.get(l["alterado_por"]),
             "regras_st": usos.get(l["id"], 0), "regras_st_encerradas": revogacoes.get(l["id"], 0)}
            for l in _linhas(db.scalars(select(Norma).order_by(Norma.esfera.desc(), Norma.titulo)))]


def _gravar_norma(n: Norma, dados: NormaEntrada, u) -> None:
    for k, v in dados.model_dump().items():
        setattr(n, k, ",".join(v) if k == "tributos" else (v.strip() if isinstance(v, str) else v))
    n.uf = n.uf.upper() if n.uf else None
    n.alterado_por, n.alterado_em = u.id, datetime.now(UTC)


@router.post("/normas", status_code=201)
def incluir_norma(dados: NormaEntrada, db: DB, u: Contador):
    base = "".join(c if c.isalnum() else "-" for c in dados.titulo.lower()).strip("-")[:30]
    codigo, n = base, 1
    while db.scalar(select(Norma.id).where(Norma.codigo == codigo)):
        n += 1
        codigo = f"{base}-{n}"
    norma = Norma(codigo=codigo)
    _gravar_norma(norma, dados, u)
    db.add(norma)
    db.commit()
    return next(x for x in normas(db, u) if x["id"] == norma.id)


@router.put("/normas/{norma_id}")
def alterar_norma(norma_id: int, dados: NormaEntrada, db: DB, u: Contador):
    norma = db.get(Norma, norma_id)
    if norma is None:
        raise NaoEncontrado("Norma")
    _gravar_norma(norma, dados, u)
    db.commit()
    return next(x for x in normas(db, u) if x["id"] == norma.id)


@router.get("/st")
def regras_st(db: DB, _: UsuarioAtual, uf: str = "SP"):
    titulos = {n.id: n.titulo for n in db.scalars(select(Norma))}
    hoje = date.today()
    return [{**l, "excecoes": [e for e in (l["excecoes"] or "").split(",") if e], "norma": titulos.get(l["norma_id"]),
             "revogada_por": titulos.get(l["revogada_por_id"]),
             "vigente_hoje": l["vigencia_inicio"] <= hoje and (l["vigencia_fim"] is None or hoje <= l["vigencia_fim"])}
            for l in _linhas(db.scalars(select(RegraSt).where(RegraSt.uf == uf.upper()).order_by(RegraSt.segmento, RegraSt.ncm)))]


@router.get("/st/consulta")
def consultar_st(ncm: str, competencia: str, db: DB, _: UsuarioAtual, uf: str = "SP"):
    """O NCM estava na ST na competência? E, se não, a ST já valeu e acabou?"""
    ncm = "".join(c for c in ncm if c.isdigit())
    tabela = substituicao.carregar(db, uf.upper())
    r = tabela.vigente(ncm, competencia) or tabela.encerrada(ncm, competencia)
    vigente = tabela.vigente(ncm, competencia) is not None
    return {"ncm": ncm, "competencia": competencia, "sujeito_st": vigente,
            "regra": None if r is None else {"segmento": r.segmento, "item": r.item, "ncm": r.ncm, "fim": r.fim, "revogada_por": r.revogada_por}}


def _gravar_st(r: RegraSt, dados: RegraStEntrada, u) -> None:
    for k, v in dados.model_dump().items():
        setattr(r, k, ",".join(v) or None if k == "excecoes" else v)
    r.uf = r.uf.upper()
    r.alterado_por, r.alterado_em = u.id, datetime.now(UTC)


@router.post("/st", status_code=201)
def incluir_st(dados: RegraStEntrada, db: DB, u: Contador):
    r = RegraSt()
    _gravar_st(r, dados, u)
    db.add(r)
    db.execute(update(Simulacao).values(desatualizada=True))  # a ST muda o ICMS de qualquer planejamento do estado
    db.commit()
    return _linhas([r])[0]


@router.put("/st/{regra_id}")
def alterar_st(regra_id: int, dados: RegraStEntrada, db: DB, u: Contador):
    r = db.get(RegraSt, regra_id)
    if r is None:
        raise NaoEncontrado("Regra de substituição tributária")
    _gravar_st(r, dados, u)
    db.execute(update(Simulacao).values(desatualizada=True))
    db.commit()
    return _linhas([r])[0]
