"""Premissas tiradas das notas importadas.

Valem só enquanto o contador não informar o valor: a ordem é informado > notas > padrão do motor.
O que não sai das notas nem foi informado vira pendência (bloco "Premissas" do progresso).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import CompraMensal, CompraOrigem, NotaFiscal, NotaItem, ParametroTributario, Planejamento, PremissaPlanejamento
from app.services import pgdas, substituicao
from app.services.relatorio_contabil import CFOP_COMPRA_REVENDA
from app.services.memo import por_planejamento

ZERO = Decimal("0")
UM = Decimal("1")

# rótulos das pendências, na ordem da tela de Premissas
ROTULOS = {
    "composicao_compras": "Origem das compras",
    "rbt12_informado": "Receita bruta dos últimos 12 meses (RBT12)",
    "estoque_inicial": "Estoque inicial do período (0,00 se não houver)",
    "estoque_final": "Estoque final do período (0,00 se não houver)",
    "adicoes_lr": "Adições ao lucro real (0,00 se não houver)",
    "exclusoes_lr": "Exclusões do lucro real (0,00 se não houver)",
    "prejuizo_fiscal_compensar": "Prejuízo fiscal a compensar (0,00 se não houver)",
    "aplicar_st_vendas_internas": "Vendas internas com ICMS-ST",
    "excluir_icms_base_pis_cofins": "Excluir o ICMS da base do PIS/COFINS",
    "credito_frete_integral": "Crédito de PIS/COFINS sobre fretes",
    "pct_compras_credito_ibs_cbs": "Compras com crédito de IBS/CBS",
    "vendas_b2c": "Vendas para consumidor final",
}

SUL_SUDESTE = {"PR", "SC", "RS", "SP", "RJ", "MG"}  # o ES fica de fora (Resolução do Senado 22/1989)
ORIGEM_IMPORTADA = {"1", "2", "3", "8"}  # Resolução do Senado 13/2012: 4% na operação interestadual
CST_ST = {"10", "30", "60", "70"}
CSOSN_ST = {"201", "202", "203", "500"}
CRT_NORMAL = {"2", "3"}
ALIQUOTAS_INTERESTADUAIS = {Decimal("0.04"), Decimal("0.07"), Decimal("0.12")}


@dataclass
class Derivada:
    valor: Decimal | bool
    fonte: str


@dataclass
class Automaticas:
    premissas: dict[str, Derivada] = field(default_factory=dict)
    composicao: dict[Decimal, Decimal] | None = None
    fonte_composicao: str | None = None
    indicio_st: str | None = None  # NCM da base de ST sem CST na nota que confirme


def eh_st(cst: str | None) -> bool | None:
    """CST/CSOSN de ICMS indica substituição tributária? None quando a nota não traz o código.

    O XML separa origem e CST; o relatório do Domínio às vezes junta os dois ("060").
    """
    if not cst:
        return None
    return cst in CST_ST or cst in CSOSN_ST or (len(cst) == 3 and cst not in CSOSN_ST | {"101", "102", "103", "300", "400", "900"}
                                                and cst[1:] in CST_ST)


def _brl(v: Decimal) -> str:
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _fmt_ncms(ncms: list[str]) -> str:
    texto = ", ".join(f"{n[:4]}.{n[4:6]}.{n[6:]}" for n in ncms[:3])
    return texto + ("…" if len(ncms) > 3 else "")


def _pct(v: Decimal) -> str:
    return f"{v * 100:.1f}%".replace(".", ",")


def aliquota_interna(db: Session, p: Planejamento) -> Decimal:
    ref = date.fromisoformat(p.competencia_inicial + "-01")
    v = db.scalar(select(ParametroTributario.valor).where(
        ParametroTributario.chave == "aliq_icms_interna", ParametroTributario.vigencia_inicio <= ref,
        or_(ParametroTributario.vigencia_fim.is_(None), ParametroTributario.vigencia_fim >= ref)))
    return Decimal(str(v)) if v is not None else Decimal("0.18")


def aliquota_da_compra(uf_empresa: str, interna: Decimal, uf_emitente: str, orig: str | None, aliq: Decimal | None) -> Decimal:
    """Alíquota do crédito de uma compra: a destacada na nota quando é interestadual; senão, a regra da origem."""
    if uf_emitente == uf_empresa:
        return interna
    if aliq is not None and aliq.quantize(Decimal("0.01")) in ALIQUOTAS_INTERESTADUAIS:
        return aliq.quantize(Decimal("0.01"))
    if orig in ORIGEM_IMPORTADA:
        return Decimal("0.04")
    if uf_emitente in SUL_SUDESTE and uf_empresa not in SUL_SUDESTE:
        return Decimal("0.07")
    return Decimal("0.12")


def _fechar_em_cem(partes: dict[Decimal, Decimal]) -> dict[Decimal, Decimal]:
    total = sum(partes.values(), ZERO)
    out = {a: (v / total).quantize(Decimal("0.0001"), ROUND_HALF_UP) for a, v in partes.items() if v > 0}
    maior = max(out, key=out.get)
    out[maior] += UM - sum(out.values(), ZERO)  # o arredondamento não pode deixar a soma fora de 100%
    return out


@por_planejamento
def derivar(db: Session, p: Planejamento) -> Automaticas:
    uf = p.empresa.uf
    out = Automaticas()
    comps = p.competencias()

    # ---- extrato do PGDAS-D enviado em Documentos: RBT12 declarado
    extrato = pgdas.do_planejamento(db, p)
    if extrato:
        pa = f"{extrato.competencia[5:]}/{extrato.competencia[:4]}" if extrato.competencia else "período não identificado"
        out.premissas["rbt12_informado"] = Derivada(extrato.rbt12, f"extrato do PGDAS-D de {pa} ({extrato.arquivo}): RBT12 de {_brl(extrato.rbt12)}")

    # ---- entradas (XML): origem das compras e regime dos fornecedores
    entradas = db.execute(
        select(NotaFiscal.id, NotaFiscal.uf_emitente, NotaFiscal.crt_emitente, NotaItem.orig_icms, NotaItem.aliq_icms, NotaItem.vl_total)
        .join(NotaItem, NotaItem.nota_fiscal_id == NotaFiscal.id)
        .where(NotaFiscal.planejamento_id == p.id, NotaFiscal.tipo == "ENTRADA", NotaFiscal.competencia.in_(comps),
               NotaFiscal.uf_emitente.is_not(None), NotaItem.cfop.in_(CFOP_COMPRA_REVENDA))
    ).all()
    if entradas:
        interna = aliquota_interna(db, p)
        partes: dict[Decimal, Decimal] = {}
        for _, uf_emit, _, orig, aliq, v in entradas:
            a = aliquota_da_compra(uf, interna, uf_emit, orig, aliq)
            partes[a] = partes.get(a, ZERO) + Decimal(str(v))
        valor = sum(partes.values(), ZERO)
        if valor > 0:
            out.composicao = _fechar_em_cem(partes)
            compras = sum((c.valor for c in db.scalars(select(CompraMensal).where(CompraMensal.planejamento_id == p.id))), ZERO)
            notas = len({e[0] for e in entradas})
            cobertura = f", {_pct(valor / compras)} das compras informadas" if compras else ""
            out.fonte_composicao = f"{notas} {'nota' if notas == 1 else 'notas'} de compra, {_brl(valor)}{cobertura}"

        com_crt = [(crt, Decimal(str(v))) for _, _, crt, _, _, v in entradas if crt]
        total = sum((v for _, v in com_crt), ZERO)
        if total > 0:
            normal = sum((v for crt, v in com_crt if crt in CRT_NORMAL), ZERO) / total
            out.premissas["pct_compras_credito_ibs_cbs"] = Derivada(
                normal.quantize(Decimal("0.0001"), ROUND_HALF_UP),
                f"{_pct(normal)} das compras nas notas vêm de fornecedores fora do Simples Nacional")

    # ---- saídas: ICMS-ST pelo NCM e pelo CST, e venda a consumidor final
    saidas = db.execute(
        select(NotaItem.ncm, NotaItem.cfop, NotaItem.cst_icms, NotaItem.vl_total, NotaFiscal.uf_destinatario, NotaFiscal.consumidor_final,
               NotaFiscal.competencia)
        .join(NotaFiscal, NotaItem.nota_fiscal_id == NotaFiscal.id)
        .where(NotaFiscal.planejamento_id == p.id, NotaFiscal.tipo == "SAIDA", NotaFiscal.competencia.in_(comps))
    ).all()
    internas = [s for s in saidas if (s.uf_destinatario == uf if s.uf_destinatario else str(s.cfop).startswith("5"))]
    if internas:
        # A nota decide: CST/CSOSN de ST na venda prova a ST no período. A tabela de ST da Base legal tem vigência
        # por NCM: aponta o indício quando a nota não traz o CST e avisa a nota que destaca ST depois que ela acabou.
        tabela = substituicao.carregar(db, uf)
        total = sum((Decimal(str(s.vl_total)) for s in internas), ZERO)
        com_st = [s for s in internas if eh_st(s.cst_icms)]
        sem_cst = [s for s in internas if eh_st(s.cst_icms) is None]
        avisos = []
        if com_st:
            valor_st = sum((Decimal(str(s.vl_total)) for s in com_st), ZERO)
            ncms = sorted({s.ncm for s in com_st})
            out.premissas["aplicar_st_vendas_internas"] = Derivada(
                True, f"{len(ncms)} NCM vendidos no estado saíram com CST de substituição tributária ({_fmt_ncms(ncms)}): "
                      f"{_brl(valor_st)}, {_pct(valor_st / total)} das vendas internas")
            encerradas = {}
            for s in com_st:
                r = tabela.encerrada(s.ncm, s.competencia)
                if r:
                    encerradas.setdefault((r.fim, r.revogada_por), set()).add(s.ncm)
            for (fim, norma), ncms_fim in sorted(encerradas.items(), key=lambda x: x[0][0]):
                avisos.append(f"{len(ncms_fim)} NCM saíram com CST de ST depois do fim da ST em {fim:%d/%m/%Y}"
                              f"{f' ({norma})' if norma else ''}: {_fmt_ncms(sorted(ncms_fim))}. Confira o cadastro fiscal desses produtos.")
        elif not sem_cst and total > 0:
            out.premissas["aplicar_st_vendas_internas"] = Derivada(False, "Nenhuma venda no estado saiu com CST de substituição tributária")
        else:
            ncms = sorted({s.ncm for s in sem_cst if tabela.vigente(s.ncm, s.competencia)})
            if ncms:
                avisos.append(f"{len(ncms)} NCM vendidos no estado estavam na substituição tributária no período ({_fmt_ncms(ncms)}), "
                              "mas as notas não trazem o CST. Confirme se a venda saiu com ST.")
        out.indicio_st = " ".join(avisos) or None

    com_ind = [(s.consumidor_final, Decimal(str(s.vl_total))) for s in saidas if s.consumidor_final is not None]
    total = sum((v for _, v in com_ind), ZERO)
    if total > 0:
        b2c = sum((v for cf, v in com_ind if cf), ZERO) / total
        out.premissas["vendas_b2c"] = Derivada(b2c >= Decimal("0.5"), f"{_pct(b2c)} das vendas nas notas são para consumidor final")
    return out


def informadas(db: Session, p: Planejamento) -> set[str]:
    chaves = {pr.chave for pr in db.scalars(select(PremissaPlanejamento).where(PremissaPlanejamento.planejamento_id == p.id))
              if json.loads(pr.valor) is not None}
    if db.scalar(select(CompraOrigem.id).where(CompraOrigem.planejamento_id == p.id).limit(1)) is not None:
        chaves.add("composicao_compras")
    return chaves


def faltantes(db: Session, p: Planejamento) -> list[str]:
    """Premissas sem valor informado e sem valor nas notas, na ordem da tela."""
    preenchidas = informadas(db, p)
    auto = derivar(db, p)
    if auto.composicao:
        preenchidas.add("composicao_compras")
    preenchidas |= set(auto.premissas)
    return [k for k in ROTULOS if k not in preenchidas]
