"""Arquivos dos documentos do levantamento: validação do conteúdo e armazenamento."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.core.erros import ErroNegocio

# extensão -> assinatura inicial do arquivo (None = texto, sem assinatura)
ASSINATURAS: dict[str, bytes | None] = {
    ".pdf": b"%PDF-",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".xlsx": b"PK\x03\x04",
    ".csv": None,
}


def pasta() -> Path:
    destino = Path(get_settings().upload_dir) / "documentos"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def validar(nome: str, conteudo: bytes) -> str:
    """Devolve a extensão; confere formato, tamanho e se o conteúdo corresponde à extensão."""
    ext = Path(nome).suffix.lower()
    if ext not in ASSINATURAS:
        raise ErroNegocio("Envie o arquivo em PDF, XLSX, CSV, JPG ou PNG", 415, {"arquivo": "formato não aceito"})
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
    """Grava com nome gerado pelo sistema; o nome original fica só no banco."""
    nome = f"{uuid4().hex}{ext}"
    (pasta() / nome).write_bytes(conteudo)
    return nome


def apagar(arquivo: str | None) -> None:
    if arquivo:
        (pasta() / Path(arquivo).name).unlink(missing_ok=True)


def caminho(arquivo: str) -> Path:
    return pasta() / Path(arquivo).name
