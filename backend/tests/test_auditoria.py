"""Trilha de auditoria: eventos das rotas, corrente de hash, verificação, expurgo, exportação e falha fechada."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import session as db_session
from app.db.session import Base
from app.models import EventoAuditoria
from app.services import auditoria

PDF = b"%PDF-1.7 auditoria"


def eventos(fabrica, acao, **filtro):
    with fabrica() as db:
        q = select(EventoAuditoria).where(EventoAuditoria.acao == acao)
        for k, v in filtro.items():
            q = q.where(getattr(EventoAuditoria, k) == v)
        return db.scalars(q.order_by(EventoAuditoria.id)).all()


@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "AUDITADA LTDA", "cnpj": "62.047.315/0001-41", "regime_tributario": "LUCRO_REAL"}).json()
    return cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-01", "competencia_final": "2026-02"}).json()["id"]


@pytest.fixture
def banco_isolado(monkeypatch):
    """Corrente em banco próprio, para adulterar e expurgar sem afetar os outros testes."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_session, "SessionLocal", fabrica)
    return fabrica


def _ev(acao="LOGOUT", **extra):
    base = {k: None for k in auditoria.CAMPOS_HASH}
    return {**base, "acao": acao, "resultado": "OK", **extra}


# ------------------------------------------------------------------ eventos das rotas

def test_login_falho_e_bem_sucedido_ficam_registrados(cliente, fabrica_sessao):
    assert cliente.post("/api/auth/login", json={"usuario": "contador", "senha": "errada"}).status_code == 401
    assert cliente.post("/api/auth/login", json={"usuario": "ninguem", "senha": "x"}).status_code == 401
    assert cliente.post("/api/auth/login", json={"usuario": "contador", "senha": "demo123"},
                        headers={"User-Agent": "teste-auditoria"}).status_code == 200
    falha = eventos(fabrica_sessao, "LOGIN_FALHA", usuario_login="contador")[-1]
    assert falha.resultado == "FALHA" and falha.detalhes == {"motivo": "senha_incorreta"} and falha.ip
    assert eventos(fabrica_sessao, "LOGIN_FALHA", usuario_login="ninguem")[-1].detalhes == {"motivo": "usuario_inexistente"}
    ok = eventos(fabrica_sessao, "LOGIN_OK", usuario_login="contador")[-1]
    assert ok.usuario_id and ok.user_agent == "teste-auditoria"


def test_documento_enviado_e_baixado(cliente, analista, pid, fabrica_sessao):
    r = cliente.post(f"/api/planejamentos/{pid}/documentos/2026-01/1", headers=analista,
                     files={"arquivo": ("extrato.pdf", PDF)})
    doc_id = r.json()["id"]
    assert cliente.get(f"/api/planejamentos/{pid}/documentos/{doc_id}/download", headers=analista).status_code == 200
    env = eventos(fabrica_sessao, "DOCUMENTO_ENVIADO", recurso_id=doc_id)[-1]
    assert env.planejamento_id == pid and env.empresa_cnpj == "62047315000141"
    assert env.detalhes["arquivo"] == "extrato.pdf" and env.detalhes["bytes"] == len(PDF) and len(env.detalhes["sha256"]) == 64
    baixado = eventos(fabrica_sessao, "DOCUMENTO_BAIXADO", recurso_id=doc_id)[-1]
    assert baixado.usuario_login == "analista" and baixado.sessao_id and len(baixado.sessao_id) >= 16


def test_planejamento_aberto_uma_vez_por_sessao(cliente, contador, pid, fabrica_sessao):
    antes = len(eventos(fabrica_sessao, "PLANEJAMENTO_ABERTO", planejamento_id=pid))
    for _ in range(3):
        assert cliente.get(f"/api/planejamentos/{pid}", headers=contador).status_code == 200
    assert len(eventos(fabrica_sessao, "PLANEJAMENTO_ABERTO", planejamento_id=pid)) == antes + 1


