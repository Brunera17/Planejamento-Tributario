"""Onde ficam os arquivos enviados e os relatórios, já cifrados (app/services/cripto.py): pasta local ou Google Drive.

As duas implementações têm a mesma interface: `gravar`, `ler`, `existe`, `apagar` e `nomes`, sempre por
pasta lógica ("documentos" ou "relatorios") e nome do arquivo. ARMAZENAMENTO=disco (padrão) usa UPLOAD_DIR;
ARMAZENAMENTO=drive usa a pasta do Drive preparada por `python -m app.services.armazenamento --autorizar`.

O Drive entra pela conta do escritório (OAuth com token de atualização, escopo drive.file: o app só enxerga o que
ele mesmo criou). Conta de serviço não serve: ela não tem espaço próprio no Drive de uma conta comum.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from app.core.config import get_settings
from app.core.erros import ErroNegocio

PASTAS = ("documentos", "relatorios")


class ErroArmazenamento(ErroNegocio):
    def __init__(self, detalhe: str):
        super().__init__(f"Armazenamento de arquivos indisponível ({detalhe}); tente de novo em instantes", 503)


class Disco:
    def __init__(self, base: str | Path):
        self.base = Path(base)

    def _arq(self, pasta: str, nome: str) -> Path:
        destino = self.base / pasta
        destino.mkdir(parents=True, exist_ok=True)
        return destino / Path(nome).name

    def gravar(self, pasta: str, nome: str, dados: bytes) -> None:
        arq = self._arq(pasta, nome)
        tmp = arq.with_name(f".{arq.name}.{os.getpid()}.tmp")
        tmp.write_bytes(dados)
        os.replace(tmp, arq)  # troca atômica: nunca fica meio arquivo

    def ler(self, pasta: str, nome: str) -> bytes:
        return self._arq(pasta, nome).read_bytes()

    def existe(self, pasta: str, nome: str) -> bool:
        return self._arq(pasta, nome).is_file()

    def apagar(self, pasta: str, nome: str) -> None:
        self._arq(pasta, nome).unlink(missing_ok=True)

    def nomes(self, pasta: str) -> list[str]:
        d = self.base / pasta
        return sorted(a.name for a in d.iterdir() if a.is_file() and not a.name.startswith(".")) if d.exists() else []


# ------------------------------------------------------------------ Google Drive (API v3, sem dependência nova)

TOKEN = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
PASTA_MIME = "application/vnd.google-apps.folder"
ESCOPO = "https://www.googleapis.com/auth/drive.file"
JSON = {"Content-Type": "application/json; charset=UTF-8"}


def _literal(texto: str) -> str:
    return "'" + texto.replace("\\", "\\\\").replace("'", "\\'") + "'"


class Drive:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str, raiz: str):
        self.client_id, self.client_secret, self.refresh_token, self.raiz = client_id, client_secret, refresh_token, raiz
        self._token, self._expira = "", 0.0
        self._pastas: dict[str, str] = {}
        self._trava = threading.Lock()

    def _http(self, metodo: str, url: str, corpo: bytes | None = None, cabecalhos: dict | None = None) -> tuple[bytes, dict]:
        req = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos or {})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise FileNotFoundError(url) from e
            raise ErroArmazenamento(f"Google Drive respondeu {e.code}") from e
        except urllib.error.URLError as e:
            raise ErroArmazenamento("Google Drive fora do ar") from e

    def _api(self, metodo: str, url: str, corpo: bytes | None = None, cabecalhos: dict | None = None) -> tuple[bytes, dict]:
        with self._trava:
            if time.monotonic() >= self._expira:
                r = json.loads(self._http("POST", TOKEN, urlencode({
                    "client_id": self.client_id, "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token, "grant_type": "refresh_token"}).encode(),
                    {"Content-Type": "application/x-www-form-urlencoded"})[0])
                self._token, self._expira = r["access_token"], time.monotonic() + int(r["expires_in"]) - 60
            token = self._token
        return self._http(metodo, url, corpo, {**(cabecalhos or {}), "Authorization": f"Bearer {token}"})

    def _buscar(self, pai: str, nome: str | None = None, pasta: bool = False) -> list[dict]:
        q = [f"{_literal(pai)} in parents", "trashed = false"]
        if nome is not None:
            q.append(f"name = {_literal(nome)}")
        if pasta:
            q.append(f"mimeType = '{PASTA_MIME}'")
        achados, pagina = [], None
        while True:
            params = {"q": " and ".join(q), "fields": "nextPageToken,files(id,name)", "pageSize": 1000}
            if pagina:
                params["pageToken"] = pagina
            r = json.loads(self._api("GET", f"{API}?{urlencode(params)}")[0])
            achados += r.get("files", [])
            pagina = r.get("nextPageToken")
            if not pagina:
                return achados

    def _pasta(self, pasta: str) -> str:
        # as subpastas são criadas uma vez, no --autorizar: criar aqui deixaria dois processos com pastas duplicadas
        if pasta not in self._pastas:
            achadas = self._buscar(self.raiz, pasta, pasta=True)
            if not achadas:
                raise ErroArmazenamento(f"pasta '{pasta}' não encontrada no Drive; rode --autorizar")
            self._pastas[pasta] = achadas[0]["id"]
        return self._pastas[pasta]

    def _id(self, pasta: str, nome: str) -> str | None:
        achados = self._buscar(self._pasta(pasta), nome)
        return achados[0]["id"] if achados else None

    def gravar(self, pasta: str, nome: str, dados: bytes) -> None:
        # envio "resumable": serve para qualquer tamanho (o multipart para em 5 MB)
        fid = self._id(pasta, nome)
        if fid:  # recifrar: o arquivo continua o mesmo, só o conteúdo muda
            inicio = self._api("PATCH", f"{UPLOAD}/{fid}?uploadType=resumable", b"{}", JSON)
        else:
            meta = {"name": nome, "parents": [self._pasta(pasta)]}
            inicio = self._api("POST", f"{UPLOAD}?uploadType=resumable", json.dumps(meta).encode(), JSON)
        sessao = {k.lower(): v for k, v in inicio[1].items()}["location"]
        self._api("PUT", sessao, dados, {"Content-Type": "application/octet-stream"})

    def ler(self, pasta: str, nome: str) -> bytes:
        fid = self._id(pasta, nome)
        if fid is None:
            raise FileNotFoundError(nome)
        return self._api("GET", f"{API}/{fid}?alt=media")[0]

    def existe(self, pasta: str, nome: str) -> bool:
        return self._id(pasta, nome) is not None

    def apagar(self, pasta: str, nome: str) -> None:
        fid = self._id(pasta, nome)
        if fid:
            self._api("DELETE", f"{API}/{fid}")

    def nomes(self, pasta: str) -> list[str]:
        return sorted(f["name"] for f in self._buscar(self._pasta(pasta)))

    def criar_pasta(self, nome: str, pai: str | None = None) -> str:
        meta = {"name": nome, "mimeType": PASTA_MIME, **({"parents": [pai]} if pai else {})}
        return json.loads(self._api("POST", f"{API}?fields=id", json.dumps(meta).encode(), JSON)[0])["id"]


@lru_cache
def atual() -> Disco | Drive:
    s = get_settings()
    if s.armazenamento == "drive":
        return Drive(s.drive_client_id, s.drive_client_secret, s.drive_refresh_token, s.drive_pasta_id)
    return Disco(s.upload_dir)


# ------------------------------------------------------------------ preparação (uma vez, no computador de quem é dono da conta)

def _autorizar() -> None:
    """Abre o navegador, recebe a autorização da conta do Google, cria a pasta Planejador com as subpastas e
    imprime as variáveis para o Render. Precisa de DRIVE_CLIENT_ID e DRIVE_CLIENT_SECRET (cliente OAuth do tipo
    "Aplicativo para computador", com o app publicado como "Em produção": no modo Teste o token expira em 7 dias)."""
    s = get_settings()
    if not (s.drive_client_id and s.drive_client_secret):
        raise SystemExit("Defina DRIVE_CLIENT_ID e DRIVE_CLIENT_SECRET antes de autorizar")
    estado, recebido = secrets.token_urlsafe(16), {}

    class Resposta(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 – nome exigido pelo http.server
            recebido.update({k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Pode fechar esta aba e voltar ao terminal.".encode())

        def log_message(self, *_):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), Resposta)
    retorno = f"http://127.0.0.1:{servidor.server_port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": s.drive_client_id, "redirect_uri": retorno, "response_type": "code", "scope": ESCOPO,
        "access_type": "offline", "prompt": "consent", "state": estado})
    print(f"Abrindo o navegador. Se não abrir, acesse:\n{url}\n")
    webbrowser.open(url)
    servidor.handle_request()
    if recebido.get("state") != estado or "code" not in recebido:
        raise SystemExit(f"Autorização recusada ou inválida: {recebido.get('error', 'sem código')}")
    drive = Drive(s.drive_client_id, s.drive_client_secret, "", "")
    r = json.loads(drive._http("POST", TOKEN, urlencode({
        "client_id": s.drive_client_id, "client_secret": s.drive_client_secret, "code": recebido["code"],
        "redirect_uri": retorno, "grant_type": "authorization_code"}).encode(),
        {"Content-Type": "application/x-www-form-urlencoded"})[0])
    if "refresh_token" not in r:
        raise SystemExit("O Google não devolveu o token de atualização; remova o acesso do app na conta e tente de novo")
    drive.refresh_token = r["refresh_token"]
    raiz = drive.criar_pasta("Planejador")
    for pasta in PASTAS:
        drive.criar_pasta(pasta, raiz)
    print("Guarde no gerenciador de senhas e preencha no Render:\n")
    print("ARMAZENAMENTO=drive")
    print(f"DRIVE_REFRESH_TOKEN={r['refresh_token']}")
    print(f"DRIVE_PASTA_ID={raiz}")


def _importar_pasta(origem: str) -> None:
    """Migração: sobe os arquivos de uma pasta de uploads (como o disco do Render) para o armazenamento atual."""
    disco, destino = Disco(origem), atual()
    for pasta in PASTAS:
        ja = set(destino.nomes(pasta))
        novos = [n for n in disco.nomes(pasta) if n not in ja]
        for nome in novos:
            destino.gravar(pasta, nome, disco.ler(pasta, nome))
        print(f"{pasta}: {len(novos)} enviado(s), {len(ja)} já estava(m) lá")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Armazenamento dos arquivos")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--autorizar", action="store_true", help="autoriza a conta do Google e cria as pastas no Drive")
    g.add_argument("--importar-pasta", metavar="PASTA", help="sobe os arquivos de uma pasta de uploads")
    a = p.parse_args()
    _autorizar() if a.autorizar else _importar_pasta(a.importar_pasta)
