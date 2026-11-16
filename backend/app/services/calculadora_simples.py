"""Calculadora do Simples por nota: transforma XML de NF-e em linhas do motor, com ST e monofásico já marcados."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CfopRegra, Empresa, NcmRegra
from app.motor.calculadora_simples import LinhaNota
from app.motor.lei_monofasico import avaliar
from app.seeds import tabelas
from app.services import substituicao
from app.services.nfe_xml import NotaLida
from app.utils.simples import anexo_da_empresa


def anexo_mercadorias(empresa: Empresa) -> str:
    """Nota de produto entra no anexo da empresa quando é I ou II; empresa de serviço vendendo mercadoria, no I."""
    anexo, _ = anexo_da_empresa(empresa.anexo_simples, empresa.cnae, empresa.atividade)
    return anexo if anexo in ("I", "II") else "I"


def linhas_da_nfe(db: Session, empresa: Empresa, notas: list[NotaLida]) -> tuple[list[LinhaNota], list[str]]:
    """(linhas, avisos). Só entram notas de saída emitidas pela empresa e itens com CFOP que gera receita."""
    anexo = anexo_mercadorias(empresa)
    gera_receita = {r.cfop: r.gera_receita for r in db.scalars(select(CfopRegra))}
    st_tabela = substituicao.carregar(db, empresa.uf)
    st_ncm = {r.ncm: r.sujeito_st for r in db.scalars(select(NcmRegra))}
    lei = tabelas.lei_monofasico()
    linhas: list[LinhaNota] = []
    avisos: list[str] = []
    for n in notas:
        if n.tipo_nf != 1 or n.cnpj_emitente != empresa.cnpj:
            avisos.append(f"NF {n.numero}: não é nota de saída emitida pela empresa e ficou fora do cálculo")
            continue
        for i in n.itens:
            if not gera_receita.get(i.cfop, False):
                avisos.append(f"NF {n.numero}, item {i.n_item}: CFOP {i.cfop} não gera receita e ficou fora do cálculo")
                continue
            st = st_ncm.get(i.ncm, False) if st_tabela.vazia else st_tabela.vigente(i.ncm, n.competencia) is not None
            linhas.append(LinhaNota(
                descricao=f"NF {n.numero} · item {i.n_item} · {i.descricao}"[:150],
                valor=i.vl_total,
                anexo=anexo,
                competencia=n.competencia,
                st=st,
                monofasico=avaliar(i.ncm, lei).monofasico_presumido,
            ))
    return linhas, avisos
