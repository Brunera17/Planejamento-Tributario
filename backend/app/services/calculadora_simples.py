"""Calculadora do Simples por nota: transforma XML de NF-e em linhas do motor, com ST e monofásico já marcados.

As notas de venda (emitidas pela empresa) viram as linhas do cálculo. As notas de compra (a empresa é a destinatária) são
opcionais e só melhoram a marcação: o ST de cada produto passa a seguir o que o fornecedor cobrou, e o CST de PIS do
fornecedor confere o monofásico da lei.
"""
from __future__ import annotations

import collections
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CfopRegra, Empresa
from app.motor.calculadora_simples import LinhaNota
from app.motor.lei_monofasico import avaliar
from app.seeds import tabelas
from app.services.nfe_xml import ItemLido, NotaLida
from app.utils.simples import anexo_da_empresa

# ICMS-ST retido pelo fornecedor (CST 10, 30, 70; CSOSN 201 a 203) ou cobrado em etapa anterior (CST 60; CSOSN 500)
CST_COM_ST = {"10", "30", "60", "70", "201", "202", "203", "500"}
VENDA_COM_ST = {"60", "500"}  # na nota de venda: ST já recolhido, o ICMS sai do DAS
CFOP_LANCAMENTO_DE_CUPOM = {5929, 6929}  # NF-e que só lança operação já registrada em NFC-e ou cupom fiscal
SEM_COMPRAS = ("As notas de compra são opcionais, mas melhoram o cálculo: com elas o ST de cada produto segue o que o fornecedor "
               "cobrou e o monofásico é conferido pelo CST de PIS da compra. Sem elas, o ST segue o CSOSN das notas de venda.")
SEM_CANCELAMENTOS = ("Nenhum evento de cancelamento no envio. Se houve nota cancelada no mês, envie também os XML de evento "
                     "(costumam ficar numa pasta CANCELADAS): sem eles, a nota cancelada entra como venda. Use \"Escolher pasta\" "
                     "para mandar a pasta inteira, com as subpastas.")


@dataclass
class Leitura:
    linhas: list[LinhaNota] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    vendas: int = 0
    compras: int = 0


def anexo_mercadorias(empresa: Empresa) -> str:
    """Nota de produto entra no anexo da empresa quando é I ou II; empresa de serviço vendendo mercadoria, no I."""
    anexo, _ = anexo_da_empresa(empresa.anexo_simples, empresa.cnae, empresa.atividade)
    return anexo if anexo in ("I", "II") else "I"


def _brl(v: Decimal) -> str:
    return f"R$ {v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")  # sem quebra após o R$


def _compra_com_st(i: ItemLido) -> bool:
    return bool(i.vl_icms_st) or (i.cst_icms or "") in CST_COM_ST


