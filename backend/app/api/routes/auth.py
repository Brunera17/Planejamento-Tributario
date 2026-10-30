from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, Contador, UsuarioAtual
from app.core.erros import ErroNegocio, NaoEncontrado
from app.core.seguranca import conferir_senha, criar_token, gerar_hash
from app.models import Usuario
from app.schemas.cadastro import LoginEntrada, LoginSaida, UsuarioEdicao, UsuarioEntrada, UsuarioSaida

router = APIRouter(tags=["Autenticação e usuários"])


@router.post("/auth/login", response_model=LoginSaida)
def login(dados: LoginEntrada, db: DB):
    u = db.scalar(select(Usuario).where(Usuario.usuario == dados.usuario))
    if u is None or not u.ativo or not conferir_senha(dados.senha, u.senha_hash):
        raise ErroNegocio("Usuário ou senha inválidos", 401)
    return LoginSaida(token=criar_token(u.id, u.perfil), usuario=UsuarioSaida.model_validate(u))


@router.post("/auth/logout", status_code=204)
def logout(_: UsuarioAtual):
    """JWT sem estado: o cliente descarta o token."""


@router.get("/auth/me", response_model=UsuarioSaida)
def eu(u: UsuarioAtual):
    return u


@router.get("/usuarios", response_model=list[UsuarioSaida])
def listar_usuarios(db: DB, _: Contador):
    return db.scalars(select(Usuario).order_by(Usuario.nome)).all()


@router.post("/usuarios", response_model=UsuarioSaida, status_code=201)
def criar_usuario(dados: UsuarioEntrada, db: DB, _: Contador):
    if db.scalar(select(Usuario).where(Usuario.usuario == dados.usuario)):
        raise ErroNegocio("Login já cadastrado", 409, {"usuario": "já existe"})
    u = Usuario(nome=dados.nome, usuario=dados.usuario, senha_hash=gerar_hash(dados.senha), perfil=dados.perfil)
    db.add(u)
    db.commit()
    return u


@router.put("/usuarios/{usuario_id}", response_model=UsuarioSaida)
def editar_usuario(usuario_id: int, dados: UsuarioEdicao, db: DB, atual: Contador):
    u = db.get(Usuario, usuario_id)
    if u is None:
        raise NaoEncontrado("Usuário")
    # impedir o próprio bloqueio garante que sempre reste um contador ativo
    if u.id == atual.id and (not dados.ativo or dados.perfil != "CONTADOR"):
        raise ErroNegocio("Você não pode desativar o próprio usuário nem deixar o perfil de contador", 409)
    u.nome, u.perfil, u.ativo = dados.nome, dados.perfil, dados.ativo
    if dados.senha:
        u.senha_hash = gerar_hash(dados.senha)
    db.commit()
    return u
