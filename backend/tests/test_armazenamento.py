"""Armazenamento no Google Drive, contra um Drive falso em memória (sem rede): mesma interface do disco."""
import json
import re
from urllib.parse import parse_qs, urlsplit

import pytest

from app.services import armazenamento, cripto, documentos
from app.services.armazenamento import API, TOKEN, UPLOAD, Drive, ErroArmazenamento

PDF = b"%PDF-1.7 extrato sigiloso"


class DriveFalso(Drive):
    def __init__(self, subpastas=armazenamento.PASTAS):
        super().__init__("cliente", "segredo", "refresh", "raiz")
        self.itens = {"raiz": {"name": "Planejador", "pai": None, "pasta": True}}
        for p in subpastas:
            self.itens[f"id-{p}"] = {"name": p, "pai": "raiz", "pasta": True}
        self.conteudo: dict[str, bytes] = {}
        self.tokens = 0
        self._seq = 0

    def _novo(self, meta, pasta=False):
        self._seq += 1
        fid = f"f{self._seq}"
        self.itens[fid] = {"name": meta["name"], "pai": (meta.get("parents") or [None])[0], "pasta": pasta}
        return fid

    def _http(self, metodo, url, corpo=None, cabecalhos=None):
        u = urlsplit(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        base = f"{u.scheme}://{u.netloc}{u.path}"
        if url == TOKEN:
            self.tokens += 1
            return json.dumps({"access_token": f"t{self.tokens}", "expires_in": 3600}).encode(), {}
        assert cabecalhos["Authorization"] == f"Bearer t{self.tokens}"
        if base.startswith("https://sessao/"):
            assert metodo == "PUT"
            self.conteudo[base.rsplit("/", 1)[1]] = corpo
            return b"{}", {}
        if base == API and metodo == "GET":
            consulta = q["q"]
            pai = re.search(r"'([^']*)' in parents", consulta).group(1)
            nome = re.search(r"name = '((?:[^'\\]|\\.)*)'", consulta)
            nome = nome and re.sub(r"\\(.)", r"\1", nome.group(1))
            so_pasta = "mimeType" in consulta
            achados = [{"id": i, "name": x["name"]} for i, x in self.itens.items()
                       if x["pai"] == pai and (nome is None or x["name"] == nome) and (not so_pasta or x["pasta"])]
            return json.dumps({"files": achados}).encode(), {}
        if base == API and metodo == "POST":
            meta = json.loads(corpo)
            return json.dumps({"id": self._novo(meta, pasta=True)}).encode(), {}
        if base == UPLOAD and metodo == "POST":
            return b"", {"Location": f"https://sessao/{self._novo(json.loads(corpo))}"}
        if base.startswith(UPLOAD + "/") and metodo == "PATCH":
            return b"", {"location": f"https://sessao/{base.rsplit('/', 1)[1]}"}
        fid = base.rsplit("/", 1)[1]
        if fid not in self.itens:
            raise FileNotFoundError(url)
        if metodo == "GET" and q.get("alt") == "media":
            return self.conteudo[fid], {}
        if metodo == "DELETE":
            del self.itens[fid]
            self.conteudo.pop(fid, None)
            return b"", {}
        raise AssertionError(f"chamada inesperada: {metodo} {url}")


def test_drive_tem_a_mesma_interface_do_disco():
    d = DriveFalso()
    grande = b"x" * (6 * 1024 * 1024)  # passa do limite do multipart (5 MB): o envio é sempre resumable
    d.gravar("documentos", "a.pdf", PDF)
    d.gravar("relatorios", "r.pdf", grande)
    assert d.existe("documentos", "a.pdf") and not d.existe("relatorios", "a.pdf")
    assert d.ler("documentos", "a.pdf") == PDF and d.ler("relatorios", "r.pdf") == grande
    d.gravar("documentos", "a.pdf", b"novo")  # regravar troca o conteúdo, sem criar outro arquivo
    assert d.nomes("documentos") == ["a.pdf"] and d.ler("documentos", "a.pdf") == b"novo"
    d.apagar("documentos", "a.pdf")
    d.apagar("documentos", "a.pdf")  # apagar de novo não falha, como no disco
    assert not d.existe("documentos", "a.pdf")
    with pytest.raises(FileNotFoundError):
        d.ler("documentos", "a.pdf")
    assert d.tokens == 1  # o token de acesso é reaproveitado até perto de vencer


def test_token_renovado_ao_vencer():
    d = DriveFalso()
    d.existe("documentos", "a.pdf")
    d._expira = 0
    d.existe("documentos", "a.pdf")
    assert d.tokens == 2


def test_nome_com_aspas_e_buscado_certo():
    d = DriveFalso()
    d.gravar("documentos", "d'água.pdf", PDF)
    assert d.ler("documentos", "d'água.pdf") == PDF


def test_subpasta_ausente_responde_503():
    d = DriveFalso(subpastas=("documentos",))
    with pytest.raises(ErroArmazenamento) as e:
        d.gravar("relatorios", "r.pdf", PDF)
    assert e.value.status == 503 and "--autorizar" in e.value.mensagem


@pytest.fixture
def drive(monkeypatch):
    d = DriveFalso()
    monkeypatch.setattr(armazenamento, "atual", lambda: d)
    return d


def test_documento_vai_cifrado_para_o_drive(cliente, contador, drive):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "DRIVE LTDA", "cnpj": "81520477009903", "regime_tributario": "LUCRO_REAL"}).json()
    pid = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-01", "competencia_final": "2026-01"}).json()["id"]
    r = cliente.post(f"/api/planejamentos/{pid}/documentos/2026-01/1", headers=contador, files={"arquivo": ("e.pdf", PDF)})
    assert r.status_code == 201, r.text
    [guardado] = drive.conteudo.values()
    assert cripto.eh_cifrado(guardado) and b"sigiloso" not in guardado
    baixado = cliente.get(f"/api/planejamentos/{pid}/documentos/{r.json()['id']}/download", headers=contador)
    assert baixado.status_code == 200 and baixado.content == PDF


def test_cifrar_existentes_no_drive(drive):
    drive.gravar("documentos", "antigo.pdf", PDF)  # enviado antes da criptografia
    assert cripto.cifrar_existentes() == (1, 0)
    assert cripto.eh_cifrado(drive.ler("documentos", "antigo.pdf")) and documentos.ler("antigo.pdf") == PDF
    assert cripto.cifrar_existentes() == (0, 1)


def test_importar_pasta_sobe_so_o_que_falta(drive, tmp_path, capsys):
    origem = armazenamento.Disco(tmp_path)
    origem.gravar("documentos", "a.pdf", b"A")
    origem.gravar("relatorios", "r.pdf", b"R")
    armazenamento._importar_pasta(str(tmp_path))
    armazenamento._importar_pasta(str(tmp_path))  # repetir não duplica
    assert drive.nomes("documentos") == ["a.pdf"] and drive.ler("relatorios", "r.pdf") == b"R"
    assert "0 enviado(s), 1 já estava(m) lá" in capsys.readouterr().out
