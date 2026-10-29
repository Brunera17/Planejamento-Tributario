"""Relatório PDF: emissão, conteúdo, marca de preliminar, arquivamento com hash e permissões."""
import hashlib
import io

import pytest
from pypdf import PdfReader


@pytest.fixture(scope="module")
def sim(cliente, contador):
    pid = next(p["id"] for p in cliente.get("/api/planejamentos", headers=contador).json() if p["cnpj"] == "11222333000181")
    return cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()


def texto(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def test_analista_nao_emite(cliente, analista, sim):
    assert cliente.post(f"/api/simulacoes/{sim['id']}/relatorio-pdf", headers=analista, json={}).status_code == 403


def test_recomendacao_padrao(cliente, contador, sim):
    itens = cliente.get(f"/api/simulacoes/{sim['id']}/recomendacao", headers=contador).json()
    assert any("Lucro Presumido" in i for i in itens)


def test_emite_arquiva_e_baixa(cliente, contador, sim):
    r = cliente.post(f"/api/simulacoes/{sim['id']}/relatorio-pdf", headers=contador,
                     json={"recomendacao": ["Optar pelo Lucro Presumido em janeiro.", "  "]})
    assert r.status_code == 201, r.text
    rel = r.json()
    assert rel["preliminar"] is True
    assert rel["arquivo"].startswith("PLANEJAMENTO_11222333000181_202606-202608_")

    baixado = cliente.get(f"/api/relatorios/{rel['id']}/download", headers=contador)
    assert baixado.status_code == 200
    assert baixado.content[:5] == b"%PDF-"
    assert hashlib.sha256(baixado.content).hexdigest() == rel["hash_sha256"]

    conteudo = texto(baixado.content)
    for trecho in ["Lucro Presumido tem a menor carga", "R$ 59.765,84", "R$ 63.688,26", "PRELIMINAR",
                   "Página 1 de", "Optar pelo Lucro Presumido em janeiro.", "Memória de cálculo", "Fontes legais",
                   "Verificação por NCM", "8 de 18 NCMs precisam de revisão", "8708.80.00",
                   "11.222.333/0001-81"]:
        assert trecho in conteudo, trecho

    lista = cliente.get(f"/api/planejamentos/{sim['planejamento_id']}/relatorios", headers=contador).json()
    assert lista[0]["id"] == rel["id"] and lista[0]["gerado_por_nome"] == "Contador Demonstração"


def test_arquivo_alterado_e_recusado(cliente, contador, sim):
    from app.core.config import get_settings
    from pathlib import Path

    rel = cliente.post(f"/api/simulacoes/{sim['id']}/relatorio-pdf", headers=contador, json={}).json()
    arq = Path(get_settings().upload_dir) / "relatorios" / rel["arquivo"]
    arq.write_bytes(arq.read_bytes() + b"%adulterado")
    assert cliente.get(f"/api/relatorios/{rel['id']}/download", headers=contador).status_code == 409
