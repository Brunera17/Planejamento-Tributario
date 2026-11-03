from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, bens_documentos, dashboard, empresas, planejamentos, simulacoes, tabelas
from app.core.config import get_settings
from app.core.erros import registrar_handlers


def criar_app() -> FastAPI:
    app = FastAPI(
        title="Planejador Tributário",
        version="0.1.0",
        description="Compara Simples Nacional, Lucro Presumido e Lucro Real, inclusive na transição da Reforma.",
    )
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_lista, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["Content-Disposition"])  # nome do arquivo nos downloads (Excel, apresentação)
    registrar_handlers(app)
    for r in (auth, empresas, tabelas, planejamentos, bens_documentos, simulacoes, dashboard):
        app.include_router(r.router, prefix="/api")

    @app.get("/api/saude", tags=["Infra"])
    def saude():
        return {"status": "ok"}

    return app


app = criar_app()
