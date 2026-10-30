"""Importação do relatório "Movimentação de Produtos – ICMS – PIS – COFINS" do sistema contábil (Domínio).

O relatório vem em .xls (ou .xlsx) com uma linha por item de nota:
Código | Numero | Data | Produto | CFOP | NCM | Qtde | R$ Unit. | R$ Produto | ICMS (base, alíq., valor, CST) | PIS | COFINS.
A última linha traz os totais. Não há chave de acesso nem UF do destinatário: a nota é identificada por
número + data e o âmbito sai do CFOP (5xxx interna, 6xxx interestadual).

- Saídas viram notas e itens de saída, como na importação de XML.
- Entradas viram notas de entrada; as devoluções de venda (CFOP x202) preenchem as devoluções do mês.
  As compras para revenda são só informadas no resumo: o relatório costuma não cobrir todas as compras.
"""
from __future__ import annotations

import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import CompraMensal, DevolucaoMensal, ImportacaoNfe, NotaFiscal, NotaItem, Planejamento
from app.utils.validacao import sem_acentos

ZERO = Decimal("0")
CFOP_DEVOLUCAO_VENDA = {1201, 1202, 2201, 2202}
CFOP_COMPRA_REVENDA = {1102, 1403, 2102, 2403, 1101, 2101, 3102}
CENTAVO = Decimal("0.01")

# rótulo no cabeçalho -> campo (os blocos de ICMS, PIS e COFINS repetem "R$ Base", "Aliq." e "CST")
COLUNAS = {"CODIGO": "codigo", "NUMERO": "numero", "DATA": "data", "PRODUTO": "produto", "CFOP": "cfop", "NCM": "ncm",
           "QTDE": "qtde", "R$ UNIT.": "unitario", "R$ PRODUTO": "valor", "R$ ICMS": "icms", "R$ PIS": "pis",
           "R$ COFINS": "cofins"}


class RelatorioInvalido(ValueError):
    pass


@dataclass
class LinhaRelatorio:
    numero: str
    data: date
    cod_produto: str
    descricao: str
    cfop: int
    ncm: str
    quantidade: Decimal
    unitario: Decimal
    valor: Decimal
    icms: Decimal
    cst_icms: str
    cst_pis: str | None = None

    @property
    def competencia(self) -> str:
        return f"{self.data:%Y-%m}"


@dataclass
class RelatorioLido:
    tipo: str  # SAIDA, ENTRADA
    periodo: tuple[date, date] | None
    empresa: str | None
    linhas: list[LinhaRelatorio]
    total_rodape: Decimal | None
    avisos: list[str] = field(default_factory=list)


def _dec(v) -> Decimal:
    if v in (None, ""):
        return ZERO
    if isinstance(v, float):
        return Decimal(repr(v))
    return Decimal(str(v).replace(".", "").replace(",", ".")) if isinstance(v, str) and "," in v else Decimal(str(v))


def _texto(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return "" if v is None else str(v).strip()


def _data(v, datemode: int | None) -> date:
    if isinstance(v, float) and datemode is not None:  # data serial do Excel
        import xlrd

        return xlrd.xldate_as_datetime(v, datemode).date()
    if hasattr(v, "date"):
        return v.date()
    d, m, a = _texto(v).split("/")
    return date(int(a), int(m), int(d))


def _ler_celulas(nome: str, conteudo: bytes) -> tuple[list[list], int | None]:
    if nome.lower().endswith(".xls"):
        import xlrd

        try:
            livro = xlrd.open_workbook(file_contents=conteudo)
        except xlrd.XLRDError as e:
            raise RelatorioInvalido(f"Não foi possível ler o .xls: {e}") from e
        aba = livro.sheet_by_index(0)
        return [aba.row_values(r) for r in range(aba.nrows)], livro.datemode
    from openpyxl import load_workbook

    aba = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True).worksheets[0]
    return [list(r) for r in aba.iter_rows(values_only=True)], None