def test_evento_nao_grava_quando_a_operacao_falha(cliente, contador, fabrica_sessao):
    antes = len(eventos(fabrica_sessao, "EMPRESA_CRIADA"))
    dados = {"razao_social": "DUPLICADA", "cnpj": "62.047.315/0001-41", "regime_tributario": "LUCRO_REAL"}
    assert cliente.post("/api/empresas", headers=contador, json=dados).status_code == 409
    assert len(eventos(fabrica_sessao, "EMPRESA_CRIADA")) == antes


def test_alteracoes_de_usuario(cliente, contador, fabrica_sessao):
    u = cliente.post("/api/usuarios", headers=contador, json={
        "nome": "Auditado", "usuario": "auditado", "senha": "senha-forte-1", "perfil": "ANALISTA"}).json()
    cliente.put(f"/api/usuarios/{u['id']}", headers=contador, json={
        "nome": "Auditado", "perfil": "CONTADOR", "ativo": False, "senha": "outra-senha-2"})
    for acao in ("USUARIO_CRIADO", "PERFIL_ALTERADO", "USUARIO_DESATIVADO", "SENHA_ALTERADA"):
        assert eventos(fabrica_sessao, acao, recurso_id=u["id"]), acao
    assert eventos(fabrica_sessao, "PERFIL_ALTERADO", recurso_id=u["id"])[-1].detalhes["perfil"] == ["ANALISTA", "CONTADOR"]


# ------------------------------------------------------------------ falha fechada

@pytest.fixture
def auditoria_fora(monkeypatch):
    def falhar(_eventos):
        raise RuntimeError("banco fora")
    monkeypatch.setattr(auditoria, "gravar", falhar)
    yield
    for arq in auditoria._pasta_contingencia().glob("*.jsonl"):
        arq.unlink()


def test_download_sem_auditoria_vira_503(cliente, analista, pid, auditoria_fora):
    envio = cliente.post(f"/api/planejamentos/{pid}/documentos/2026-02/1", headers=analista,
                             files={"arquivo": ("b.pdf", PDF)})
    assert envio.status_code == 201  # alteração: resposta original segue
    r = cliente.get(f"/api/planejamentos/{pid}/documentos/{envio.json()['id']}/download", headers=analista)
    assert r.status_code == 503 and "auditoria" in r.json()["erro"]


def test_alteracao_sem_auditoria_vai_para_contingencia(cliente, contador, auditoria_fora, monkeypatch):
    r = cliente.post("/api/auth/login", json={"usuario": "contador", "senha": "demo123"})
    assert r.status_code == 200  # a sessão foi criada: dizer 503 seria mentira
    assert auditoria.pendentes_na_contingencia() == 1
    assert cliente.get("/api/saude").json()["auditoria_pendente"] == 1
    linha = next(auditoria._pasta_contingencia().glob("*.jsonl")).read_text(encoding="utf-8")
    assert '"LOGIN_OK"' in linha and "_ocorrido_em" in linha


def test_contingencia_e_reprocessada_no_proximo_gravar(banco_isolado):
    auditoria.guardar_contingencia([_ev("EMPRESA_CRIADA")])
    auditoria.gravar([_ev("LOGOUT")])
    assert auditoria.pendentes_na_contingencia() == 0
    with banco_isolado() as db:
        acoes = [e.acao for e in db.scalars(select(EventoAuditoria).order_by(EventoAuditoria.id))]
        assert acoes == ["EMPRESA_CRIADA", "LOGOUT"] and auditoria.verificar(db, completo=True).ok


# ------------------------------------------------------------------ corrente e verificação

def test_corrente_integra_passa_e_cria_checkpoint(banco_isolado):
    auditoria.gravar([_ev(), _ev("LOGIN_OK", detalhes={"a": 1})])
    with banco_isolado() as db:
        r = auditoria.verificar(db)
        assert r.ok and r.verificados == 2
        auditoria.gravar([_ev()])
        r = auditoria.verificar(db)  # incremental: só o novo
        assert r.ok and r.verificados == 1


