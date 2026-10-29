"""Verificação por NCM: receita de cada NCM com a classificação tributária e a ação recomendada."""
from __future__ import annotations

from decimal import Decimal

from .base import ItemCalculado
from .tipos import ZERO, EntradaSimulacao, InfoNcm, LinhaNcm


def verificar_ncms(entrada: EntradaSimulacao, itens: list[ItemCalculado]) -> list[LinhaNcm]:
    """Uma linha por NCM com receita no período, da maior para a menor receita."""
    receita: dict[str, Decimal] = {}
    exemplo: dict[str, ItemCalculado] = {}
    for it in itens:
        if not it.item.gera_receita:
            continue
        receita[it.item.ncm] = receita.get(it.item.ncm, ZERO) + it.receita_liquida
        exemplo.setdefault(it.item.ncm, it)
    total = sum(receita.values(), ZERO)
    linhas = []
    for ncm, valor in sorted(receita.items(), key=lambda x: x[1], reverse=True):
        info = entrada.ncm_info.get(ncm)
        sem_regra = info is None
        info = info or InfoNcm(confianca=None, requer_revisao=True, acao_recomendada="NCM sem regra cadastrada: classificar antes da simulação final.")
        it = exemplo[ncm].item
        linhas.append(LinhaNcm(
            ncm=ncm,
            receita=valor,
            participacao=ZERO if total == 0 else valor / total,
            monofasico=it.monofasico,
            sujeito_st=it.sujeito_st,
            sem_regra=sem_regra,
            produto_exemplo=info.produto_exemplo,
            confianca=info.confianca,
            indicio_ncm_incorreto=info.indicio_ncm_incorreto,
            requer_revisao=info.requer_revisao,
            acao_recomendada=info.acao_recomendada,
            cst_ibs_cbs=info.cst_ibs_cbs,
            cclass_trib=info.cclass_trib,
            beneficio_reforma=info.beneficio_reforma,
        ))
    return linhas