def ler_relatorio(nome: str, conteudo: bytes) -> RelatorioLido:
    linhas, datemode = _ler_celulas(nome, conteudo)
    topo = [_texto(c) for r in linhas[:6] for c in r if _texto(c)]
    titulo = next((t for t in topo if t.startswith("Movimentação de Produtos")), None)
    if titulo is None:
        raise RelatorioInvalido("O arquivo não é o relatório \"Movimentação de Produtos – ICMS – PIS – COFINS\" do sistema contábil")
    tipo = "SAIDA" if any(sem_acentos(t).upper() == "SAIDAS" for t in topo) else \
        "ENTRADA" if any(t.upper() == "ENTRADAS" for t in topo) else None
    if tipo is None:
        raise RelatorioInvalido("Não foi possível identificar se o relatório é de saídas ou de entradas")
    periodo = None
    m = re.search(r"(\d{2}/\d{2}/\d{4}) at[eé] (\d{2}/\d{2}/\d{4})", titulo)
    if m:
        periodo = (_data(m.group(1), None), _data(m.group(2), None))
    empresa = next((t.split(":", 1)[1].strip() for t in topo if t.startswith("Empresa:")), None)

    # cabeçalho: linha que tem "Código" e "Numero"
    idx_cab = next((i for i, r in enumerate(linhas[:15])
                    if {"CODIGO", "NUMERO"} <= {sem_acentos(_texto(c)).upper() for c in r}), None)
    if idx_cab is None:
        raise RelatorioInvalido("Cabeçalho das colunas não encontrado (Código, Numero, Data, Produto…)")
    col: dict[str, int] = {}
    for i, c in enumerate(linhas[idx_cab]):
        rotulo = sem_acentos(_texto(c)).upper()
        if rotulo in COLUNAS and COLUNAS[rotulo] not in col:
            col[COLUNAS[rotulo]] = i
        if rotulo == "CST" and "icms" in col and "cst_icms" not in col:
            col["cst_icms"] = i
        if rotulo == "CST" and "pis" in col and "cst_pis" not in col:
            col["cst_pis"] = i
    faltando = {"numero", "data", "produto", "cfop", "ncm", "valor"} - col.keys()
    if faltando:
        raise RelatorioInvalido("Colunas obrigatórias ausentes: " + ", ".join(sorted(faltando)))

    def cel(r, campo):
        i = col.get(campo)
        return r[i] if i is not None and i < len(r) else None

    itens: list[LinhaRelatorio] = []
    total = None
    for r in linhas[idx_cab + 1:]:
        if _texto(cel(r, "numero")) and _texto(cel(r, "ncm")) and _texto(cel(r, "cfop")):
            produto = _texto(cel(r, "produto"))
            cod, _, desc = produto.partition(" - ")
            itens.append(LinhaRelatorio(
                numero=_texto(cel(r, "numero")), data=_data(cel(r, "data"), datemode),
                cod_produto=cod.strip()[:60], descricao=(desc or produto).strip()[:200],
                cfop=int(float(_texto(cel(r, "cfop")))), ncm=re.sub(r"\D", "", _texto(cel(r, "ncm")))[:8],
                quantidade=_dec(cel(r, "qtde")), unitario=_dec(cel(r, "unitario")), valor=_dec(cel(r, "valor")),
                icms=_dec(cel(r, "icms")), cst_icms=_texto(cel(r, "cst_icms")),
                cst_pis=(_texto(cel(r, "cst_pis")).zfill(2) if _texto(cel(r, "cst_pis")) else None),
            ))
        else:
            numeros = [c for c in r if isinstance(c, (int, float)) and not isinstance(c, bool)]
            if numeros and itens:
                total = _dec(numeros[0])  # rodapé: o primeiro valor é o total de "R$ Produto"
    if not itens:
        raise RelatorioInvalido("Nenhum item encontrado no relatório")

    avisos = []
    soma = sum((i.valor for i in itens), ZERO)
    if total is not None and abs(soma - total) > CENTAVO:
        avisos.append(f"A soma dos itens ({soma:.2f}) difere do total do rodapé ({total:.2f}); confira se o arquivo está completo")
    return RelatorioLido(tipo, periodo, empresa, itens, total, avisos)


@dataclass
class ResumoImportacao:
    tipo: str
    empresa_relatorio: str | None
    linhas: int = 0
    notas_importadas: int = 0
    notas_ignoradas: int = 0
    valor_importado: Decimal = ZERO
    por_competencia: dict[str, dict] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


