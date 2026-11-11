"""Preparo da API ao acordar: só pula migrações e cargas quando esta versão já foi preparada no banco."""
from sqlalchemy import create_engine

from app import implantacao
from app.models import MarcaImplantacao


def test_pula_o_preparo_so_com_a_mesma_versao(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'b.db'}"
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    assert not implantacao.pronta(url)  # fora do Render: prepara sempre
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc")
    assert not implantacao.pronta(url)  # banco sem a tabela: prepara
    MarcaImplantacao.__table__.create(create_engine(url))
    assert not implantacao.pronta(url)
    implantacao.marcar(url)
    assert implantacao.pronta(url)
    implantacao.marcar(url)  # marcar de novo não duplica a chave
    monkeypatch.setenv("RENDER_GIT_COMMIT", "def")
    assert not implantacao.pronta(url)  # deploy novo: prepara de novo
