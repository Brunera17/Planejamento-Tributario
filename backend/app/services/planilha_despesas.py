"""Importação da planilha de despesas que o escritório manda ao cliente (DESPESAS_SIMULACAO_TRIBUTARIA.xlsx).

Formato: uma aba por período; em cada aba, blocos por grupo ("DESPESAS COM VENDAS", "DESPESAS ADMINISTRATIVAS"…) cuja
linha de título traz as datas dos meses nas colunas. Cada linha é uma despesa: número = valor do mês, "N/A" = não houve
(0), vazio = não informado. O mês de cada valor vem da data no título da coluna. A linha é ligada ao catálogo pelas
palavras do nome, dentro do grupo; a que não está no catálogo entra como "outra despesa" do grupo.
"""
from __future__ import annotations

import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import GrupoDespesa, ItemDespesa, Levantamento, LevantamentoItem, OutraDespesa, Planejamento
from app.utils.validacao import sem_acentos

PREFIXO_OUTRA = "Planilha: "  # outras despesas vindas da planilha: trocadas a cada nova importação
PARADA = ("bens proprios", "documentos a serem")  # fim dos blocos de despesa
NAO_HOUVE = {"n/a", "na", "-", "nao", "nao tem", "nao houve", "zero"}
VAZIAS = {"de", "da", "do", "das", "dos", "e", "a", "o", "com", "em", "para"}
APELIDOS = {"percas": "perdas"}  # grafia da planilha do cliente


class PlanilhaInvalida(ValueError):
    pass


@dataclass
class Leitura:
    meses: list[str] = field(default_factory=list)
    valores: dict[tuple[str, int], Decimal] = field(default_factory=dict)  # (competência, item) -> valor
    outras: list[tuple[str, int, str, Decimal]] = field(default_factory=list)  # competência, grupo, descrição, valor
    avisos: list[str] = field(default_factory=list)


def _palavras(texto: str) -> set[str]:
    t = sem_acentos(str(texto)).lower()
    return {APELIDOS.get(w, w) for w in re.findall(r"[a-z0-9]+", t) if w not in VAZIAS}


def _sem_parenteses(texto: str) -> str:
    return re.sub(r"\(.*?\)", " ", texto)


def _melhor(rotulo: str, candidatos: list[tuple[int, str]]) -> int | None:
    """Candidato cujas palavras (sem o parêntese) estão todas no rótulo; o mais específico vence."""
    p = _palavras(rotulo)
    achados = [(len(_palavras(_sem_parenteses(nome))), cid) for cid, nome in candidatos
               if _palavras(_sem_parenteses(nome)) and _palavras(_sem_parenteses(nome)) <= p]
    return max(achados)[1] if achados else None


def _valor(c) -> Decimal | None | str:
    """Decimal, None (vazio) ou o texto, quando a célula não é valor."""
    if c is None or (isinstance(c, str) and not c.strip()):
        return None
    if isinstance(c, bool):
        return str(c)
    if isinstance(c, (int, float)):
        return Decimal(str(round(c, 2)))
    t = sem_acentos(c).strip().lower()
    if t in NAO_HOUVE:
        return Decimal(0)
    num = re.sub(r"^r\$\s*", "", t)
    if re.fullmatch(r"-?[\d.]*\d(,\d{1,2})?", num):
        try:
            return Decimal(num.replace(".", "").replace(",", "."))
        except InvalidOperation:
            pass
    return c.strip()


def _abas(conteudo: bytes) -> list[list[tuple]]:
    from openpyxl import load_workbook

    try:
        livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as e:
        raise PlanilhaInvalida("Não foi possível abrir a planilha (.xlsx)") from e
    return [list(aba.iter_rows(max_row=400, max_col=40, values_only=True)) for aba in livro.worksheets[:24]]


def _ler_aba(linhas: list[tuple], competencias: list[str], grupos: dict[int, str],
             itens: dict[int, list[tuple[int, str]]]) -> Leitura:
    lt = Leitura()
    grupo, colunas = None, {}  # coluna -> competência
    for linha in linhas:
        idx_rotulo = next((j for j, c in enumerate(linha) if isinstance(c, str) and c.strip()), None)
        rotulo = linha[idx_rotulo].strip(" :	") if idx_rotulo is not None else ""
        datas = {j: f"{c:%Y-%m}" for j, c in enumerate(linha) if isinstance(c, (date, datetime))}
        if datas:  # título de bloco: as colunas dos meses
            colunas = {j: comp for j, comp in datas.items() if comp in competencias}
            grupo = _melhor(rotulo, list(grupos.items()))
            continue
        if any(sem_acentos(rotulo).lower().startswith(p) for p in PARADA):
            break
        if not rotulo or not colunas or idx_rotulo in colunas:
            continue
        celulas = {comp: _valor(linha[j]) for j, comp in colunas.items() if j < len(linha)}
        if all(v is None for v in celulas.values()):
            continue
        textos = {comp: v for comp, v in celulas.items() if isinstance(v, str)}
        if textos:
            meses = ", ".join(f"{c[5:]}/{c[:4]}" for c in textos)
            lt.avisos.append(f"{rotulo}: \"{next(iter(textos.values()))[:60]}\" em {meses} não é valor; não importado")
        numeros = {comp: v for comp, v in celulas.items() if isinstance(v, Decimal) and v >= 0}
        if not numeros:
            continue
        if "folha" in _palavras(rotulo):
            if any(numeros.values()):
                lt.avisos.append(f"{rotulo}: informe na aba Faturamento, compras e folha; não importado")
            continue
        item = _melhor(rotulo, itens.get(grupo, [])) if grupo else None
        if item is None and grupo is None:
            item = _melhor(rotulo, [x for xs in itens.values() for x in xs])
        if item is not None:
            for comp, v in numeros.items():
                lt.valores[(comp, item)] = v
        elif grupo is not None:  # "Outras despesas (descrever quais)" ou linha fora do catálogo
            for comp, v in numeros.items():
                if v:
                    lt.outras.append((comp, grupo, (PREFIXO_OUTRA + _sem_parenteses(rotulo).strip(" :"))[:200], v))
        else:
            lt.avisos.append(f"{rotulo}: grupo não identificado; não importado")
    lt.meses = sorted({comp for comp, _ in lt.valores} | {o[0] for o in lt.outras})
    return lt


