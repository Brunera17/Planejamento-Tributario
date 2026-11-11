"""Senhas (bcrypt), tokens de acesso (JWT curto) e tokens de refresh (opacos)."""
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import bcrypt
import jwt

from .config import get_settings

ALGORITMO = "HS256"
EMISSOR = "planejador-api"
AUDIENCIA = "planejador-web"


def gerar_hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def conferir_senha(senha: str, senha_hash: str) -> bool:
    b = senha.encode()
    if len(b) > 72:  # o bcrypt 5 lança ValueError: vira senha errada (e conta no limite de tentativas)
        bcrypt.checkpw(b[:72], senha_hash.encode())  # mesmo tempo de resposta
        return False
    return bcrypt.checkpw(b, senha_hash.encode())


@lru_cache
def _hash_ficticio() -> str:
    return gerar_hash(secrets.token_urlsafe(16))


def conferir_senha_tempo_constante(senha: str, senha_hash: str | None) -> bool:
    """Sem usuário, roda o bcrypt mesmo assim: o tempo de resposta não revela se o login existe."""
    if senha_hash is None:
        conferir_senha(senha, _hash_ficticio())
        return False
    return conferir_senha(senha, senha_hash)


def _kid(segredo: str) -> str:
    return hashlib.sha256(segredo.encode()).hexdigest()[:8]


def criar_access(usuario_id: int, perfil: str, sid: str) -> tuple[str, datetime]:
    s = get_settings()
    agora = datetime.now(UTC)
    expira = agora + timedelta(minutes=s.access_ttl_min)
    payload = {"sub": str(usuario_id), "perfil": perfil, "sid": sid, "jti": secrets.token_hex(8), "typ": "access",
               "iss": EMISSOR, "aud": AUDIENCIA, "iat": agora, "exp": expira}
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITMO, headers={"kid": _kid(s.jwt_secret)}), expira


def ler_access(token: str) -> dict:
    """Valida assinatura, expiração, emissor, audiência e tipo. Aceita o segredo anterior durante a rotação."""
    s = get_settings()
    segredos = {_kid(x): x for x in (s.jwt_secret, s.jwt_secret_anterior) if x}
    kid = jwt.get_unverified_header(token).get("kid")
    segredo = segredos.get(kid)
    if segredo is None:
        raise jwt.InvalidTokenError("chave desconhecida")
    payload = jwt.decode(token, segredo, algorithms=[ALGORITMO], audience=AUDIENCIA, issuer=EMISSOR,
                         options={"require": ["exp", "iat", "sub", "sid", "typ"]})
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("tipo de token inválido")
    return payload


def gerar_refresh() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh(token: str) -> str:
    """No Redis só fica o hash: um vazamento do Redis não entrega tokens utilizáveis."""
    return hashlib.sha256(token.encode()).hexdigest()
