"""Criptografia dos arquivos em repouso: envelope AES-GCM, integridade, rotação, migração e downloads."""
import base64
import os

import pytest

from app.core.config import CHAVE_ARQUIVOS_DESENVOLVIMENTO, Settings, get_settings
from app.services import cripto, documentos
from app.services.cripto import ErroCripto

K1 = base64.b64encode(b"1" * 32).decode()
K2 = base64.b64encode(b"2" * 32).decode()
PDF = b"%PDF-1.7 documento sigiloso do cliente"
DEV = CHAVE_ARQUIVOS_DESENVOLVIMENTO  # arquivos dos outros testes, na mesma pasta


@pytest.fixture
def chave(monkeypatch):
    s = get_settings()

    def usar(atual=K1, kid="t1", antigas=""):
        monkeypatch.setattr(s, "chave_arquivos", atual)
        monkeypatch.setattr(s, "chave_arquivos_id", kid)
        monkeypatch.setattr(s, "chaves_arquivos_antigas", antigas)
    usar()
    return usar


# ------------------------------------------------------------------ envelope

def test_ida_e_volta_sem_texto_puro_no_cifrado(chave):
    blob = cripto.cifrar(PDF, b"a.pdf")
    assert blob.startswith(cripto.MARCA) and PDF not in blob and b"sigiloso" not in blob
    assert cripto.decifrar(blob, b"a.pdf") == PDF
    assert cripto.cifrar(PDF, b"a.pdf") != blob  # chave e nonce novos a cada gravação


@pytest.mark.parametrize("estragar", [
    lambda b: b[:-1] + bytes([b[-1] ^ 1]),        # conteúdo
    lambda b: b[:40] + bytes([b[40] ^ 1]) + b[41:],  # DEK cifrada
    lambda b: b[:-20],                             # truncado
])
def test_arquivo_adulterado_falha_em_vez_de_devolver_lixo(chave, estragar):
    with pytest.raises(ErroCripto):
        cripto.decifrar(estragar(cripto.cifrar(PDF, b"a.pdf")), b"a.pdf")


def test_arquivo_trocado_pelo_de_outro_documento_falha(chave):
    with pytest.raises(ErroCripto):
        cripto.decifrar(cripto.cifrar(PDF, b"a.pdf"), b"b.pdf")


def test_chave_errada_ou_desconhecida(chave):
    blob = cripto.cifrar(PDF, b"a.pdf")
    chave(atual=K2, kid="t1")  # mesmo id, outro material
    with pytest.raises(ErroCripto):
        cripto.decifrar(blob, b"a.pdf")
    chave(atual=K2, kid="t2")  # t1 não configurada
    with pytest.raises(ErroCripto, match="t1"):
        cripto.decifrar(blob, b"a.pdf")


def test_rotacao_le_com_a_antiga_e_recifra_so_o_cabecalho(chave):
    blob = cripto.cifrar(PDF, b"a.pdf")
    chave(atual=K2, kid="t2", antigas=f"t1:{K1},k1:{DEV}")
    assert cripto.decifrar(blob, b"a.pdf") == PDF
    novo = cripto.recifrar_cabecalho(blob, b"a.pdf")
    assert novo.endswith(blob[-(len(PDF) + 16):])  # conteúdo cifrado intocado
    chave(atual=K2, kid="t2")  # a antiga já pode sair
    assert cripto.decifrar(novo, b"a.pdf") == PDF


def test_campo_do_banco_amarrado_ao_contexto(chave):
    valor = cripto.cifrar_campo("JBSWY3DPEHPK3PXP", "mfa:1")
    assert "JBSWY3DP" not in valor and cripto.decifrar_campo(valor, "mfa:1") == "JBSWY3DPEHPK3PXP"
    with pytest.raises(ErroCripto):
        cripto.decifrar_campo(valor, "mfa:2")


