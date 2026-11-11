"""Cliente Redis: falha fechada, disjuntor e estado no /api/saude."""
import pytest
import redis

from app.core import redis as redis_cliente
from app.core.redis import Disjuntor, RedisIndisponivel


class RedisFora:
    """Simula Redis inacessível: toda operação estoura o timeout."""

    def __init__(self) -> None:
        self.chamadas = 0

    def ping(self):
        self.chamadas += 1
        raise redis.TimeoutError("timeout")

    def get(self, _chave):
        self.chamadas += 1
        raise redis.ConnectionError("recusado")

    def __getattr__(self, _nome):
        # qualquer outro comando (pipeline, hgetall...) também falha como conexão recusada
        def falhar(*_a, **_k):
            self.chamadas += 1
            raise redis.ConnectionError("recusado")
        return falhar


def test_operacao_normal(redis_falso):
    redis_cliente.executar(lambda r: r.set("x", "1"))
    assert redis_cliente.executar(lambda r: r.get("x")) == "1"


def test_redis_fora_vira_503_e_abre_o_disjuntor():
    fora = RedisFora()
    redis_cliente.definir_cliente(fora)
    for _ in range(redis_cliente.disjuntor.limite):
        with pytest.raises(RedisIndisponivel) as e:
            redis_cliente.executar(lambda r: r.get("x"))
        assert e.value.status == 503
    assert redis_cliente.disjuntor.aberto
    # aberto: recusa direto, sem esperar timeout do Redis
    with pytest.raises(RedisIndisponivel):
        redis_cliente.executar(lambda r: r.get("x"))
    assert fora.chamadas == redis_cliente.disjuntor.limite


def test_disjuntor_fecha_depois_da_pausa(monkeypatch):
    d = Disjuntor(limite=2, pausa=5.0)
    agora = [100.0]
    monkeypatch.setattr("app.core.redis.time.monotonic", lambda: agora[0])
    d.falha()
    assert not d.aberto
    d.falha()
    assert d.aberto
    agora[0] += 5.1
    assert not d.aberto
    d.sucesso()
    d.falha()
    assert not d.aberto  # o sucesso zerou a contagem


def test_saude_informa_redis_e_continua_200(cliente):
    r = cliente.get("/api/saude")
    assert r.status_code == 200 and r.json()["redis"] == "ok"
    redis_cliente.definir_cliente(RedisFora())
    r = cliente.get("/api/saude")
    assert r.status_code == 200 and r.json()["redis"] == "indisponivel"


def test_producao_exige_redis_url(monkeypatch):
    from app.core.config import Settings
    with pytest.raises(ValueError, match="REDIS_URL"):
        Settings(database_url="postgresql://u:s@h/db", jwt_secret="x" * 40, redis_url="")


def test_saude_continua_200_com_erro_do_redis_ou_do_disco(cliente, monkeypatch):
    class RedisCarregando:
        def ping(self):
            raise redis.exceptions.BusyLoadingError("LOADING")

    def disco_cheio():
        raise OSError("disco cheio")

    redis_cliente.definir_cliente(RedisCarregando())
    monkeypatch.setattr("app.services.auditoria.pendentes_na_contingencia", disco_cheio)
    r = cliente.get("/api/saude")
    assert r.status_code == 200 and r.json()["redis"] == "indisponivel" and r.json()["auditoria_pendente"] is None
