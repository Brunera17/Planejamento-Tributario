"""Limite de tentativas de login por usuário e por IP, numa janela móvel do primeiro erro."""
from __future__ import annotations

from app.core import redis as redis_cliente
from app.core.config import get_settings
from app.core.erros import ErroNegocio


def _chaves(login: str, ip: str | None) -> list[tuple[str, int]]:
    s = get_settings()
    chaves = [(f"login_falhas:usuario:{login.strip().lower()[:60]}", s.login_max_falhas_usuario)]
    if ip:
        chaves.append((f"login_falhas:ip:{ip}", s.login_max_falhas_ip))
    return chaves


def bloqueio(login: str, ip: str | None) -> int | None:
    """Segundos até liberar, se o login ou o IP passou do limite; senão None."""
    def ler(r):
        p = r.pipeline()
        for k, _ in _chaves(login, ip):
            p.get(k)
            p.ttl(k)
        return p.execute()

    valores = redis_cliente.executar(ler)
    espera = None
    for i, (_, limite) in enumerate(_chaves(login, ip)):
        n, ttl = valores[2 * i], valores[2 * i + 1]
        if n is not None and int(n) >= limite:
            espera = max(espera or 0, ttl if ttl and ttl > 0 else 1)
    return espera


def registrar_falha(login: str, ip: str | None) -> None:
    janela = get_settings().login_janela_min * 60

    def contar(r):
        p = r.pipeline()
        for k, _ in _chaves(login, ip):
            p.incr(k)
            p.expire(k, janela, nx=True)  # a janela conta do primeiro erro
        p.execute()

    redis_cliente.executar(contar)


def limpar_usuario(login: str) -> None:
    """Login certo zera o contador do usuário (o do IP segue: protege contra várias contas a partir de um IP)."""
    k = _chaves(login, None)[0][0]
    redis_cliente.executar(lambda r: r.delete(k))


def primeira_vez_no_bloqueio(login: str, ip: str | None, espera: int) -> bool:
    """Um LOGIN_BLOQUEADO por janela, não um por tentativa: um ataque não enche a auditoria."""
    k = f"aud_bloqueio:{login.strip().lower()[:60]}:{ip or ''}"
    return bool(redis_cliente.executar(lambda r: r.set(k, 1, nx=True, ex=max(espera, 1))))


def erro_bloqueado(espera: int) -> ErroNegocio:
    minutos = max(1, (espera + 59) // 60)
    return ErroNegocio(f"Muitas tentativas. Tente novamente em {minutos} min", 429,
                       cabecalhos={"Retry-After": str(espera)})
