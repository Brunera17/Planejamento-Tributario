from typing import Annotated
from urllib.parse import urlsplit

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.contexto import contexto_atual
from app.core.erros import ErroNegocio, NaoEncontrado
from app.core.seguranca import ler_access
from app.db.session import get_db
from app.models import Planejamento, Usuario
from app.services import sessoes

bearer = HTTPBearer(auto_error=False)
DB = Annotated[Session, Depends(get_db)]


def usuario_atual(db: DB, cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> Usuario:
    """JWT válido **e** sessão viva no Redis: logout, troca de senha e desativação valem na hora."""
    if cred is None:
        raise ErroNegocio("Não autenticado", 401)
    try:
        payload = ler_access(cred.credentials)
    except jwt.PyJWTError as e:
        raise ErroNegocio("Sessão inválida ou expirada", 401) from e
    sid, uid = payload["sid"], int(payload["sub"])
    if sessoes.validar(sid, uid) is None:
        raise ErroNegocio("Sessão encerrada; entre novamente", 401)
    # PK: barato, e devolve o modelo de verdade aos serviços (relatório, apresentação) sem objeto solto
    u = db.get(Usuario, uid)
    if u is None or not u.ativo:
        raise ErroNegocio("Usuário inativo", 401)
    ctx = contexto_atual.get()
    if ctx is not None:
        ctx.sessao_id = sid
    return u


def sid_atual(cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str | None:
    """sid do token já validado por usuario_atual (use junto com ele)."""
    if cred is None:
        return None
    try:
        return ler_access(cred.credentials)["sid"]
    except jwt.PyJWTError:
        return None


def somente_contador(u: Annotated[Usuario, Depends(usuario_atual)]) -> Usuario:
    if u.perfil != "CONTADOR":
        raise ErroNegocio("Acesso restrito ao perfil Contador", 403)
    return u


def protecao_csrf(request: Request) -> None:
    """Rotas que usam o cookie de refresh: origem conhecida e cabeçalho que um formulário de outro site não envia."""
    if request.headers.get("x-requested-with") != "planejador":
        raise ErroNegocio("Requisição recusada", 403)
    origem = request.headers.get("origin")
    if origem is None:
        return
    origem = origem.rstrip("/")
    mesma_origem = urlsplit(origem).netloc == request.headers.get("host")  # tela e API no mesmo endereço (proxy)
    if not mesma_origem and origem not in get_settings().origens_permitidas:
        raise ErroNegocio("Origem não permitida", 403)


UsuarioAtual = Annotated[Usuario, Depends(usuario_atual)]
Contador = Annotated[Usuario, Depends(somente_contador)]
SidAtual = Annotated[str | None, Depends(sid_atual)]
ProtecaoCsrf = Depends(protecao_csrf)


def obter_planejamento(db: Session, planejamento_id: int, alterar: bool = False) -> Planejamento:
    """alterar=True: recusa gravar dados num planejamento aprovado (o relatório entregue deixaria de bater)."""
    p = db.get(Planejamento, planejamento_id)
    if p is None:
        raise NaoEncontrado("Planejamento")
    if alterar and p.status == "APROVADO":
        raise ErroNegocio("Planejamento aprovado: o contador precisa reabri-lo (volta para Em coleta) antes de alterar os dados", 409)
    return p
