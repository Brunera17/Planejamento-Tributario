"""Confronta um NCM com os Anexos I e II da Lei 10.485/2002 (autopeças com PIS/COFINS monofásico)."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class Enquadramento(str, Enum):
    MONOFASICO = "MONOFASICO"  # o código está nos anexos, sem ressalva
    CONDICIONAL = "CONDICIONAL"  # depende de Ex tarifário ou da destinação do produto
    NAO_LISTADO = "NAO_LISTADO"  # o código não está nos anexos


@dataclass(frozen=True)
class ItemLei:
    anexo: str
    item: int | None
    codigo: str
    prefixo: str
    ex: tuple[str, ...] = ()
    condicao: str | None = None
    padrao: bool = True  # presunção enquanto o contador não confirma a condição


@dataclass(frozen=True)
class Avaliacao:
    enquadramento: Enquadramento
    monofasico_presumido: bool
    item: ItemLei | None
    motivo: str

    @property
    def fundamento(self) -> str | None:
        if self.item is None:
            return None
        referencia = f"item {self.item.item}" if self.item.item else f"código {self.item.codigo}"
        return f"Lei 10.485/2002, Anexo {self.item.anexo}, {referencia}"


def avaliar(ncm: str, tabela: Iterable[ItemLei]) -> Avaliacao:
    """Vale a entrada mais específica: a lei cita desde posições (87.08) até códigos completos."""
    candidatos = [i for i in tabela if ncm.startswith(i.prefixo)]
    if not candidatos:
        return Avaliacao(Enquadramento.NAO_LISTADO, False, None, "O NCM não consta dos Anexos I e II da Lei 10.485/2002")
    item = max(candidatos, key=lambda i: len(i.prefixo))
    if item.ex:
        return Avaliacao(Enquadramento.CONDICIONAL, item.padrao, item,
                         f"O código {item.codigo} só entra nos Ex {' e '.join(item.ex)}: confirme o Ex na nota do fornecedor")
    if item.condicao:
        return Avaliacao(Enquadramento.CONDICIONAL, item.padrao, item, f"Confirme a condição da lei: {item.condicao}")
    return Avaliacao(Enquadramento.MONOFASICO, True, item, f"Código {item.codigo} do Anexo {item.anexo}")
