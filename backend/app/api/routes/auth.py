import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import DB, Contador, ProtecaoCsrf, SidAtual, UsuarioAtual
from app.core.config import get_settings
from app.core.contexto import contexto_atual
from app.core.erros import ErroNegocio, NaoEncontrado
from app.core.seguranca import conferir_senha_tempo_constante, gerar_hash
from app.models import Usuario
from app.schemas.cadastro import LoginEntrada, LoginSaida, UsuarioEdicao, UsuarioEntrada, UsuarioSaida
from app.services import limite_login, sessoes
from app.services.auditoria import auditar

router = APIRouter(tags=["Autenticação e usuários"])

COOKIE_PATH = "/api/auth"


def _nome_cookie() -> str:
    # o prefixo __Secure- obriga o navegador a só aceitar o cookie com Secure
    return "__Secure-rt" if get_settings().cookie_secure else "rt"


def _gravar_cookie(resposta: Response, refresh: str, expira_sessao: int) -> None:
    resposta.set_cookie(_nome_cookie(), refresh, max_age=max(1, expira_sessao - int(time.time())), path=COOKIE_PATH,
                        secure=get_settings().cookie_secure, httponly=True, samesite="strict")


def _apagar_cookie(resposta: Response) -> None:
    resposta.delete_cookie(_nome_cookie(), path=COOKIE_PATH, secure=get_settings().cookie_secure, httponly=True,
                           samesite="strict")


def _saida(emissao: sessoes.Emissao, u: Usuario) -> LoginSaida:
    return LoginSaida(access=emissao.access, expira_em=emissao.expira_access, sessao_expira_em=emissao.expira_sessao,
                      usuario=UsuarioSaida.model_validate(u))


def _sem_cache(resposta: Response) -> None:
    resposta.headers["Cache-Control"] = "no-store"


@router.post("/auth/login", response_model=LoginSaida)
def login(dados: LoginEntrada, db: DB, resposta: Response):
    ctx = contexto_atual.get()
    ip = ctx.ip if ctx else None
    espera = limite_login.bloqueio(dados.usuario, ip)
    if espera:
        if limite_login.primeira_vez_no_bloqueio(dados.usuario, ip, espera):
            auditar("LOGIN_BLOQUEADO", resultado="NEGADO", usuario_login=dados.usuario, detalhes={"espera_s": espera})
        raise limite_login.erro_bloqueado(espera)
    u = db.scalar(select(Usuario).where(Usuario.usuario == dados.usuario))
    # bcrypt sempre roda (mesmo sem usuário ou inativo): o tempo de resposta não revela o que falhou
    senha_ok = conferir_senha_tempo_constante(dados.senha, u.senha_hash if u else None)
    motivo = "usuario_inexistente" if u is None else "usuario_inativo" if not u.ativo else None if senha_ok else "senha_incorreta"
    if motivo:
        limite_login.registrar_falha(dados.usuario, ip)
        auditar("LOGIN_FALHA", resultado="FALHA", usuario=u, usuario_login=dados.usuario, detalhes={"motivo": motivo})
        raise ErroNegocio("Usuário ou senha inválidos", 401)
    limite_login.limpar_usuario(dados.usuario)
    emissao = sessoes.criar(u.id, u.perfil, ip, ctx.user_agent if ctx else None)
    if ctx is not None:
        ctx.sessao_id = emissao.sid
    auditar("LOGIN_OK", usuario=u)
    _gravar_cookie(resposta, emissao.refresh, emissao.expira_sessao)
    _sem_cache(resposta)
    return _saida(emissao, u)


@router.post("/auth/refresh", response_model=LoginSaida, dependencies=[ProtecaoCsrf])
def renovar(request: Request, db: DB, resposta: Response):
    """Troca o refresh do cookie por um novo e devolve um access novo. Refresh já usado = sessão derrubada."""
    token = request.cookies.get(_nome_cookie())
    if not token:
        raise ErroNegocio("Sessão expirada; entre novamente", 401)
    r = sessoes.renovar(token)
    ctx = contexto_atual.get()
    if ctx is not None and r.sid:
        ctx.sessao_id = r.sid
    if r.situacao == "reuso":
        auditar("REFRESH_REUSO", resultado="NEGADO", usuario=db.get(Usuario, r.usuario_id),
                detalhes={"acao": "sessão encerrada por suspeita de roubo do token"})
    if r.situacao in ("reuso", "invalido"):
        negado = JSONResponse({"erro": "Sessão expirada; entre novamente", "campos": {}}, status_code=401)
        _apagar_cookie(negado)  # o navegador descarta o refresh morto
        return negado
    u = db.get(Usuario, r.usuario_id)
    if u is None or not u.ativo:
        sessoes.encerrar(r.sid)
        raise ErroNegocio("Usuário inativo", 401)
    if r.emissao.refresh:  # na tolerância o navegador já tem o cookie novo (outra aba renovou)
        _gravar_cookie(resposta, r.emissao.refresh, r.emissao.expira_sessao)
    _sem_cache(resposta)
    return _saida(r.emissao, u)