def importar(db: Session, p: Planejamento, nome: str, conteudo: bytes, usuario_id: int) -> ResumoImportacao:
    rel = ler_relatorio(nome, conteudo)
    resumo = ResumoImportacao(rel.tipo, rel.empresa, linhas=len(rel.linhas), avisos=list(rel.avisos))
    emp = p.empresa
    if rel.empresa:
        nome_rel = sem_acentos(rel.empresa.split(" - ", 1)[-1]).upper()
        if sem_acentos(emp.razao_social).upper()[:20] not in nome_rel and nome_rel[:20] not in sem_acentos(emp.razao_social).upper():
            resumo.avisos.append(f"O relatório é da empresa \"{rel.empresa}\", e o planejamento é de \"{emp.razao_social}\"; confira se é o arquivo certo")

    comps = set(p.competencias())
    fora = sorted({l.competencia for l in rel.linhas} - comps)
    if fora:
        resumo.avisos.append("Itens fora do período do planejamento foram ignorados: " + ", ".join(fora))

    # competências que já têm notas do mesmo tipo de outra origem (XML, carga) seriam duplicadas
    bloqueadas = set(db.scalars(
        select(NotaFiscal.competencia).outerjoin(ImportacaoNfe, ImportacaoNfe.id == NotaFiscal.importacao_id)
        .where(NotaFiscal.planejamento_id == p.id, NotaFiscal.tipo == rel.tipo,
               or_(ImportacaoNfe.id.is_(None), ImportacaoNfe.origem != "RELATORIO"))
        .distinct()))
    for c in sorted(bloqueadas & {l.competencia for l in rel.linhas}):
        resumo.avisos.append(f"{c}: já há notas de {'saída' if rel.tipo == 'SAIDA' else 'entrada'} de outra origem (XML ou carga) "
                             "nesta competência; o relatório não foi importado para não duplicar valores")

    imp = ImportacaoNfe(planejamento_id=p.id, origem="RELATORIO", arquivo=nome, importado_por=usuario_id,
                        lidos=len(rel.linhas), importados=0, ignorados=0)
    db.add(imp)
    db.flush()

    notas: dict[tuple[str, date], list[LinhaRelatorio]] = defaultdict(list)
    for l in rel.linhas:
        if l.competencia in comps and l.competencia not in bloqueadas:
            notas[(l.numero, l.data)].append(l)
    existentes = set(db.scalars(select(NotaFiscal.chave_acesso).where(NotaFiscal.planejamento_id == p.id)))
    prefixo = "DOMS" if rel.tipo == "SAIDA" else "DOME"
    por_comp: dict[str, dict] = defaultdict(lambda: {"notas": 0, "itens": 0, "valor": ZERO, "devolucoes": ZERO, "compras_revenda": ZERO})
    for (numero, dia), itens in sorted(notas.items(), key=lambda x: (x[0][1], x[0][0])):
        chave = f"{prefixo}{dia:%Y%m%d}{numero.zfill(12)}"[:44]
        if chave in existentes:
            resumo.notas_ignoradas += 1
            continue
        nf = NotaFiscal(planejamento_id=p.id, importacao_id=imp.id, chave_acesso=chave, numero=numero[:12], data_emissao=dia,
                        competencia=f"{dia:%Y-%m}", tipo=rel.tipo, uf_emitente=emp.uf if rel.tipo == "SAIDA" else None,
                        uf_destinatario=emp.uf if rel.tipo == "ENTRADA" else None)
        db.add(nf)
        db.flush()
        db.add_all(NotaItem(nota_fiscal_id=nf.id, n_item=n, cod_produto=i.cod_produto, descricao=i.descricao, ncm=i.ncm,
                            cfop=i.cfop, quantidade=i.quantidade, vl_unitario=i.unitario, vl_produtos=i.valor,
                            vl_total=i.valor, vl_icms=i.icms, cst_pis=i.cst_pis) for n, i in enumerate(itens, start=1))
        resumo.notas_importadas += 1
        acc = por_comp[nf.competencia]
        acc["notas"] += 1
        for i in itens:
            acc["itens"] += 1
            acc["valor"] += i.valor
            resumo.valor_importado += i.valor
            if i.cfop in CFOP_DEVOLUCAO_VENDA:
                acc["devolucoes"] += i.valor
            if i.cfop in CFOP_COMPRA_REVENDA:
                acc["compras_revenda"] += i.valor

    if rel.tipo == "ENTRADA":
        _aplicar_entradas(db, p, por_comp, resumo)

    imp.importados, imp.ignorados = resumo.notas_importadas, resumo.notas_ignoradas
    imp.status = "CONCLUIDA"
    imp.log = "\n".join(resumo.avisos) or None
    resumo.por_competencia = {c: {k: (round(v, 2) if isinstance(v, Decimal) else v) for k, v in d.items()}
                              for c, d in sorted(por_comp.items())}
    return resumo


def _aplicar_entradas(db: Session, p: Planejamento, por_comp: dict, resumo: ResumoImportacao) -> None:
    """Devoluções de venda preenchem o mês (se vazio); compras para revenda só são comparadas."""
    for c, acc in sorted(por_comp.items()):
        dev = round(acc["devolucoes"], 2)
        atual = db.scalar(select(DevolucaoMensal).where(DevolucaoMensal.planejamento_id == p.id, DevolucaoMensal.competencia == c))
        if atual is None:
            db.add(DevolucaoMensal(planejamento_id=p.id, competencia=c, valor=dev))
            resumo.avisos.append(f"{c}: devoluções de venda preenchidas com {_brl(dev)} (CFOP 1202/2202 do relatório)")
        elif abs(atual.valor - dev) > CENTAVO:
            resumo.avisos.append(f"{c}: o relatório tem {_brl(dev)} em devoluções de venda e o informado é {_brl(atual.valor)}; "
                                 "o valor informado foi mantido")
        compras = db.scalar(select(CompraMensal.valor).where(CompraMensal.planejamento_id == p.id, CompraMensal.competencia == c))
        revenda = round(acc["compras_revenda"], 2)
        if compras is None:
            resumo.avisos.append(f"{c}: o relatório tem {_brl(revenda)} em compras para revenda; informe as compras do mês "
                                 "(o relatório pode não cobrir todas as notas de compra)")
        elif compras and abs(revenda - compras) / compras > Decimal("0.05"):
            resumo.avisos.append(f"{c}: o relatório tem {_brl(revenda)} em compras para revenda e o informado é {_brl(compras)}; "
                                 "o crédito de ICMS continua estimado pelas compras informadas")


def _brl(v: Decimal) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
