from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auditoria, auth, bens_documentos, dashboard, empresas, planejamentos, simulacoes, tabelas
from app.core.config import get_settings
from app.core import redis as redis_cliente
from app.core.contexto import MiddlewareAuditoria
from app.core.erros import registrar_handlers
from app.services import auditoria as auditoria_servico


def criar_app() -> FastAPI:
    app = FastAPI(
        title="Planejador Tributário",
        version="0.1.0",
        description="Compara Simples Nacional, Lucro Presumido e Lucro Real, inclusive na transição da Reforma.",
    )
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_lista, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["Content-Disposition", "X-Proximo"])  # nome dos downloads; próxima página das listas
    app.add_middleware(MiddlewareAuditoria)
    registrar_handlers(app)
    for r in (auth, auditoria, empresas, tabelas, planejamentos, bens_documentos, simulacoes, dashboard):
        app.include_router(r.router, prefix="/api")

    @app.get("/api/saude", tags=["Infra"])
    def saude():
        # sempre 200: se virar health check do Render, uma queda do Redis não pode reiniciar a API em loop
        return {"status": "ok", "redis": redis_cliente.estado(),
                "auditoria_pendente": auditoria_servico.pendentes_na_contingencia()}

    return app


app = criar_app()
