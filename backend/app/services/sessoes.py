"""Sessões no Redis: criação, renovação com rotação do refresh, detecção de reuso e revogação.

Chaves (todas expiram no fim absoluto da sessão — renovar não estende):
    sessao:{sid}                hash: usuario_id, perfil, nivel, criada_em, expira_em, ip, user_agent, refresh_atual
    refresh:{hash}              sid do refresh vigente
    refresh_usado:{hash}        "sid|instante" de um refresh já trocado (tolerância e detecção de reuso)
    usuario_sessoes:{uid}       set de sids do usuário
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from app.core import redis as redis_cliente
from app.core.config import get_settings
from app.core.seguranca import criar_access, gerar_refresh, hash_refresh


@dataclass
class Emissao:
    sid: str
    access: str
    expira_access: object
    refresh: str | None  # None: dentro da tolerância, o navegador já tem o cookie novo
    expira_sessao: int  # epoch


@dataclass
class Renovacao:
    situacao: str  # "ok" | "tolerancia" | "reuso" | "invalido"
    emissao: Emissao | None = None
    sid: str | None = None
    usuario_id: int | None = None


def _k(sid: str) -> str:
    return f"sessao:{sid}"


def criar(usuario_id: int, perfil: str, ip: str | None, user_agent: str | None, nivel: str = "senha") -> Emissao:
    s = get_settings()
    agora = int(time.time())
    expira = agora + s.sessao_absoluta_h * 3600
    sid = secrets.token_urlsafe(16)
    refresh = gerar_refresh()
    h = hash_refresh(refresh)

    def gravar(r):
        p = r.pipeline()
        p.hset(_k(sid), mapping={"usuario_id": usuario_id, "perfil": perfil, "nivel": nivel, "criada_em": agora,
                                 "expira_em": expira, "ip": ip or "", "user_agent": user_agent or "",
                                 "refresh_atual": h})
        p.expireat(_k(sid), expira)
        p.set(f"refresh:{h}", sid, exat=expira)
        p.sadd(f"usuario_sessoes:{usuario_id}", sid)
        p.expire(f"usuario_sessoes:{usuario_id}", s.sessao_absoluta_h * 3600)
        p.execute()

    redis_cliente.executar(gravar)
    access, exp = criar_access(usuario_id, perfil, sid)
    return Emissao(sid, access, exp, refresh, expira)


def validar(sid: str, usuario_id: int) -> dict | None:
    """A sessão existe e é desse usuário? (1 ida ao Redis por requisição)."""
    dados = redis_cliente.executar(lambda r: r.hgetall(_k(sid)))
    if not dados or dados.get("usuario_id") != str(usuario_id):
        return None
    return dados


def renovar(refresh: str) -> Renovacao:
    s = get_settings()
    h = hash_refresh(refresh)
    agora = time.time()
    # GETDEL é atômico: entre requisições simultâneas com o mesmo refresh, só uma troca o token
    sid = redis_cliente.executar(lambda r: r.getdel(f"refresh:{h}"))
    if sid is None:
        usado = redis_cliente.executar(lambda r: r.get(f"refresh_usado:{h}"))
        if not usado:
            return Renovacao("invalido")
        sid_usado, quando = usado.split("|")
        dados = redis_cliente.executar(lambda r: r.hgetall(_k(sid_usado)))
        if not dados:
            return Renovacao("invalido")
        uid = int(dados["usuario_id"])
        if agora - float(quando) <= s.refresh_tolerancia_s:
            access, exp = criar_access(uid, dados["perfil"], sid_usado)
            return Renovacao("tolerancia", Emissao(sid_usado, access, exp, None, int(dados["expira_em"])), sid_usado, uid)
        encerrar(sid_usado)  # refresh velho reapareceu: trata como roubo
        return Renovacao("reuso", sid=sid_usado, usuario_id=uid)

    dados = redis_cliente.executar(lambda r: r.hgetall(_k(sid)))
    if not dados:
        return Renovacao("invalido")
    expira = int(dados["expira_em"])
    novo = gerar_refresh()
    nh = hash_refresh(novo)

    def trocar(r):
        p = r.pipeline()
        p.set(f"refresh_usado:{h}", f"{sid}|{agora}", exat=expira)
        p.set(f"refresh:{nh}", sid, exat=expira)
        p.hset(_k(sid), "refresh_atual", nh)
        p.execute()

    redis_cliente.executar(trocar)
    uid = int(dados["usuario_id"])
    access, exp = criar_access(uid, dados["perfil"], sid)
    return Renovacao("ok", Emissao(sid, access, exp, novo, expira), sid, uid)


def elevar(sid: str, nivel: str) -> None:
    redis_cliente.executar(lambda r: r.hset(_k(sid), "nivel", nivel))


def encerrar(sid: str) -> None:
    def apagar(r):
        dados = r.hgetall(_k(sid))
        p = r.pipeline()
        p.delete(_k(sid))
        if dados.get("refresh_atual"):
            p.delete(f"refresh:{dados['refresh_atual']}")
        if dados.get("usuario_id"):
            p.srem(f"usuario_sessoes:{dados['usuario_id']}", sid)
        p.execute()

    redis_cliente.executar(apagar)


def encerrar_todas(usuario_id: int, exceto: str | None = None) -> int:
    sids = redis_cliente.executar(lambda r: r.smembers(f"usuario_sessoes:{usuario_id}"))
    n = 0
    for sid in sids:
        if sid != exceto:
            encerrar(sid)
            n += 1
    return n
