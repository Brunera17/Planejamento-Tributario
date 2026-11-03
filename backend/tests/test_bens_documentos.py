"""Bens próprios e documentos: regras, permissões, armazenamento e efeito no progresso."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Empresa, Planejamento
from app.seeds.exemplo import CNPJ, carregar_exemplo
from app.services import documentos

PDF = b"%PDF-1.7 teste"
BEM = {"tipo": "VEICULOS", "descricao": "Caminhonete", "data_aquisicao": "2024-05-10", "valor": "45000.00"}


@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "BENS E DOCS LTDA", "cnpj": "27.865.757/0001-02", "regime_tributario": "LUCRO_REAL"}).json()
    return cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-01", "competencia_final": "2026-02"}).json()["id"]


def bloco(cliente, h, pid, codigo):
    blocos = cliente.get(f"/api/planejamentos/{pid}/progresso", headers=h).json()["blocos"]
    return next(b for b in blocos if b["codigo"] == codigo)


@pytest.mark.parametrize("campo,valor", [
    ("valor", "1200.00"),
    ("data_aquisicao", (date.today() + timedelta(days=1)).isoformat()),
    ("tipo", "BARCO"),
])
def test_bem_invalido(cliente, analista, pid, campo, valor):
    r = cliente.post(f"/api/planejamentos/{pid}/bens", headers=analista, json={**BEM, campo: valor})
    assert r.status_code == 422 and campo in r.json()["campos"]


def test_ciclo_do_bem(cliente, analista, pid):
    url = f"/api/planejamentos/{pid}/bens"
    assert cliente.put(f"/api/planejamentos/{pid}/sem-bens?sem_bens=true", headers=analista).status_code == 204
    assert bloco(cliente, analista, pid, "BENS")["preenchidos"] == 1

    b = cliente.post(url, headers=analista, json=BEM).json()
    dados = cliente.get(url, headers=analista).json()
    assert dados["sem_bens"] is False and len(dados["bens"]) == 1  # cadastrar desfaz a declaração
    assert cliente.put(f"/api/planejamentos/{pid}/sem-bens?sem_bens=true", headers=analista).status_code == 409

    r = cliente.put(f"{url}/{b['id']}", headers=analista, json={**BEM, "descricao": "Furgão"})
    assert r.json()["descricao"] == "Furgão"
    assert cliente.delete(f"{url}/{b['id']}", headers=analista).status_code == 204
    assert bloco(cliente, analista, pid, "BENS")["preenchidos"] == 0


def test_nao_altera_bem_de_outra_empresa(cliente, contador, pid):
    outra = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "OUTRA LTDA", "cnpj": "11.444.777/0001-61", "regime_tributario": "LUCRO_REAL"})
    emp = outra.json() if outra.status_code == 201 else cliente.get("/api/empresas?busca=11444777", headers=contador).json()[0]
    pl = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2025-01", "competencia_final": "2025-01"}).json()["id"]
    b = cliente.post(f"/api/planejamentos/{pl}/bens", headers=contador, json=BEM).json()
    assert cliente.delete(f"/api/planejamentos/{pid}/bens/{b['id']}", headers=contador).status_code == 404


def enviar(cliente, h, pid, nome, conteudo, comp="2026-01", tipo=1):
    return cliente.post(f"/api/planejamentos/{pid}/documentos/{comp}/{tipo}", headers=h, files={"arquivo": (nome, conteudo)})


@pytest.mark.parametrize("nome,conteudo,status", [
    ("virus.exe", b"MZ", 415),
    ("falso.pdf", b"nao sou pdf", 415),
    ("vazio.pdf", b"", 422),
    ("binario.csv", b"a\0b", 415),
    ("grande.pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024), 413),
])
def test_arquivo_recusado(cliente, analista, pid, nome, conteudo, status):
    assert enviar(cliente, analista, pid, nome, conteudo).status_code == status


def test_envio_substituicao_e_download(cliente, analista, pid):
    r = enviar(cliente, analista, pid, "extrato.pdf", PDF)
    assert r.status_code == 201 and r.json()["arquivo"] == "extrato.pdf"
    doc_id = r.json()["id"]
    antes = len(list(documentos.pasta().iterdir()))

    assert enviar(cliente, analista, pid, "extrato-v2.pdf", PDF + b"2").json()["id"] == doc_id
    assert len(list(documentos.pasta().iterdir())) == antes  # o arquivo anterior foi apagado

    baixado = cliente.get(f"/api/planejamentos/{pid}/documentos/{doc_id}/download", headers=analista)
    assert baixado.content == PDF + b"2" and "extrato-v2.pdf" in baixado.headers["content-disposition"]
    assert bloco(cliente, analista, pid, "DOCUMENTOS")["preenchidos"] == 1


def test_nao_se_aplica_exige_justificativa_e_substitui_arquivo(cliente, analista, pid):
    url = f"/api/planejamentos/{pid}/documentos/2026-01/1/nao-se-aplica"
    assert cliente.put(url, headers=analista, json={"justificativa": ""}).status_code == 422
    assert cliente.put(url, headers=analista, json={"justificativa": "Empresa sem conta bancária"}).status_code == 204
    d = cliente.get(f"/api/planejamentos/{pid}/documentos", headers=analista).json()
    doc = next(x for x in d["documentos"] if x["tipo_documento_id"] == 1)
    assert doc["nao_se_aplica"] and doc["arquivo"] is None and doc["justificativa"] == "Empresa sem conta bancária"
    assert cliente.delete(f"/api/planejamentos/{pid}/documentos/{doc['id']}", headers=analista).status_code == 204
    assert bloco(cliente, analista, pid, "DOCUMENTOS")["preenchidos"] == 0


def test_mes_conferido_nao_aceita_alteracao(cliente, fabrica_sessao, contador):
    with fabrica_sessao() as db:
        carregar_exemplo(db)
        db.commit()
        p = db.scalar(select(Planejamento).join(Empresa).where(Empresa.cnpj == CNPJ))
    assert enviar(cliente, contador, p.id, "a.pdf", PDF, comp="2026-06").status_code == 409
    d = cliente.get(f"/api/planejamentos/{p.id}/documentos", headers=contador).json()
    assert d["competencias"][0] == {"competencia": "2026-06", "editavel": False}


def test_lista_mostra_quando_chegaram_todos_os_documentos(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "DOCS COMPLETOS LTDA", "cnpj": "60.701.190/0001-04", "regime_tributario": "LUCRO_REAL"}).json()
    p = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-03", "competencia_final": "2026-03"}).json()
    tipos = cliente.get(f"/api/planejamentos/{p['id']}/documentos", headers=contador).json()["tipos"]
    assert p["documentos_faltando"] == len(tipos) and p["documentos_recebidos_em"] is None

    for t in tipos:
        r = cliente.put(f"/api/planejamentos/{p['id']}/documentos/2026-03/{t['id']}/nao-se-aplica", headers=contador,
                        json={"justificativa": "Não se aplica à empresa"})
        assert r.status_code == 204, r.text
    item = next(x for x in cliente.get("/api/planejamentos", headers=contador).json() if x["id"] == p["id"])
    assert item["documentos_faltando"] == 0 and item["documentos_recebidos_em"]