def test_conteudo_adulterado_e_detectado(banco_isolado):
    auditoria.gravar([_ev(), _ev("DOCUMENTO_BAIXADO", detalhes={"arquivo": "a.pdf"}), _ev()])
    with banco_isolado() as db:
        alvo = db.scalars(select(EventoAuditoria.id).order_by(EventoAuditoria.id)).all()[1]
        db.execute(update(EventoAuditoria).where(EventoAuditoria.id == alvo).values(usuario_login="outro"))
        db.commit()
        r = auditoria.verificar(db, completo=True)
    assert not r.ok and r.problema_evento == alvo and "alterado" in r.problema


def test_evento_removido_e_detectado(banco_isolado):
    auditoria.gravar([_ev(), _ev(), _ev()])
    with banco_isolado() as db:
        ids = db.scalars(select(EventoAuditoria.id).order_by(EventoAuditoria.id)).all()
        db.query(EventoAuditoria).filter(EventoAuditoria.id == ids[1]).delete()
        db.commit()
        r = auditoria.verificar(db, completo=True)
    assert not r.ok and r.problema_evento == ids[2] and "interrompida" in r.problema


def test_expurgo_mantem_a_corrente_verificavel(banco_isolado, monkeypatch):
    real = datetime

    class Relogio(datetime):
        agora = real.now(UTC) - timedelta(days=365 * 6)

        @classmethod
        def now(cls, tz=None):
            return cls.agora

    monkeypatch.setattr(auditoria, "datetime", Relogio)
    auditoria.gravar([_ev(), _ev()])  # há 6 anos
    Relogio.agora = real.now(UTC)
    auditoria.gravar([_ev("LOGIN_OK"), _ev()])  # hoje
    assert auditoria.expurgar() == 2
    with banco_isolado() as db:
        restantes = db.scalars(select(EventoAuditoria).order_by(EventoAuditoria.id)).all()
        assert [e.acao for e in restantes] == ["LOGIN_OK", "LOGOUT", "AUDITORIA_EXPURGO"]
        assert restantes[-1].detalhes["removidos"] == 2
        assert auditoria.verificar(db, completo=True).ok


def test_acao_desconhecida_e_recusada():
    with pytest.raises(ValueError):
        auditoria.auditar("QUALQUER_COISA")


# ------------------------------------------------------------------ consulta e exportação

def test_consulta_so_para_contador(cliente, analista, contador):
    assert cliente.get("/api/auditoria", headers=analista).status_code == 403
    r = cliente.get("/api/auditoria?acao=LOGIN_OK&limite=1", headers=contador).json()
    assert len(r["itens"]) == 1 and r["itens"][0]["acao"] == "LOGIN_OK"
    if r["proximo"]:
        seguinte = cliente.get(f"/api/auditoria?acao=LOGIN_OK&limite=1&antes_de={r['proximo']}", headers=contador).json()
        assert seguinte["itens"][0]["id"] < r["itens"][0]["id"]


def test_exportacao_csv_com_periodo_limitado(cliente, contador, fabrica_sessao):
    hoje = datetime.now(UTC).date()
    longo = cliente.get(f"/api/auditoria/exportar?desde={hoje - timedelta(days=400)}&ate={hoje}", headers=contador)
    assert longo.status_code == 422
    r = cliente.get(f"/api/auditoria/exportar?desde={hoje}&ate={hoje}&acao=LOGIN_OK", headers=contador)
    assert r.status_code == 200 and r.text.lstrip("﻿").startswith("id;momento;acao")
    assert "LOGIN_OK" in r.text
    assert eventos(fabrica_sessao, "AUDITORIA_EXPORTADA")


def test_verificar_pela_api(cliente, contador):
    r = cliente.get("/api/auditoria/verificar", headers=contador)
    assert r.status_code == 200 and r.json()["ok"] is True