@router.post("/auth/logout", status_code=204)
def logout(u: UsuarioAtual, sid: SidAtual, resposta: Response):
    if sid:
        sessoes.encerrar(sid)
    _apagar_cookie(resposta)
    auditar("LOGOUT", usuario=u)


@router.post("/auth/logout-todos", status_code=204)
def logout_todos(u: UsuarioAtual, resposta: Response):
    """Sair de todos os dispositivos, inclusive deste."""
    n = sessoes.encerrar_todas(u.id)
    _apagar_cookie(resposta)
    auditar("LOGOUT_TODOS", usuario=u, detalhes={"sessoes_encerradas": n})


@router.get("/auth/me", response_model=UsuarioSaida)
def eu(u: UsuarioAtual):
    return u


@router.get("/usuarios", response_model=list[UsuarioSaida])
def listar_usuarios(db: DB, _: Contador):
    return db.scalars(select(Usuario).order_by(Usuario.nome)).all()


@router.post("/usuarios", response_model=UsuarioSaida, status_code=201)
def criar_usuario(dados: UsuarioEntrada, db: DB, atual: Contador):
    if db.scalar(select(Usuario).where(Usuario.usuario == dados.usuario)):
        raise ErroNegocio("Login já cadastrado", 409, {"usuario": "já existe"})
    u = Usuario(nome=dados.nome, usuario=dados.usuario, senha_hash=gerar_hash(dados.senha), perfil=dados.perfil)
    db.add(u)
    db.commit()
    auditar("USUARIO_CRIADO", usuario=atual, recurso_tipo="usuario", recurso_id=u.id,
            detalhes={"login": u.usuario, "perfil": u.perfil})
    return u


@router.put("/usuarios/{usuario_id}", response_model=UsuarioSaida)
def editar_usuario(usuario_id: int, dados: UsuarioEdicao, db: DB, atual: Contador):
    u = db.get(Usuario, usuario_id)
    if u is None:
        raise NaoEncontrado("Usuário")
    # impedir o próprio bloqueio garante que sempre reste um contador ativo
    if u.id == atual.id and (not dados.ativo or dados.perfil != "CONTADOR"):
        raise ErroNegocio("Você não pode desativar o próprio usuário nem deixar o perfil de contador", 409)
    sid: str | None = None
    ctx = contexto_atual.get()
    if ctx is not None:
        sid = ctx.sessao_id
    antes = (u.nome, u.perfil, u.ativo)
    u.nome, u.perfil, u.ativo = dados.nome, dados.perfil, dados.ativo
    if dados.senha:
        u.senha_hash = gerar_hash(dados.senha)
    db.commit()
    alvo = {"usuario": atual, "recurso_tipo": "usuario", "recurso_id": u.id}
    if antes[0] != u.nome:
        auditar("USUARIO_EDITADO", **alvo, detalhes={"login": u.usuario, "nome": [antes[0], u.nome]})
    if antes[1] != u.perfil:
        auditar("PERFIL_ALTERADO", **alvo, detalhes={"login": u.usuario, "perfil": [antes[1], u.perfil]})
    if antes[2] != u.ativo:
        auditar("USUARIO_REATIVADO" if u.ativo else "USUARIO_DESATIVADO", **alvo, detalhes={"login": u.usuario})
    if dados.senha:
        auditar("SENHA_ALTERADA", **alvo, detalhes={"login": u.usuario})
    # senha, perfil ou situação mudaram: as sessões abertas caem (na própria troca de senha, fica só esta)
    if dados.senha or antes[1] != u.perfil or antes[2] != u.ativo:
        sessoes.encerrar_todas(u.id, exceto=sid if u.id == atual.id else None)
    return u
