"""Preparo da API ao acordar: só pula migrações e cargas quando esta versão já foi preparada no banco."""
from sqlalchemy import create_engine

from app import implantacao
from app.models import MarcaImplantacao, Usuario


def test_pula_o_preparo_so_com_a_mesma_versao(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'b.db'}"
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    assert not implantacao.pronta(url)  # fora do Render: prepara sempre
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc")
    assert not implantacao.pronta(url)  # banco sem a tabela: prepara
    motor = create_engine(url)
    MarcaImplantacao.__table__.create(motor)
    Usuario.__table__.create(motor)
    assert not implantacao.pronta(url)
    implantacao.marcar(url)
    assert not implantacao.pronta(url)  # marcada, mas sem usuário: a carga ainda cria o primeiro
    with motor.begin() as c:
        c.execute(Usuario.__table__.insert().values(nome="A", usuario="a", senha_hash="x", perfil="CONTADOR"))
    assert implantacao.pronta(url)
    implantacao.marcar(url)  # marcar de novo não duplica a chave
    monkeypatch.setenv("RENDER_GIT_COMMIT", "def")
    assert not implantacao.pronta(url)  # deploy novo: prepara de novo
