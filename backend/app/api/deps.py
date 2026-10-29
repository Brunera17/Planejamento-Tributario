from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.erros import ErroNegocio, NaoEncontrado
from app.core.seguranca import ler_token
from app.db.session import get_db
from app.models import Planejamento, Usuario

bearer = HTTPBearer(auto_error=False)
DB = Annotated[Session, Depends(get_db)]


def usuario_atual(db: DB, cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> Usuario:
    if cred is None:
        raise ErroNegocio("Não autenticado", 401)
    try:
        payload = ler_token(cred.credentials)
    except jwt.PyJWTError as e:
        raise ErroNegocio("Sessão inválida ou expirada", 401) from e
    u = db.get(Usuario, int(payload["sub"]))
    if u is None or not u.ativo:
        raise ErroNegocio("Usuário inativo", 401)
    return u


def somente_contador(u: Annotated[Usuario, Depends(usuario_atual)]) -> Usuario:
    if u.perfil != "CONTADOR":
        raise ErroNegocio("Acesso restrito ao perfil Contador", 403)
    return u


UsuarioAtual = Annotated[Usuario, Depends(usuario_atual)]
Contador = Annotated[Usuario, Depends(somente_contador)]


def obter_planejamento(db: Session, planejamento_id: int) -> Planejamento:
    p = db.get(Planejamento, planejamento_id)
    if p is None:
        raise NaoEncontrado("Planejamento")
    return p
