from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_BACKEND = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(RAIZ_BACKEND.parent / ".env", RAIZ_BACKEND / ".env"), extra="ignore")

    database_url: str = f"sqlite:///{(RAIZ_BACKEND / 'planejador.db').as_posix()}"
    jwt_secret: str = "dev-somente-local-troque-em-producao-0123456789"
    jwt_expira_minutos: int = 480
    upload_dir: str = str(RAIZ_BACKEND / "uploads")
    escritorio_nome: str = "Planejador Tributário"  # aparece no cabeçalho do relatório PDF
    upload_max_mb: int = 10
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_lista(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
