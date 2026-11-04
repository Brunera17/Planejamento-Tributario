"""Sessões: access curto + refresh rotativo no cookie, revogação, limite de login, CSRF e ataques ao JWT."""
import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import redis as redis_cliente
from app.core.config import get_settings
from app.core.contexto import resolver_ip
from app.core.seguranca import ALGORITMO, AUDIENCIA, EMISSOR, _kid
from app.main import app
from app.models import EventoAuditoria
from tests.test_redis import RedisFora

CSRF = {"X-Requested-With": "planejador"}
COOKIE = "rt"  # COOKIE_SECURE=false nos testes; em produção é __Secure-rt


@pytest.fixture
def nav(cliente):
    """Um "navegador" novo por teste: cookie jar próprio (o fixture cliente é compartilhado)."""
    return TestClient(app)


def entrar(nav, usuario="analista", senha="demo123", **kw):
    return nav.post("/api/auth/login", json={"usuario": usuario, "senha": senha}, **kw)


def h(r):
    return {"Authorization": f"Bearer {r.json()['access']}"}


def eventos(fabrica, acao):
    with fabrica() as db:
        return db.scalars(select(EventoAuditoria).where(EventoAuditoria.acao == acao)).all()


# ------------------------------------------------------------------ login e cookie

def test_login_entrega_access_curto_e_cookie_protegido(nav):
    r = entrar(nav)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    corpo = r.json()
    assert set(corpo) == {"access", "expira_em", "sessao_expira_em", "usuario"} and "token" not in corpo
    cookie = r.headers["set-cookie"].lower()
    assert all(x in cookie for x in ("httponly", "samesite=strict", "path=/api/auth"))
    payload = jwt.decode(corpo["access"], options={"verify_signature": False})
    assert payload["exp"] - payload["iat"] == get_settings().access_ttl_min * 60
    assert payload["typ"] == "access" and payload["aud"] == AUDIENCIA and payload["sid"]
    assert abs(corpo["sessao_expira_em"] - (time.time() + 12 * 3600)) < 60


def test_cookie_secure_em_producao(nav, monkeypatch):
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    cookie = entrar(nav).headers["set-cookie"]
    assert cookie.startswith("__Secure-rt=") and "secure" in cookie.lower()


# ------------------------------------------------------------------ refresh

def test_refresh_rotaciona_e_reuso_derruba_a_sessao(nav, monkeypatch, fabrica_sessao):
    monkeypatch.setattr(get_settings(), "refresh_tolerancia_s", 0)
    login = entrar(nav)
    velho = nav.cookies[COOKIE]
    r = nav.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 200 and nav.cookies[COOKIE] != velho
    assert nav.get("/api/auth/me", headers=h(r)).status_code == 200

    time.sleep(0.01)
    atacante = TestClient(app)
    atacante.cookies.set(COOKIE, velho, path="/api/auth")
    assert atacante.post("/api/auth/refresh", headers=CSRF).status_code == 401
    # a sessão inteira caiu: o access da vítima e o refresh novo também
    assert nav.get("/api/auth/me", headers=h(login)).status_code == 401
    assert nav.post("/api/auth/refresh", headers=CSRF).status_code == 401
    assert eventos(fabrica_sessao, "REFRESH_REUSO")


def test_corrida_entre_abas_dentro_da_tolerancia_nao_derruba(nav):
    entrar(nav)
    velho = nav.cookies[COOKIE]
    assert nav.post("/api/auth/refresh", headers=CSRF).status_code == 200
    outra_aba = TestClient(app)
    outra_aba.cookies.set(COOKIE, velho, path="/api/auth")
    r = outra_aba.post("/api/auth/refresh", headers=CSRF)
    assert r.status_code == 200 and "set-cookie" not in r.headers  # o navegador já tem o cookie novo
    assert nav.post("/api/auth/refresh", headers=CSRF).status_code == 200


def test_renovar_nao_estende_a_sessao(nav, redis_falso):
    r = entrar(nav)
    sid = jwt.decode(r.json()["access"], options={"verify_signature": False})["sid"]
    ttl_antes = redis_falso.ttl(f"sessao:{sid}")
    r2 = nav.post("/api/auth/refresh", headers=CSRF)
    assert r2.json()["sessao_expira_em"] == r.json()["sessao_expira_em"]
    assert redis_falso.ttl(f"sessao:{sid}") <= ttl_antes


