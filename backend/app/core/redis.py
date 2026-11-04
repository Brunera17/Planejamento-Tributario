"""Cliente Redis único da API: sessões, limites de tentativa e deduplicação da auditoria.

Síncrono de propósito (as rotas rodam no threadpool). Falha fechada e rápida: timeouts curtos e um disjuntor
que, após falhas seguidas, recusa por alguns segundos sem tentar — um Redis lento não prende as threads da API.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TypeVar

import redis

from app.core.config import get_settings
from app.core.erros import ErroNegocio

T = TypeVar("T")


class RedisIndisponivel(ErroNegocio):
    def __init__(self) -> None:
        super().__init__("Serviço de sessão indisponível; tente novamente em instantes", 503)


class Disjuntor:
    """Abre após `limite` falhas seguidas e fica aberto por `pausa` segundos; um sucesso fecha."""

    def __init__(self, limite: int, pausa: float) -> None:
        self.limite, self.pausa = limite, pausa
        self._falhas = 0
        self._aberto_ate = 0.0
        self._trava = threading.Lock()

    @property
    def aberto(self) -> bool:
        return time.monotonic() < self._aberto_ate

    def sucesso(self) -> None:
        with self._trava:
            self._falhas, self._aberto_ate = 0, 0.0

    def falha(self) -> None:
        with self._trava:
            self._falhas += 1
            if self._falhas >= self.limite:
                self._aberto_ate = time.monotonic() + self.pausa


_cliente: redis.Redis | None = None
_trava_cliente = threading.Lock()
disjuntor = Disjuntor(limite=3, pausa=5.0)


def _criar() -> redis.Redis:
    s = get_settings()
    if not s.redis_url:
        # desenvolvimento sem Redis instalado: fakeredis em memória (só existe com requirements-dev)
        try:
            import fakeredis
        except ImportError as e:
            raise RuntimeError("Defina REDIS_URL ou instale requirements-dev.txt (fakeredis)") from e
        return fakeredis.FakeRedis(decode_responses=True)
    pool = redis.ConnectionPool.from_url(
        s.redis_url, decode_responses=True, max_connections=s.redis_max_conexoes,
        socket_timeout=s.redis_timeout_s, socket_connect_timeout=s.redis_timeout_s,
        retry_on_timeout=False, health_check_interval=30,
    )
    return redis.Redis(connection_pool=pool)


def cliente() -> redis.Redis:
    global _cliente
    if _cliente is None:
        with _trava_cliente:
            if _cliente is None:
                _cliente = _criar()
    return _cliente


def definir_cliente(c: redis.Redis | None) -> None:
    """Troca o cliente (testes usam fakeredis); None faz recriar a partir da configuração."""
    global _cliente
    with _trava_cliente:
        _cliente = c
    disjuntor.sucesso()


def executar(operacao: Callable[[redis.Redis], T]) -> T:
    """Roda uma operação no Redis; indisponível (ou disjuntor aberto) vira 503, nunca acesso liberado."""
    if disjuntor.aberto:
        raise RedisIndisponivel()
    try:
        resultado = operacao(cliente())
    except (redis.ConnectionError, redis.TimeoutError) as e:
        disjuntor.falha()
        raise RedisIndisponivel() from e
    disjuntor.sucesso()
    return resultado


def estado() -> str:
    """'ok', 'indisponivel' ou 'disjuntor_aberto' — para o /api/saude."""
    if disjuntor.aberto:
        return "disjuntor_aberto"
    try:
        executar(lambda r: r.ping())
    except RedisIndisponivel:
        return "indisponivel"
    return "ok"