def linhas_da_nfe(db: Session, empresa: Empresa, notas: list[NotaLida]) -> Leitura:
    """Vendas da empresa viram linhas (só itens com CFOP que gera receita); compras, se vierem, conferem ST e monofásico."""
    anexo = anexo_mercadorias(empresa)
    gera_receita = {r.cfop: r.gera_receita for r in db.scalars(select(CfopRegra))}
    lei = tabelas.lei_monofasico()
    out = Leitura()

    vendas = [n for n in notas if n.tipo_nf == 1 and n.cnpj_emitente == empresa.cnpj]
    compras = [n for n in notas if n.cnpj_destinatario == empresa.cnpj and n.cnpj_emitente != empresa.cnpj]
    usadas = {id(n) for n in vendas} | {id(n) for n in compras}
    for n in notas:
        if id(n) not in usadas:
            out.avisos.append(f"NF {n.numero}: não é venda nem compra da empresa e ficou fora do cálculo")
    out.vendas, out.compras = len(vendas), len(compras)

    st_compra: dict[str, set[bool]] = defaultdict(set)
    cst_pis_compra: dict[str, set[str]] = defaultdict(set)
    for n in compras:
        for i in n.itens:
            st_compra[i.ncm].add(_compra_com_st(i))
            if i.cst_pis:
                cst_pis_compra[i.ncm].add(i.cst_pis)

    divergencias: dict[str, dict] = {}  # por NCM, para avisar uma vez só
    for n in vendas:
        if any(i.cfop in CFOP_LANCAMENTO_DE_CUPOM for i in n.itens):
            # a nota só lança vendas já registradas em NFC-e/cupom; um item de venda nela contaria a receita duas vezes
            vendas_na_nota = sum((i.vl_total for i in n.itens if i.cfop not in CFOP_LANCAMENTO_DE_CUPOM and gera_receita.get(i.cfop)),
                                 Decimal(0))
            out.avisos.append(f"NF {n.numero}: lançamento de vendas já registradas em NFC-e (CFOP 5929/6929) e ficou fora do cálculo"
                              + (f"; ela tem itens com CFOP de venda ({_brl(vendas_na_nota)}): se forem vendas novas, inclua o "
                                 "valor à mão" if vendas_na_nota else ""))
            continue
        fora = collections.Counter(i.cfop for i in n.itens if not gera_receita.get(i.cfop, False))
        if fora:
            out.avisos.append(f"NF {n.numero}: " + ", ".join(f"{q} {'item' if q == 1 else 'itens'} com CFOP {c}" for c, q in fora.items())
                              + " não geram receita e ficaram fora do cálculo")
        for i in n.itens:
            if not gera_receita.get(i.cfop, False):
                continue
            na_venda = (i.cst_icms or "") in VENDA_COM_ST
            # o ST segue o que o fornecedor cobrou quando há compra do produto; sem compra, o padrão da nota de venda (CSOSN)
            st = (True in st_compra[i.ncm]) if i.ncm in st_compra else na_venda
            mono = avaliar(i.ncm, lei).monofasico_presumido
            if st != na_venda:
                d = divergencias.setdefault(i.ncm, {"st": st, "desc": i.descricao, "valor": 0})
                d["valor"] += i.vl_total
            out.linhas.append(LinhaNota(
                descricao=f"NF {n.numero}, item {i.n_item}: {i.descricao}"[:150],
                valor=i.vl_total,
                anexo=anexo,
                competencia=n.competencia,
                st=st,
                monofasico=mono,
            ))

    for ncm, d in divergencias.items():
        valor = _brl(d["valor"])
        if d["st"]:
            out.avisos.append(f"NCM {ncm} ({d['desc'][:40]}): vendido sem ST, mas a compra veio com ST cobrado. O cálculo tira o ICMS "
                              f"do DAS; confira o CSOSN das vendas ({valor})")
        else:
            out.avisos.append(f"NCM {ncm} ({d['desc'][:40]}): vendido como ST, mas a compra veio sem ST. O cálculo mantém o ICMS "
                              f"no DAS; confira o CSOSN das vendas ({valor})")
    vendidos = {i.ncm: i.descricao for n in vendas for i in n.itens}
    for ncm, csts in cst_pis_compra.items():
        if ncm not in vendidos:
            continue
        lei_mono = avaliar(ncm, lei).monofasico_presumido
        if "04" in csts and not lei_mono:
            out.avisos.append(f"NCM {ncm} ({vendidos[ncm][:40]}): o fornecedor informou monofásico (CST 04), mas o NCM não está nas leis "
                              "do monofásico. O cálculo tributa PIS e COFINS; confira o NCM do produto")
        elif lei_mono and csts == {"01"}:  # 02 e 03 também são monofásico (no fabricante); 01 é tributação normal
            out.avisos.append(f"NCM {ncm} ({vendidos[ncm][:40]}): está na lei do monofásico, mas o fornecedor tributou PIS e COFINS "
                              f"(CST {', '.join(sorted(csts))}). O cálculo segue a lei; confira o produto")
    if vendas and not compras:
        out.info.append(SEM_COMPRAS)
    return out
