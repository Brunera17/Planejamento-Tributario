import os

import tempfile

os.environ["DATABASE_URL"] = "sqlite://"  # banco em memória para os testes de API
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="planejador-testes-")

os.environ["REDIS_URL"] = ""  # nunca usa um Redis de verdade nos testes
os.environ["COOKIE_SECURE"] = "false"  # o TestClient fala HTTP; cookie Secure não voltaria

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 – registra os modelos
from app.core import redis as redis_cliente
from app.db import session as db_session
from app.db.session import Base, get_db
from app.main import app
from app.seeds import carga


_REDIS = fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture(autouse=True)
def redis_falso():
    """Redis em memória único na suíte (as sessões dos fixtures contador/analista vivem nele). A cada teste
    volta o cliente (um teste pode trocá-lo por um Redis fora do ar) e zeram os contadores de tentativa."""
    redis_cliente.definir_cliente(_REDIS)
    yield _REDIS
    for padrao in ("login_falhas:*", "aud_bloqueio:*"):
        for k in _REDIS.scan_iter(padrao):
            _REDIS.delete(k)
    redis_cliente.definir_cliente(_REDIS)


@pytest.fixture(scope="session")
def fabrica_sessao():
    # TEST_DATABASE_URL (ex.: Postgres do CI) troca só o banco dos testes; o Settings continua em SQLite
    url_teste = os.environ.get("TEST_DATABASE_URL", "")
    if url_teste:
        engine = create_engine(url_teste)
        # drop_all apaga tudo: só em banco com "test" no nome, nunca no de desenvolvimento ou produção
        if "test" not in (engine.url.database or "").lower():
            pytest.exit(f"TEST_DATABASE_URL aponta para '{engine.url.database}': use um banco com 'test' no nome "
                        "(os testes apagam todas as tabelas dele)", returncode=2)
        Base.metadata.drop_all(engine)  # banco descartável: começa sempre vazio
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with fabrica() as db:
        carga.carregar_tabelas(db)
        carga.carregar_catalogo(db)
        carga.carregar_usuarios_demo(db)
        db.flush()
        carga.carregar_demo(db)
        db.commit()
    return fabrica


@pytest.fixture(scope="session")
def cliente(fabrica_sessao):
    def _db():
        with fabrica_sessao() as db:
            yield db

    app.dependency_overrides[get_db] = _db
    db_session.SessionLocal = fabrica_sessao
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _token(cliente, usuario):
    r = cliente.post("/api/auth/login", json={"usuario": usuario, "senha": "demo123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access']}"}


@pytest.fixture(scope="session")
def contador(cliente):
    return _token(cliente, "contador")


@pytest.fixture(scope="session")
def analista(cliente):
    return _token(cliente, "analista")