def ler(db: Session, conteudo: bytes, competencias: list[str]) -> Leitura:
    """Lê a aba que tem mais meses do período do planejamento."""
    grupos = {g.id: g.nome for g in db.scalars(select(GrupoDespesa))}
    itens: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for i in db.scalars(select(ItemDespesa).where(ItemDespesa.ativo.is_(True))):
        itens[i.grupo_id].append((i.id, i.nome))
    leituras = [_ler_aba(linhas, competencias, grupos, itens) for linhas in _abas(conteudo)]
    melhor = max(leituras, key=lambda lt: (len(lt.meses), len(lt.valores)), default=Leitura())
    if not melhor.meses:
        raise PlanilhaInvalida("Nenhum mês do período do planejamento foi encontrado nos títulos da planilha")
    return melhor


def _levantamentos(db: Session, pid: int, meses: list[str]) -> dict[str, Levantamento]:
    return {lv.competencia: lv for lv in db.scalars(select(Levantamento).where(
        Levantamento.planejamento_id == pid, Levantamento.competencia.in_(meses)))}


def previa(db: Session, p: Planejamento, lt: Leitura) -> dict:
    """O que a importação faria: quantos valores, quantos trocam um valor já informado (digitado ou importado antes)
    por outro, e os meses fechados."""
    lvs = _levantamentos(db, p.id, lt.meses)
    fechados = sorted(c for c, lv in lvs.items() if lv.status != "EM_PREENCHIMENTO")
    atuais = {(lv.competencia, li.item_despesa_id): li for lv in lvs.values() for li in db.scalars(
        select(LevantamentoItem).where(LevantamentoItem.levantamento_id == lv.id))}
    substitui = sum(1 for k, v in lt.valores.items() if k[0] not in fechados and k in atuais
                    and not atuais[k].estimado and atuais[k].valor != v)
    return {"meses": [m for m in lt.meses if m not in fechados], "meses_fechados": fechados,
            "valores": sum(1 for k in lt.valores if k[0] not in fechados),
            "outras": sum(1 for o in lt.outras if o[0] not in fechados),
            "total": sum((v for k, v in lt.valores.items() if k[0] not in fechados), Decimal(0))
            + sum((o[3] for o in lt.outras if o[0] not in fechados), Decimal(0)),
            "substitui_digitados": substitui, "avisos": lt.avisos}


def importar(db: Session, p: Planejamento, lt: Leitura, usuario_id: int) -> dict:
    """Grava os valores por mês. A planilha é a fonte: substitui o que estava no item (digitado ou simulado);
    as "outras" vindas de uma importação anterior são trocadas; as digitadas à mão ficam."""
    r = previa(db, p, lt)
    lvs = _levantamentos(db, p.id, r["meses"])
    for comp in r["meses"]:
        lv = lvs.get(comp)
        if lv is None:
            lv = Levantamento(planejamento_id=p.id, competencia=comp, criado_por=usuario_id)
            db.add(lv)
            db.flush()
        atuais = {li.item_despesa_id: li for li in db.scalars(
            select(LevantamentoItem).where(LevantamentoItem.levantamento_id == lv.id))}
        for (c, item), v in lt.valores.items():
            if c != comp:
                continue
            if item in atuais:
                atuais[item].valor, atuais[item].estimado = v, False
            else:
                db.add(LevantamentoItem(levantamento_id=lv.id, item_despesa_id=item, valor=v))
        db.execute(delete(OutraDespesa).where(OutraDespesa.levantamento_id == lv.id,
                                              OutraDespesa.descricao.startswith(PREFIXO_OUTRA)))
        db.add_all(OutraDespesa(levantamento_id=lv.id, grupo_id=g, descricao=d, valor=v)
                   for c, g, d, v in lt.outras if c == comp)
        lv.alterado_em = datetime.now(UTC)
    return r
