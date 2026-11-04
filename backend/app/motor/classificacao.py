"""Classificação dos itens de NF-e (CFOP, NCM, âmbito) e CSTs sugeridos por regime."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .icms import aliquota_interestadual
from .tipos import Ambito, DestinoDifal, ItemSaida


@dataclass(frozen=True)
class RegraCfop:
    cfop: int
    gera_receita: bool


@dataclass(frozen=True)
class RegraNcm:
    ncm: str
    monofasico: bool
    sujeito_st: bool = False


@dataclass(frozen=True)
class ItemBruto:
    competencia: str
    ncm: str
    cfop: int
    uf_destino: str | None
    valor: Decimal
    ref: str | None = None
    monofasico: bool | None = None  # decisão do contador; vazio segue a regra do NCM
    sujeito_st: bool | None = None  # pela tabela de ST com vigência; vazio segue a regra do NCM
    origem: str | None = None  # origem da mercadoria (orig do ICMS): 1, 2, 3 e 8 vão a 4% para outro estado
    difal: DestinoDifal | None = None  # venda a não contribuinte de outro estado, com a alíquota do destino
    reducao_ibs_cbs: Decimal = Decimal("0")  # redução dos anexos da LC 214/2025


@dataclass
class Classificacao:
    itens: list[ItemSaida] = field(default_factory=list)
    cfops_sem_regra: set[int] = field(default_factory=set)
    ncms_sem_regra: set[str] = field(default_factory=set)

    @property
    def tem_pendencias(self) -> bool:
        return bool(self.cfops_sem_regra or self.ncms_sem_regra)


def ambito_por_cfop(cfop: int) -> Ambito:
    """CFOP 5xxx = operação interna; 6xxx = interestadual; 7xxx = exterior (tratado como interestadual)."""
    return Ambito.INTERNA if str(cfop).startswith("5") else Ambito.INTERESTADUAL


def classificar(
    brutos: list[ItemBruto],
    regras_cfop: dict[int, RegraCfop],
    regras_ncm: dict[str, RegraNcm],
    uf_empresa: str | None = None,
) -> Classificacao:
    """Itens com CFOP sem regra são tratados como 'não gera receita'; NCM sem regra, como 'não monofásico'.

    Ambos viram pendência e bloqueiam a simulação final (a preliminar roda com o aviso).
    """
    out = Classificacao()
    for b in brutos:
        rc = regras_cfop.get(b.cfop)
        if rc is None:
            out.cfops_sem_regra.add(b.cfop)
        rn = regras_ncm.get(b.ncm)
        if rn is None:
            out.ncms_sem_regra.add(b.ncm)
        if uf_empresa and b.uf_destino:
            ambito = Ambito.INTERNA if b.uf_destino == uf_empresa else Ambito.INTERESTADUAL
        else:
            ambito = ambito_por_cfop(b.cfop)
        out.itens.append(ItemSaida(
            competencia=b.competencia,
            ncm=b.ncm,
            cfop=b.cfop,
            ambito=ambito,
            gera_receita=rc.gera_receita if rc else False,
            monofasico=b.monofasico if b.monofasico is not None else (rn.monofasico if rn else False),
            sujeito_st=b.sujeito_st if b.sujeito_st is not None else (rn.sujeito_st if rn else False),
            valor=b.valor,
            ref=b.ref,
            aliq_interestadual=aliquota_interestadual(uf_empresa, b.uf_destino, b.origem) if ambito == Ambito.INTERESTADUAL else None,
            difal=b.difal if ambito == Ambito.INTERESTADUAL else None,
            reducao_ibs_cbs=b.reducao_ibs_cbs,
        ))
    return out


def csts_sugeridos(item: ItemSaida, st_interna: bool) -> dict[str, str]:
    """Matriz por Produto: CSOSN/CST sugeridos em cada regime."""
    if not item.gera_receita:
        return {"csosn_simples": "400", "cst_piscof_simples": "49", "cst_icms_normal": "41", "cst_piscof_normal": "49"}
    return {
        "csosn_simples": "500" if st_interna else "102",
        "cst_piscof_simples": "04" if item.monofasico else "99",
        "cst_icms_normal": "60" if st_interna else "00",
        "cst_piscof_normal": "04" if item.monofasico else "01",
    }