def test_producao_exige_chave_de_arquivos():
    with pytest.raises(ValueError, match="CHAVE_ARQUIVOS"):
        Settings(database_url="postgresql://u:s@h/db", jwt_secret="x" * 40, redis_url="redis://r", chave_arquivos="")


@pytest.mark.parametrize("valor", ["nao-e-base64!", base64.b64encode(b"curta").decode()])
def test_chave_mal_formada_e_recusada(chave, valor):
    chave(atual=valor)
    with pytest.raises(ErroCripto):
        cripto.cifrar(PDF, b"a.pdf")


# ------------------------------------------------------------------ arquivos antigos e migração

def test_cifrar_existentes_e_idempotente_e_atomico(chave):
    pasta = documentos.pasta()
    antigo = pasta / "antigo-em-texto-puro.pdf"
    antigo.write_bytes(PDF)
    novos, _ = cripto.cifrar_existentes()
    assert novos >= 1 and cripto.eh_cifrado(antigo.read_bytes())
    assert documentos.ler(antigo.name) == PDF
    assert cripto.cifrar_existentes()[0] == 0
    assert not [a for a in os.listdir(pasta) if a.endswith(".tmp")]


def test_texto_puro_recusado_depois_da_migracao(chave, monkeypatch):
    arq = documentos.pasta() / "esquecido.pdf"
    arq.write_bytes(PDF)
    assert documentos.ler(arq.name) == PDF  # período de transição
    monkeypatch.setattr(get_settings(), "aceitar_arquivo_sem_cifra", False)
    with pytest.raises(ErroCripto):
        documentos.ler(arq.name)


def test_recifrar_existentes_passa_tudo_para_a_chave_nova(chave):
    nome = documentos.gravar(PDF, ".pdf")
    chave(atual=K2, kid="t2", antigas=f"t1:{K1},k1:{DEV}")
    assert cripto.recifrar_existentes() >= 1
    chave(atual=K2, kid="t2")
    assert documentos.ler(nome) == PDF


# ------------------------------------------------------------------ pela API

@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "CIFRADA LTDA", "cnpj": "81520477000876", "regime_tributario": "LUCRO_REAL"}).json()
    return cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-01", "competencia_final": "2026-01"}).json()["id"]


def test_documento_cifrado_no_disco_e_original_no_download(cliente, contador, pid, fabrica_sessao):
    from app.models import Documento
    r = cliente.post(f"/api/planejamentos/{pid}/documentos/2026-01/1", headers=contador,
                     files={"arquivo": ("extrato ação.pdf", PDF)})
    assert r.status_code == 201, r.text
    with fabrica_sessao() as db:
        arquivo = db.get(Documento, r.json()["id"]).arquivo
    no_disco = documentos.caminho(arquivo).read_bytes()
    assert cripto.eh_cifrado(no_disco) and b"sigiloso" not in no_disco
    baixado = cliente.get(f"/api/planejamentos/{pid}/documentos/{r.json()['id']}/download", headers=contador)
    assert baixado.status_code == 200 and baixado.content == PDF
    assert "filename*=utf-8''extrato%20a%C3%A7%C3%A3o.pdf" in baixado.headers["content-disposition"]
    assert baixado.headers["cache-control"] == "no-store"


def test_download_de_documento_adulterado_responde_409(cliente, contador, pid, fabrica_sessao):
    from app.models import Documento
    r = cliente.post(f"/api/planejamentos/{pid}/documentos/2026-01/2", headers=contador,
                     files={"arquivo": ("b.pdf", PDF)})
    with fabrica_sessao() as db:
        arq = documentos.caminho(db.get(Documento, r.json()["id"]).arquivo)
    dados = arq.read_bytes()
    arq.write_bytes(dados[:-1] + bytes([dados[-1] ^ 1]))
    assert cliente.get(f"/api/planejamentos/{pid}/documentos/{r.json()['id']}/download", headers=contador).status_code == 409
