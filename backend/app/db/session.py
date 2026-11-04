from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def criar_engine(url: str | None = None):
    s = get_settings()
    url = url or s.database_url
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    # tamanho fixo por processo; pre_ping descarta conexão derrubada pelo Postgres antes de entregá-la
    return create_engine(url, pool_size=s.db_pool_size, max_overflow=s.db_max_overflow, pool_pre_ping=True)


engine = criar_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
