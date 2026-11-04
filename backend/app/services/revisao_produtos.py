"""Revisão de produtos: confronta o que foi vendido com a Lei 10.485/2002 e segrega as inconsistências.

A base legal é global; a revisão é do planejamento. Corrigir um NCM aqui vale só para o cálculo: o cadastro
do cliente é corrigido por ele, com a lista exportada.
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CfopRegra, NotaFiscal, NotaItem, Planejamento, RevisaoProduto, Usuario
from app.motor.lei_monofasico import Avaliacao, Enquadramento, avaliar
from app.seeds import tabelas
from app.services.memo import por_planejamento
from app.utils.validacao import sem_acentos

ZERO = Decimal("0")

# tipo -> (rótulo, trava a simulação final?)
TIPOS = {
    "CONDICIONAL": ("Depende de confirmação", True),
    "CODIGO_COM_VARIOS_NCM": ("Mesmo código com NCMs diferentes", True),
    "PRODUTOS_PARECIDOS": ("Produtos parecidos com NCMs diferentes", True),
    "MONOFASICO_SEM_CST04": ("Monofásico vendido sem CST 04", False),
    "CST04_FORA_DA_LEI": ("CST 04 em NCM fora da lei", False),
}
PALAVRAS_IGNORADAS = {"KIT", "PAR", "DOS", "DAS", "COM", "PARA"}


@dataclass
class Produto:
    cod_produto: str  # vazio em notas agregadas por NCM
    ncm_nota: str
    descricao: str
    receita: Decimal = ZERO
    itens: int = 0
    csts: set[str] = field(default_factory=set)
    ncm: str = ""  # NCM usado no cálculo
    avaliacao: Avaliacao | None = None
    monofasico: bool = False
    revisao: RevisaoProduto | None = None
    alertas: list[str] = field(default_factory=list)

    @property
    def revisado(self) -> bool:
        return self.revisao is not None

    @property
    def pendente(self) -> bool:
        return not self.revisado and any(TIPOS[a][1] for a in self.alertas)


def familia(descricao: str) -> str:
    """Duas primeiras palavras relevantes: agrupa 'KIT BUCHA BANDEJA FOX' e 'BUCHA BANDEJA GOL'."""
    palavras = [p for p in re.findall(r"[A-Z]{3,}", sem_acentos(descricao).upper()) if p not in PALAVRAS_IGNORADAS]
    return " ".join(palavras[:2])


@por_planejamento
def analisar(db: Session, p: Planejamento) -> list[Produto]:
    tabela = tabelas.lei_monofasico()
    revisoes = {(r.cod_produto, r.ncm_nota): r for r in db.scalars(select(RevisaoProduto).where(RevisaoProduto.planejamento_id == p.id))}
    linhas = db.execute(
        select(NotaItem.cod_produto, NotaItem.ncm, NotaItem.cst_pis, func.max(NotaItem.descricao), func.sum(NotaItem.vl_total), func.count())
        .join(NotaFiscal, NotaFiscal.id == NotaItem.nota_fiscal_id)
        .where(NotaFiscal.planejamento_id == p.id, NotaFiscal.tipo == "SAIDA",
               NotaItem.cfop.in_(select(CfopRegra.cfop).where(CfopRegra.gera_receita)))
        .group_by(NotaItem.cod_produto, NotaItem.ncm, NotaItem.cst_pis)
    ).all()

    produtos: dict[tuple[str, str], Produto] = {}
    for cod, ncm, cst, desc, valor, n in linhas:
        chave = (cod or "", ncm)
        pr = produtos.setdefault(chave, Produto(cod or "", ncm, desc or ""))
        pr.receita += Decimal(str(valor or 0))
        pr.itens += n
        if cst:
            pr.csts.add(cst)

    lista = sorted(produtos.values(), key=lambda x: x.receita, reverse=True)
    for pr in lista:
        pr.revisao = revisoes.get((pr.cod_produto, pr.ncm_nota))
        pr.ncm = (pr.revisao.ncm_corrigido if pr.revisao and pr.revisao.ncm_corrigido else pr.ncm_nota)
        pr.avaliacao = avaliar(pr.ncm, tabela)
        decidido = pr.revisao.monofasico if pr.revisao else None
        pr.monofasico = pr.avaliacao.monofasico_presumido if decidido is None else decidido

    ncms_do_codigo = defaultdict(set)
    ncms_da_familia = defaultdict(set)
    for pr in lista:
        if pr.cod_produto:  # notas agregadas não têm produto para comparar
            ncms_do_codigo[pr.cod_produto].add(pr.ncm)
            ncms_da_familia[familia(pr.descricao)].add(pr.ncm)

    for pr in lista:
        if pr.avaliacao.enquadramento == Enquadramento.CONDICIONAL:
            pr.alertas.append("CONDICIONAL")
        if pr.cod_produto and len(ncms_do_codigo[pr.cod_produto]) > 1:
            pr.alertas.append("CODIGO_COM_VARIOS_NCM")
        if pr.cod_produto and familia(pr.descricao) and len(ncms_da_familia[familia(pr.descricao)]) > 1:
            pr.alertas.append("PRODUTOS_PARECIDOS")
        if pr.csts:
            if pr.monofasico and "04" not in pr.csts:
                pr.alertas.append("MONOFASICO_SEM_CST04")
            if not pr.monofasico and "04" in pr.csts:
                pr.alertas.append("CST04_FORA_DA_LEI")
    return lista


def resumo(produtos: list[Produto]) -> dict:
    por_tipo = {t: {"rotulo": r, "trava": tr, "produtos": 0, "receita": ZERO} for t, (r, tr) in TIPOS.items()}
    for pr in produtos:
        for a in pr.alertas:
            if not (pr.revisado and TIPOS[a][1]):
                por_tipo[a]["produtos"] += 1
                por_tipo[a]["receita"] += pr.receita
    pendentes = [pr for pr in produtos if pr.pendente]
    return {
        "produtos": len(produtos),
        "pendentes": len(pendentes),
        "revisados": sum(pr.revisado for pr in produtos),
        "receita_pendente": sum((pr.receita for pr in pendentes), ZERO),
        "por_tipo": por_tipo,
    }


def serializar(db: Session, produtos: list[Produto]) -> list[dict]:
    nomes = {u.id: u.nome for u in db.scalars(select(Usuario))}
    saida = []
    for pr in produtos:
        r, a = pr.revisao, pr.avaliacao
        saida.append({
            "id_revisao": r.id if r else None,
            "cod_produto": pr.cod_produto, "descricao": pr.descricao, "ncm_nota": pr.ncm_nota, "ncm": pr.ncm,
            "receita": pr.receita, "itens": pr.itens, "csts": sorted(pr.csts),
            "enquadramento": a.enquadramento.value, "fundamento": a.fundamento, "motivo_lei": a.motivo,
            "condicional": a.enquadramento == Enquadramento.CONDICIONAL,
            "monofasico": pr.monofasico, "pendente": pr.pendente, "revisado": pr.revisado,
            "alertas": [{"tipo": t, "rotulo": TIPOS[t][0], "trava": TIPOS[t][1]} for t in pr.alertas],
            "motivo": r.motivo if r else None, "revisado_por": nomes.get(r.revisado_por) if r else None,
            "revisado_em": r.revisado_em if r else None,
        })
    return saida


def exportar_csv(produtos: list[Produto]) -> str:
    """Lista para o cliente corrigir o cadastro: só os produtos com alerta ou correção."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Código", "Produto", "NCM na nota", "NCM a usar", "CST PIS", "PIS/COFINS", "Receita", "Situação", "Observação"])
    for pr in produtos:
        if not pr.alertas and not (pr.revisao and pr.revisao.ncm_corrigido):
            continue
        w.writerow([pr.cod_produto, pr.descricao, pr.ncm_nota, pr.ncm, "/".join(sorted(pr.csts)), "Monofásico" if pr.monofasico else "Tributado",
                    f"{pr.receita:.2f}".replace(".", ","), "Revisado" if pr.revisado else ("Pendente" if pr.pendente else "Aviso"),
                    "; ".join(TIPOS[a][0] for a in pr.alertas) + (f". {pr.revisao.motivo}" if pr.revisao else "")])
    return buf.getvalue()
