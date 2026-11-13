"""Chaves de NF-e canceladas por evento, guardadas por planejamento (só o identificador).

Sem isso, reenviar só o XML original de uma nota já cancelada a traria de volta ao cálculo. Ficam até a validade,
e não são apagadas na aprovação: um planejamento reaberto reimporta as notas e ainda precisa delas.
shortcut: fica no Redis (sem persistência no plano grátis, como as sessões); se o Redis reiniciar no meio da apuração,
reenviar o evento de cancelamento junto resolve. Virar tabela se isso passar a acontecer.
"""
from app.core import redis as redis_cliente
from app.core.erros import ErroNegocio

VALIDADE_S = 365 * 24 * 3600
LIMITE = 20_000  # chaves por planejamento: o Redis é o mesmo das sessões e não pode encher


def _chave(pid: int) -> str:
    return f"nfe_canceladas:{pid}"


def canceladas(pid: int, novas: set[str]) -> set[str]:
    """Todas as canceladas deste planejamento, incluindo as do envio atual (ainda não guardadas)."""
    todas = redis_cliente.executar(lambda r: set(r.smembers(_chave(pid)))) | novas
    if len(todas) > LIMITE:
        raise ErroNegocio(f"Mais de {LIMITE} notas canceladas neste planejamento; confira os arquivos enviados", 413)
    return todas


def guardar(pid: int, novas: set[str]) -> None:
    """Chamado depois do commit da importação: uma importação que falha não deixa marca."""
    if not novas:
        return

    def op(r):
        with r.pipeline() as t:  # MULTI/EXEC: a chave nunca fica sem validade
            t.sadd(_chave(pid), *novas)
            t.expire(_chave(pid), VALIDADE_S)
            t.execute()
    redis_cliente.executar(op)
