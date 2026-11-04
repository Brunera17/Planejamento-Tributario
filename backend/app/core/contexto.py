"""Contexto da requisição para a auditoria: IP, navegador, sessão e os eventos a gravar.

Os eventos não são gravados no meio da rota: ficam numa fila do contexto e o middleware grava todos de uma vez
quando a resposta vai começar a sair — depois do commit da rota, numa conexão própria. Assim a gravação nunca
disputa o lock de escrita do SQLite com a requisição nem commita por engano o que a rota ainda não gravou.
Se a gravação falhar: num download ou leitura a resposta vira 503 (o conteúdo não sai sem registro); numa
alteração (já commitada) a resposta original segue e o evento vai para o arquivo de contingência.
"""
from __future__ import annotations

import ipaddress
import json
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings

log = logging.getLogger("planejador.auditoria")


@dataclass
class Contexto:
    ip: str | None = None
    user_agent: str | None = None
    sessao_id: str | None = None
    pendentes: list[dict] = field(default_factory=list)


contexto_atual: ContextVar[Contexto | None] = ContextVar("contexto_auditoria", default=None)


def _cabecalho(scope: Scope, nome: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k == nome:
            return v.decode("latin-1")
    return None


def resolver_ip(cliente: str | None, x_forwarded_for: str | None, confiar_xff: bool, proxies: list) -> str | None:
    """IP do cliente. Atrás do proxy do Render, o X-Forwarded-For chega como "forjável..., cliente, proxy...":
    lê da direita para a esquerda, pula os proxies conhecidos e fica com o primeiro endereço que sobrar.
    Fora de proxy (`confiar_xff` falso) o cabeçalho é ignorado — qualquer um poderia escrevê-lo."""
    if not confiar_xff or not x_forwarded_for:
        return cliente
    saltos = [x.strip() for x in x_forwarded_for.split(",") if x.strip()]
    for salto in reversed(saltos):
        try:
            endereco = ipaddress.ip_address(salto)
        except ValueError:
            return cliente  # cabeçalho malformado: não confia em nada dele
        if not any(endereco in rede for rede in proxies):
            return salto
    return saltos[0] if saltos else cliente


class MiddlewareAuditoria:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        cliente = scope.get("client")
        s = get_settings()
        ctx = Contexto(
            ip=resolver_ip(cliente[0] if cliente else None, _cabecalho(scope, b"x-forwarded-for"),
                           s.ip_por_x_forwarded_for, s.proxies_lista),
            user_agent=(_cabecalho(scope, b"user-agent") or "")[:300] or None,
            # sessao_id: preenchido por usuario_atual (deps.py) depois de validar o token
        )
        token = contexto_atual.set(ctx)
        iniciou = False

        async def enviar(msg: Message) -> None:
            nonlocal iniciou
            if msg["type"] == "http.response.start" and not iniciou:
                iniciou = True
                if ctx.pendentes and not await _gravar_pendentes(ctx):
                    await send({"type": "http.response.start", "status": 503,
                                "headers": [(b"content-type", b"application/json")]})
                    corpo = {"erro": "Não foi possível registrar a auditoria; tente novamente", "campos": {}}
                    await send({"type": "http.response.body", "body": json.dumps(corpo).encode()})
                    raise _RespostaSubstituida
            await send(msg)

        try:
            await self.app(scope, receive, enviar)
        except _RespostaSubstituida:
            pass
        finally:
            if ctx.pendentes:  # resposta não chegou a começar (erro não tratado): grava o que houver
                await _gravar_pendentes(ctx)
            contexto_atual.reset(token)


class _RespostaSubstituida(Exception):
    pass


async def _gravar_pendentes(ctx: Contexto) -> bool:
    """Grava os eventos da requisição. Se falhar: alterações vão para a contingência (a operação já foi
    commitada e a resposta original segue); leitura/download devolve False, e a resposta vira 503."""
    from anyio import to_thread

    from app.services import auditoria

    eventos, ctx.pendentes = ctx.pendentes, []
    try:
        await to_thread.run_sync(auditoria.gravar, eventos)
        return True
    except Exception:  # noqa: BLE001 – registrado no log e na contingência
        log.exception("Falha ao gravar %d evento(s) de auditoria", len(eventos))
        alteracoes = [e for e in eventos if e["acao"] not in auditoria.LEITURA]
        if alteracoes:
            await to_thread.run_sync(auditoria.guardar_contingencia, alteracoes)
        return len(alteracoes) == len(eventos)
