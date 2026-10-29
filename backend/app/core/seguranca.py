from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from .config import get_settings

ALGORITMO = "HS256"


def gerar_hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def conferir_senha(senha: str, senha_hash: str) -> bool:
    return bcrypt.checkpw(senha.encode(), senha_hash.encode())


def criar_token(usuario_id: int, perfil: str) -> str:
    s = get_settings()
    agora = datetime.now(UTC)
    payload = {"sub": str(usuario_id), "perfil": perfil, "iat": agora,
               "exp": agora + timedelta(minutes=s.jwt_expira_minutos)}
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITMO)


def ler_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITMO])