def test_refresh_sem_cookie_ou_invalido(nav):
    assert nav.post("/api/auth/refresh", headers=CSRF).status_code == 401
    nav.cookies.set(COOKIE, "inventado", path="/api/auth")
    assert nav.post("/api/auth/refresh", headers=CSRF).status_code == 401


@pytest.mark.parametrize("cabecalhos", [{}, {**CSRF, "Origin": "https://site-malicioso.example"}])
def test_refresh_exige_protecao_csrf(nav, cabecalhos):
    entrar(nav)
    assert nav.post("/api/auth/refresh", headers=cabecalhos).status_code == 403


def test_refresh_com_origem_permitida(nav):
    entrar(nav)
    assert nav.post("/api/auth/refresh", headers={**CSRF, "Origin": "http://localhost:5173"}).status_code == 200


def test_refresh_pelo_rewrite_da_vercel_usa_a_origem_publica(nav, monkeypatch):
    """Em produção o Host que chega é o do Render; quem libera é ORIGEM_PUBLICA, mesmo com CORS_ORIGINS vazio."""
    publica = "https://planejamento-tributario.domingosassessoria.com.br"
    monkeypatch.setattr(get_settings(), "cors_origins", "")
    monkeypatch.setattr(get_settings(), "origem_publica", publica)
    entrar(nav)
    cab = {**CSRF, "Origin": publica, "Host": "planejador-api.onrender.com"}
    assert nav.post("/api/auth/refresh", headers=cab).status_code == 200


def test_refresh_da_mesma_origem_pelo_proxy(nav):
    entrar(nav)  # o TestClient fala com o host "testserver"
    assert nav.post("/api/auth/refresh", headers={**CSRF, "Origin": "http://testserver"}).status_code == 200


# ------------------------------------------------------------------ revogação

def test_logout_derruba_access_e_refresh_na_hora(nav, fabrica_sessao):
    r = entrar(nav)
    assert nav.post("/api/auth/logout", headers=h(r)).status_code == 204
    assert nav.get("/api/auth/me", headers=h(r)).status_code == 401
    assert nav.post("/api/auth/refresh", headers=CSRF).status_code == 401


def test_logout_de_todos_os_dispositivos(nav):
    a, b = entrar(nav), entrar(TestClient(app))
    assert nav.post("/api/auth/logout-todos", headers=h(a)).status_code == 204
    assert nav.get("/api/auth/me", headers=h(b)).status_code == 401


def test_troca_de_senha_derruba_as_outras_sessoes(cliente, contador):
    u = cliente.post("/api/usuarios", headers=contador, json={
        "nome": "Sessoes", "usuario": "sessoes.teste", "senha": "senha-forte-1", "perfil": "ANALISTA"}).json()
    aberta = entrar(TestClient(app), "sessoes.teste", "senha-forte-1")
    base = {"nome": "Sessoes", "perfil": "ANALISTA", "ativo": True}
    cliente.put(f"/api/usuarios/{u['id']}", headers=contador, json={**base, "nome": "Sessoes 2"})
    assert cliente.get("/api/auth/me", headers=h(aberta)).status_code == 200  # só o nome: sessão segue
    cliente.put(f"/api/usuarios/{u['id']}", headers=contador, json={**base, "senha": "nova-senha-2"})
    assert cliente.get("/api/auth/me", headers=h(aberta)).status_code == 401


def test_mudanca_de_perfil_derruba_a_sessao(cliente, contador):
    u = cliente.post("/api/usuarios", headers=contador, json={
        "nome": "Perfil", "usuario": "perfil.teste", "senha": "senha-forte-1", "perfil": "ANALISTA"}).json()
    aberta = entrar(TestClient(app), "perfil.teste", "senha-forte-1")
    cliente.put(f"/api/usuarios/{u['id']}", headers=contador, json={"nome": "Perfil", "perfil": "CONTADOR", "ativo": True})
    assert cliente.get("/api/auth/me", headers=h(aberta)).status_code == 401


# ------------------------------------------------------------------ ataques ao JWT

def _forjar(payload, segredo=None, alg=ALGORITMO, kid=None):
    segredo = segredo or get_settings().jwt_secret
    return jwt.encode(payload, segredo, algorithm=alg, headers={"kid": kid or _kid(segredo)})


