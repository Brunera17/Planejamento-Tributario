"""Preparo antes do uvicorn: `pronta` sai com 0 se a versão do código já foi preparada no banco; `marcar` grava
a versão depois do preparo (migrações, cargas e PGDAS-D). No Render grátis a API dorme e acorda num contêiner
novo: sem isso, cada acordada repetia o preparo inteiro (vários segundos de CPU fraca antes de responder).

Versão = RENDER_GIT_COMMIT. Sem ela (docker-compose, testes), nunca está pronta: o preparo roda sempre.
"""
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings

CHAVE = "versao"


def versao() -> str:
    return os.environ.get("RENDER_GIT_COMMIT", "")


def pronta(url: str | None = None) -> bool:
    if not versao():
        return False
    try:
        with create_engine(url or get_settings().database_url).connect() as c:
            marca = c.scalar(text("SELECT valor FROM marca_implantacao WHERE chave = :c"), {"c": CHAVE})
            # sem usuário, a carga ainda precisa criar o primeiro (ADMIN_USUARIO pode ter chegado depois)
            return marca == versao() and c.scalar(text("SELECT 1 FROM usuario LIMIT 1")) is not None
    except Exception:  # banco novo, tabela ainda não criada ou fora do ar: na dúvida, prepara
        return False


def marcar(url: str | None = None) -> None:
    if not versao():
        return
    try:
        with create_engine(url or get_settings().database_url).begin() as c:
            c.execute(text("DELETE FROM marca_implantacao WHERE chave = :c"), {"c": CHAVE})
            c.execute(text("INSERT INTO marca_implantacao (chave, valor) VALUES (:c, :v)"), {"c": CHAVE, "v": versao()})
    except IntegrityError:  # outro contêiner marcou ao mesmo tempo: a marca já está lá
        pass


if __name__ == "__main__":
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    if comando == "pronta":
        ok = pronta()
        print("preparo pulado: versão já preparada" if ok else "preparando esta versão")
        sys.exit(0 if ok else 1)
    if comando == "marcar":
        marcar()
        sys.exit(0)
    sys.exit("uso: python -m app.implantacao pronta|marcar")
