"""Entradas hostis: senha acima do limite do bcrypt e texto que o Excel leria como fórmula."""
from datetime import UTC, datetime

from app.core.seguranca import conferir_senha, gerar_hash
from app.utils.download import celula_csv


def test_senha_acima_de_72_bytes_e_senha_errada_nao_erro_500(cliente):
    r = cliente.post("/api/auth/login", json={"usuario": "ninguem-longo", "senha": "ç" * 40})  # 80 bytes
    assert r.status_code == 401


def test_conferir_senha_longa_devolve_false():
    h = gerar_hash("a" * 72)
    assert conferir_senha("a" * 72, h)
    assert not conferir_senha("a" * 73, h)


def test_login_com_campos_gigantes_e_recusado(cliente):
    r = cliente.post("/api/auth/login", json={"usuario": "x" * 5000, "senha": "y"})
    assert r.status_code == 422


def test_cadastro_recusa_senha_com_acentos_acima_de_72_bytes(cliente, contador):
    r = cliente.post("/api/usuarios", headers=contador, json={
        "nome": "Teste Acento", "usuario": "teste.acento", "senha": "ã" * 40, "perfil": "ANALISTA"})
    assert r.status_code == 422 and "senha" in r.json()["campos"]


def test_celula_csv_neutraliza_formulas():
    assert celula_csv("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert celula_csv("@SUM(A1)") == "'@SUM(A1)"
    assert celula_csv("-2+3") == "'-2+3"
    assert celula_csv("\n=1+1") == "'\n=1+1"
    assert celula_csv("  =1+1") == "'  =1+1"
    assert celula_csv(" \t=1+1") == "' \t=1+1"
    assert celula_csv("Parafuso") == "Parafuso" and celula_csv("") == ""
    assert celula_csv(42) == 42 and celula_csv(None) is None


def test_exportacao_da_auditoria_neutraliza_login_hostil(cliente, contador):
    cliente.post("/api/auth/login", json={"usuario": '=HYPERLINK("http://x";"y")', "senha": "qualquer"})
    hoje = datetime.now(UTC).date()
    r = cliente.get(f"/api/auditoria/exportar?desde={hoje}&ate={hoje}&acao=LOGIN_FALHA", headers=contador)
    assert r.status_code == 200
    assert "'=HYPERLINK" in r.text
    assert ';=HYPERLINK' not in r.text and ';"=HYPERLINK' not in r.text


def test_documentacao_da_api_some_em_producao(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import Settings, get_settings
    from app.main import criar_app

    prod = Settings(database_url="postgresql://u:s@h/db", jwt_secret="x" * 40, redis_url="redis://r",
                    chave_arquivos="a" * 44)
    assert not prod.documentacao_ligada and Settings(documentacao_api=True, **prod.model_dump(
        include={"database_url", "jwt_secret", "redis_url", "chave_arquivos"})).documentacao_ligada
    monkeypatch.setattr("app.main.get_settings", lambda: prod)
    c = TestClient(criar_app())
    for rota in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(rota).status_code == 404
    assert get_settings().documentacao_ligada  # testes rodam em SQLite: docs continuam no desenvolvimento


def test_documentacao_api_vazia_vale_automatico(monkeypatch):
    from app.core.config import Settings
    monkeypatch.setenv("DOCUMENTACAO_API", "")
    assert Settings().documentacao_api is None
