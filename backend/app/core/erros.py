"""Respostas de erro padronizadas: código HTTP + {"erro": ..., "campos": {...}}."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErroNegocio(Exception):
    def __init__(self, mensagem: str, status: int = 422, campos: dict[str, str] | None = None):
        self.mensagem = mensagem
        self.status = status
        self.campos = campos or {}


class NaoEncontrado(ErroNegocio):
    def __init__(self, recurso: str):
        super().__init__(f"{recurso} não encontrado(a)", 404)


def registrar_handlers(app: FastAPI) -> None:
    @app.exception_handler(ErroNegocio)
    async def _negocio(_: Request, e: ErroNegocio):
        return JSONResponse({"erro": e.mensagem, "campos": e.campos}, status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def _validacao(_: Request, e: RequestValidationError):
        campos = {".".join(str(p) for p in err["loc"] if p != "body"): err["msg"].removeprefix("Value error, ") for err in e.errors()}
        return JSONResponse({"erro": "Dados inválidos", "campos": campos}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException):
        return JSONResponse({"erro": e.detail, "campos": {}}, status_code=e.status_code, headers=e.headers)