def _payload(**troca):
    agora = datetime.now(UTC)
    base = {"sub": "1", "perfil": "CONTADOR", "sid": "x", "typ": "access", "iss": EMISSOR, "aud": AUDIENCIA,
            "iat": agora, "exp": agora + timedelta(minutes=5)}
    return {**base, **troca}


@pytest.mark.parametrize("token", [
    lambda: _forjar(_payload(aud="outro")),
    lambda: _forjar(_payload(iss="outro")),
    lambda: _forjar(_payload(typ="refresh")),
    lambda: _forjar(_payload(exp=datetime.now(UTC) - timedelta(seconds=1))),
    lambda: _forjar(_payload(), segredo="segredo-de-outra-pessoa-0123456789abcdef"),
    lambda: jwt.encode(_payload(), key=None, algorithm="none"),
])
def test_tokens_forjados_sao_recusados(cliente, token):
    assert cliente.get("/api/auth/me", headers={"Authorization": f"Bearer {token()}"}).status_code == 401


def test_token_valido_sem_sessao_viva_e_recusado(cliente):
    token = _forjar(_payload(sid="sessao-que-nao-existe"))
    assert cliente.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_segredo_anterior_vale_durante_a_rotacao(nav, monkeypatch):
    r = entrar(nav)
    s = get_settings()
    monkeypatch.setattr(s, "jwt_secret_anterior", s.jwt_secret)
    monkeypatch.setattr(s, "jwt_secret", "segredo-novo-depois-da-rotacao-0123456789")
    assert nav.get("/api/auth/me", headers=h(r)).status_code == 200
    monkeypatch.setattr(s, "jwt_secret_anterior", "")
    assert nav.get("/api/auth/me", headers=h(r)).status_code == 401


# ------------------------------------------------------------------ limite de tentativas

def test_sexta_tentativa_bloqueia_com_retry_after(nav, fabrica_sessao):
    for _ in range(5):
        assert entrar(nav, "contador", "errada").status_code == 401
    r = entrar(nav, "contador", "errada")
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    assert entrar(nav, "contador", "demo123").status_code == 429  # nem a senha certa entra na janela
    entrar(nav, "contador", "errada")
    bloqueios = [e for e in eventos(fabrica_sessao, "LOGIN_BLOQUEADO") if e.usuario_login == "contador"]
    assert len(bloqueios) == 1  # um por janela, não um por tentativa


def test_acerto_zera_o_contador_do_usuario(nav):
    for _ in range(4):
        entrar(nav, "analista", "errada")
    assert entrar(nav).status_code == 200
    for _ in range(4):
        assert entrar(nav, "analista", "errada").status_code == 401


def test_limite_por_ip_cobre_varias_contas(nav, monkeypatch):
    monkeypatch.setattr(get_settings(), "login_max_falhas_ip", 3)
    for i in range(3):
        entrar(nav, f"inexistente{i}", "x")
    assert entrar(nav, "outra.conta", "x").status_code == 429


# ------------------------------------------------------------------ Redis fora: falha fechada

def test_sem_redis_ninguem_entra(nav, contador):
    redis_cliente.definir_cliente(RedisFora())
    assert entrar(nav).status_code == 503
    assert nav.get("/api/auth/me", headers=contador).status_code == 503


# ------------------------------------------------------------------ IP do cliente

REDE = [__import__("ipaddress").ip_network("76.76.21.0/24")]


@pytest.mark.parametrize("cliente,xff,confiar,proxies,esperado", [
    ("10.0.0.5", "1.2.3.4", False, [], "10.0.0.5"),                       # sem proxy: ignora o cabeçalho
    ("10.0.0.5", "6.6.6.6, 200.1.1.1", True, [], "200.1.1.1"),           # o Render acrescenta o real à direita
    ("10.0.0.5", "6.6.6.6, 200.1.1.1, 76.76.21.9", True, REDE, "200.1.1.1"),  # pula o salto da Vercel
    ("10.0.0.5", None, True, [], "10.0.0.5"),
    ("10.0.0.5", "lixo", True, [], "10.0.0.5"),
])
def test_resolver_ip(cliente, xff, confiar, proxies, esperado):
    assert resolver_ip(cliente, xff, confiar, proxies) == esperado
