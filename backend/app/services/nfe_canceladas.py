"""Chaves de NF-e canceladas por evento, guardadas por planejamento até a aprovação (fim da apuração).

Sem isso, reenviar só o XML original de uma nota já cancelada a traria de volta ao cálculo.
shortcut: fica no Redis (sem persistência no plano grátis, como as sessões); se o Redis reiniciar no meio da apuração,
reenviar o evento de cancelamento junto resolve. Virar tabela se isso passar a acontecer.
"""
from app.core import redis as redis_cliente

VALIDADE_S = 365 * 24 * 3600  # rede de segurança: a aprovação apaga antes


def _chave(pid: int) -> str:
    return f"nfe_canceladas:{pid}"


def lembrar(pid: int, novas: set[str]) -> set[str]:
    """Guarda as chaves novas e devolve todas as canceladas deste planejamento."""
    def op(r):
        if novas:
            r.sadd(_chave(pid), *novas)
            r.expire(_chave(pid), VALIDADE_S)
        return set(r.smembers(_chave(pid)))
    return redis_cliente.executar(op)


def esquecer(pid: int) -> None:
    """Chamado depois do commit da aprovação: com o Redis fora, a validade apaga depois (a aprovação não falha)."""
    try:
        redis_cliente.executar(lambda r: r.delete(_chave(pid)))
    except redis_cliente.RedisIndisponivel:
        pass
