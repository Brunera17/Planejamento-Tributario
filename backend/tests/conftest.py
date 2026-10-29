import os

import tempfile

os.environ["DATABASE_URL"] = "sqlite://"  # banco em memória para os testes de API
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="planejador-testes-")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 – registra os modelos
from app.db import session as db_session
from app.db.session import Base, get_db
from app.main import app
from app.seeds import carga


@pytest.fixture(scope="session")
def fabrica_sessao():
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
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def contador(cliente):
    return _token(cliente, "contador")


@pytest.fixture(scope="session")
def analista(cliente):
    return _token(cliente, "analista")
