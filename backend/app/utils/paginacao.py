"""Paginação das listagens: o corpo continua sendo a lista; a próxima página vem no cabeçalho X-Proximo."""
from typing import Annotated

from fastapi import Query, Response

Limite = Annotated[int, Query(ge=1, le=200)]
Deslocamento = Annotated[int, Query(ge=0)]


def pagina(db, q, limite: int, deslocamento: int, resposta: Response) -> list:
    """Busca uma linha a mais para saber se há próxima página; a consulta precisa de ordem estável (desempate por id)."""
    linhas = db.scalars(q.limit(limite + 1).offset(deslocamento)).unique().all()
    if len(linhas) > limite:
        resposta.headers["X-Proximo"] = str(deslocamento + limite)
    return linhas[:limite]
