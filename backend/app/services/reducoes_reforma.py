"""Reduções de CBS e IBS por NCM nos anexos da LC 214/2025, pela tabela mantida em Base legal."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RegraReforma


@dataclass(frozen=True)
class Reducao:
    anexo: str
    item: str | None
    descricao: str
    reducao: Decimal
    condicao: str | None
    cst: str
    cclass_trib: str | None

    @property
    def rotulo(self) -> str:
        efeito = "alíquota zero" if self.reducao >= 1 else f"redução de {self.reducao * 100:.0f}%"
        return f"{self.anexo}{f', item {self.item}' if self.item else ''}: {efeito} ({self.descricao})"


class TabelaReducoes:
    def __init__(self, regras: list[RegraReforma]):
        self.regras = regras
        self._por_ncm: dict[str, Reducao | None] = {}  # o mesmo NCM aparece em várias linhas das notas

    def buscar(self, ncm: str) -> Reducao | None:
        """O maior benefício vale quando o NCM está em mais de um anexo (os anexos de 60% ressalvam os de alíquota zero)."""
        if ncm not in self._por_ncm:
            self._por_ncm[ncm] = self._buscar(ncm)
        return self._por_ncm[ncm]

    def _buscar(self, ncm: str) -> Reducao | None:
        achadas = [r for r in self.regras if ncm.startswith(r.ncm) and not any(ncm.startswith(e) for e in (r.excecoes or "").split(",") if e)]
        if not achadas:
            return None
        r = max(achadas, key=lambda x: (x.reducao, len(x.ncm)))
        return Reducao(r.anexo, r.item, r.descricao, Decimal(str(r.reducao)), r.condicao, r.cst, r.cclass_trib)


def carregar(db: Session) -> TabelaReducoes:
    return TabelaReducoes(list(db.scalars(select(RegraReforma).where(RegraReforma.vigencia_fim.is_(None)))))
