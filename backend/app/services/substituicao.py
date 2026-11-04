"""Substituição tributária do ICMS por NCM e competência, pela tabela mantida em Base legal."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Norma, RegraSt


@dataclass(frozen=True)
class Regra:
    ncm: str
    excecoes: tuple[str, ...]
    segmento: str
    item: str | None
    inicio: date
    fim: date | None
    revogada_por: str | None

    def abrange(self, ncm: str) -> bool:
        return ncm.startswith(self.ncm) and not any(ncm.startswith(e) for e in self.excecoes)

    def vale_em(self, dia: date) -> bool:
        return self.inicio <= dia and (self.fim is None or dia <= self.fim)


def _dia(competencia: str) -> date:
    ano, mes = competencia.split("-")
    return date(int(ano), int(mes), 1)


class TabelaSt:
    """A ST vale na competência quando o primeiro dia do mês está dentro da vigência da regra."""

    def __init__(self, regras: list[Regra]):
        self.regras = regras
        self._vigente: dict[tuple[str, str], Regra | None] = {}  # (ncm, competência): a mesma consulta se repete por item

    @property
    def vazia(self) -> bool:
        return not self.regras

    def vigente(self, ncm: str, competencia: str) -> Regra | None:
        chave = (ncm, competencia)
        if chave not in self._vigente:
            dia = _dia(competencia)
            self._vigente[chave] = next((r for r in self.regras if r.abrange(ncm) and r.vale_em(dia)), None)
        return self._vigente[chave]

    def encerrada(self, ncm: str, competencia: str) -> Regra | None:
        """A regra que já valeu para o NCM e terminou antes da competência (para avisar notas que ainda destacam ST)."""
        if self.vigente(ncm, competencia):
            return None
        dia = _dia(competencia)
        antigas = [r for r in self.regras if r.abrange(ncm) and r.fim is not None and r.fim < dia]
        return max(antigas, key=lambda r: r.fim, default=None)


def carregar(db: Session, uf: str | None) -> TabelaSt:
    if not uf:
        return TabelaSt([])
    normas = {n.id: n.titulo for n in db.scalars(select(Norma))}
    linhas = db.scalars(select(RegraSt).where(RegraSt.uf == uf)).all()
    # o prefixo mais longo vem primeiro: o código específico decide antes da posição inteira
    linhas = sorted(linhas, key=lambda r: -len(r.ncm))
    return TabelaSt([Regra(r.ncm, tuple(e for e in (r.excecoes or "").split(",") if e), r.segmento, r.item,
                           r.vigencia_inicio, r.vigencia_fim, normas.get(r.revogada_por_id)) for r in linhas])
