"""Despesas estimadas por referência de mercado da atividade: preenche só o que o cliente ainda não informou."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CfopRegra, ItemDespesa, Levantamento, LevantamentoItem, NotaFiscal, NotaItem, Planejamento
from app.seeds.tabelas import ler

CENTAVO = Decimal("0.01")


def perfil(p: Planejamento) -> dict | None:
    """Perfil pela divisão da CNAE (dois primeiros dígitos); sem perfil, o botão não aparece."""
    digitos = "".join(c for c in (p.empresa.cnae or "") if c.isdigit())
    if len(digitos) < 2:
        return None
    return next((x for x in ler("despesas_referencia.json")["perfis"] if int(digitos[:2]) in x["cnae_divisoes"]), None)


def _faturamento(db: Session, pid: int) -> dict[str, Decimal]:
    return {c: Decimal(str(v or 0)) for c, v in db.execute(
        select(NotaFiscal.competencia, func.sum(NotaItem.vl_total))
        .join(NotaItem, NotaItem.nota_fiscal_id == NotaFiscal.id)
        .where(NotaFiscal.planejamento_id == pid, NotaFiscal.tipo == "SAIDA",
               NotaItem.cfop.in_(select(CfopRegra.cfop).where(CfopRegra.gera_receita)))
        .group_by(NotaFiscal.competencia))}


def previa(db: Session, p: Planejamento, competencia: str | None, zerados: bool = False) -> dict:
    """Por mês aberto (em preenchimento): o que seria preenchido. Item já informado fica de fora; o informado com 0,00
    ("não houve", inclusive por "Zerar despesas do mês") só entra com zerados=True. Valor maior que zero nunca muda."""
    pf = perfil(p)
    if pf is None:
        return {"perfil": None, "meses": []}
    itens = {i.nome: i for i in db.scalars(select(ItemDespesa).where(ItemDespesa.ativo))}
    regras = [(itens[n], Decimal(v), None) for n, v in pf["percentuais"].items() if n in itens] + \
             [(itens[n], None, Decimal(v)) for n, v in pf["fixos"].items() if n in itens]
    levs = {lv.competencia: lv for lv in db.scalars(select(Levantamento).where(Levantamento.planejamento_id == p.id))}
    informados = {(lv_c, i) for lv_c, i, v in db.execute(
        select(Levantamento.competencia, LevantamentoItem.item_despesa_id, LevantamentoItem.valor)
        .join(LevantamentoItem, LevantamentoItem.levantamento_id == Levantamento.id)
        .where(Levantamento.planejamento_id == p.id)) if v or not zerados}
    fat = _faturamento(db, p.id)
    meses = []
    for c in p.competencias():
        if competencia and c != competencia:
            continue
        lv = levs.get(c)
        if lv is not None and lv.status != "EM_PREENCHIMENTO":
            continue  # mês enviado para conferência: só consulta
        linhas = []
        for item, pct, fixo in regras:
            valor = fixo if fixo is not None else (fat.get(c, Decimal(0)) * pct).quantize(CENTAVO, ROUND_HALF_UP)
            linhas.append({"item_despesa_id": item.id, "item": item.nome, "percentual": pct, "fixo": fixo, "valor": valor,
                           "ja_informado": (c, item.id) in informados})
        meses.append({"competencia": c, "faturamento": fat.get(c, Decimal(0)), "itens": linhas,
                      "total": sum((x["valor"] for x in linhas if not x["ja_informado"]), Decimal(0))})
    return {"perfil": {"codigo": pf["codigo"], "nome": pf["nome"], "fonte": pf["fonte"]}, "meses": meses}


def preencher(db: Session, p: Planejamento, competencia: str | None, usuario_id: int, zerados: bool = False) -> dict:
    pv = previa(db, p, competencia, zerados)
    preenchidos, total = 0, Decimal(0)
    for m in pv["meses"]:
        novos = [x for x in m["itens"] if not x["ja_informado"]]
        if not novos:
            continue
        lv = db.scalar(select(Levantamento).where(Levantamento.planejamento_id == p.id, Levantamento.competencia == m["competencia"]))
        if lv is None:
            lv = Levantamento(planejamento_id=p.id, competencia=m["competencia"], criado_por=usuario_id)
            db.add(lv)
            db.flush()
        zerados_do_mes = {li.item_despesa_id: li for li in db.scalars(select(LevantamentoItem).where(
            LevantamentoItem.levantamento_id == lv.id, LevantamentoItem.valor == 0))}
        for x in novos:
            li = zerados_do_mes.get(x["item_despesa_id"])
            if li is not None:
                li.valor, li.estimado = x["valor"], True
            else:
                db.add(LevantamentoItem(levantamento_id=lv.id, item_despesa_id=x["item_despesa_id"], valor=x["valor"], estimado=True))
        preenchidos += len(novos)
        total += sum((x["valor"] for x in novos), Decimal(0))
    return {"meses": [m["competencia"] for m in pv["meses"]], "itens": preenchidos, "total": total,
            "perfil": pv["perfil"] and pv["perfil"]["codigo"]}
