from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_BACKEND = Path(__file__).resolve().parents[2]
# só desenvolvimento/testes: está no repositório, não protege nada (produção exige CHAVE_ARQUIVOS)
CHAVE_ARQUIVOS_DESENVOLVIMENTO = "ZGVzZW52b2x2aW1lbnRvLXNvbWVudGUtbmFvLXVzYXI="


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(RAIZ_BACKEND.parent / ".env", RAIZ_BACKEND / ".env"), extra="ignore")

    database_url: str = f"sqlite:///{(RAIZ_BACKEND / 'planejador.db').as_posix()}"
    jwt_secret: str = "dev-somente-local-troque-em-producao-0123456789"
    jwt_secret_anterior: str = ""  # aceito só na leitura, durante a troca do segredo
    # sessões (D2: expiração absoluta, sem inatividade)
    access_ttl_min: int = 15
    sessao_absoluta_h: int = 12
    refresh_tolerancia_s: int = 20  # corrida entre abas: o refresh recém-trocado ainda vale por alguns segundos
    cookie_secure: bool = True  # false só em HTTP local fora de localhost
    # limite de tentativas de login
    login_max_falhas_usuario: int = 5
    login_max_falhas_ip: int = 20
    login_janela_min: int = 15
    # IP do cliente: só confia no X-Forwarded-For atrás de proxy (Render); a lista pula os saltos conhecidos
    ip_por_x_forwarded_for: bool = False
    proxies_confiaveis: str = ""  # CIDRs separados por vírgula (ex.: faixas do proxy da Vercel)
    origem_publica: str = ""  # ex.: https://planejamento-tributario.domingosassessoria.com.br
    upload_dir: str = str(RAIZ_BACKEND / "uploads")
    # criptografia dos arquivos (envelope AES-256-GCM, app/services/cripto.py). Perder a chave = perder os arquivos:
    # guarde uma cópia fora do Render. Gere com `python -m app.services.cripto --gerar-chave`.
    chave_arquivos: str = ""  # base64 de 32 bytes; obrigatória em produção
    chave_arquivos_id: str = "k1"  # muda a cada rotação; vai no cabeçalho de cada arquivo
    chaves_arquivos_antigas: str = ""  # "id:base64,id:base64" — só leitura, durante a rotação
    aceitar_arquivo_sem_cifra: bool = True  # false depois de rodar --cifrar-existentes
    escritorio_nome: str = "Planejador Tributário"  # aparece no cabeçalho do relatório PDF
    upload_max_mb: int = 10
    # NF-e: o .zip é lido entrada por entrada; os limites barram "zip bomb" e envios que não cabem na memória
    nfe_zip_max_mb: int = 100  # arquivo enviado (compactado)
    nfe_xml_max_mb: int = 5  # cada XML, já descompactado
    nfe_zip_descompactado_max_mb: int = 1024  # soma dos XML descompactados
    nfe_zip_max_arquivos: int = 20000
    relatorio_contabil_max_mb: int = 20
    # pool de conexões do Postgres, por processo do Uvicorn (2 processos → até 20 conexões)
    db_pool_size: int = 5
    db_max_overflow: int = 5
    # Redis (sessões, limites de tentativa). Vazio só em desenvolvimento: usa fakeredis em memória
    redis_url: str = ""
    redis_timeout_s: float = 0.5
    redis_max_conexoes: int = 20
    # auditoria
    auditoria_retencao_anos: int = 5
    auditoria_dedup_horas: int = 12  # PLANEJAMENTO_ABERTO: uma vez por sessão (duração absoluta da sessão)
    cors_origins: str = "http://localhost:5173"

    @field_validator("database_url")
    @classmethod
    def _driver(cls, v: str) -> str:
        # Render e outros entregam postgres://; o SQLAlchemy usa o driver psycopg 3
        for prefixo in ("postgres://", "postgresql://"):
            if v.startswith(prefixo):
                return "postgresql+psycopg://" + v[len(prefixo):]
        return v

    @model_validator(mode="after")
    def _segredo(self):
        if not self.database_url.startswith("sqlite") and (self.jwt_secret.startswith("dev-") or self.jwt_secret.startswith("troque-") or len(self.jwt_secret) < 32):
            raise ValueError("Em produção, defina JWT_SECRET com pelo menos 32 caracteres aleatórios")
        if not self.database_url.startswith("sqlite") and not self.redis_url:
            raise ValueError("Em produção, defina REDIS_URL")
        if not self.database_url.startswith("sqlite") and not self.chave_arquivos:
            raise ValueError("Em produção, defina CHAVE_ARQUIVOS (python -m app.services.cripto --gerar-chave)")
        return self

    @property
    def chave_arquivos_efetiva(self) -> str:
        """Sem CHAVE_ARQUIVOS (só desenvolvimento e testes, em SQLite): uma chave fixa e pública — nunca em produção."""
        return self.chave_arquivos or CHAVE_ARQUIVOS_DESENVOLVIMENTO

    @property
    def cors_lista(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def origens_permitidas(self) -> set[str]:
        """Origens aceitas nas rotas que usam o cookie de refresh (conferência de Origin contra CSRF)."""
        return {*self.cors_lista, *([self.origem_publica.rstrip("/")] if self.origem_publica else [])}

    @property
    def proxies_lista(self) -> list:
        import ipaddress
        return [ipaddress.ip_network(p.strip(), strict=False) for p in self.proxies_confiaveis.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
