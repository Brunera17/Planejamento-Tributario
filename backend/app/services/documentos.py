"""Arquivos dos documentos do levantamento: validação do conteúdo e armazenamento."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.core.erros import ErroNegocio
from app.services import cripto

# extensão -> assinatura inicial do arquivo (None = texto, sem assinatura)
ASSINATURAS: dict[str, bytes | None] = {
    ".pdf": b"%PDF-",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".xlsx": b"PK\x03\x04",
    ".xls": b"\xd0\xcf\x11\xe0",
    ".zip": b"PK\x03\x04",
    ".csv": None,
    ".txt": None,  # SPED e arquivos de texto do sistema contábil
    ".xml": None,
}


def pasta() -> Path:
    destino = Path(get_settings().upload_dir) / "documentos"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def validar(nome: str, conteudo: bytes) -> str:
    """Devolve a extensão; confere formato, tamanho e se o conteúdo corresponde à extensão."""
    ext = Path(nome).suffix.lower()
    if ext not in ASSINATURAS:
        raise ErroNegocio("Envie o arquivo em PDF, XML, TXT, XLSX, XLS, CSV, ZIP, JPG ou PNG", 415, {"arquivo": "formato não aceito"})
    limite = get_settings().upload_max_mb
    if len(conteudo) > limite * 1024 * 1024:
        raise ErroNegocio(f"O arquivo tem mais de {limite} MB", 413, {"arquivo": "muito grande"})
    if not conteudo:
        raise ErroNegocio("O arquivo está vazio", 422, {"arquivo": "vazio"})
    assinatura = ASSINATURAS[ext]
    if (assinatura and not conteudo.startswith(assinatura)) or (assinatura is None and b"\0" in conteudo[:4096]):
        raise ErroNegocio(f"O conteúdo do arquivo não é um {ext[1:].upper()} válido", 415, {"arquivo": "conteúdo inválido"})
    return ext


def gravar(conteudo: bytes, ext: str) -> str:
    """Grava cifrado, com nome gerado pelo sistema; o nome original fica só no banco.
    O nome gerado entra como dado associado: o arquivo não pode ser trocado pelo de outro documento."""
    nome = f"{uuid4().hex}{ext}"
    (pasta() / nome).write_bytes(cripto.cifrar(conteudo, nome.encode()))
    return nome


def existe(arquivo: str | None) -> bool:
    return bool(arquivo) and caminho(arquivo).exists()


def ler(arquivo: str) -> bytes:
    """Conteúdo original do documento (decifrado). Arquivo de antes da criptografia ainda é aceito em texto puro
    enquanto ACEITAR_ARQUIVO_SEM_CIFRA estiver ligada (desligar depois de `cripto --cifrar-existentes`)."""
    return ler_arquivo(caminho(arquivo))


def ler_arquivo(arq: Path) -> bytes:
    dados = arq.read_bytes()
    if cripto.eh_cifrado(dados):
        return cripto.decifrar(dados, arq.name.encode())
    if get_settings().aceitar_arquivo_sem_cifra:
        return dados
    raise cripto.ErroCripto("arquivo sem criptografia recusado (ACEITAR_ARQUIVO_SEM_CIFRA=false)")


def apagar(arquivo: str | None) -> None:
    if arquivo:
        (pasta() / Path(arquivo).name).unlink(missing_ok=True)


def caminho(arquivo: str) -> Path:
    return pasta() / Path(arquivo).name
