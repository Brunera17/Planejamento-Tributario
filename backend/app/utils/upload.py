"""Leitura de arquivos enviados com teto de tamanho."""
from fastapi import UploadFile

from app.core.erros import ErroNegocio

MB = 1024 * 1024


def ler_limitado(arquivo: UploadFile, limite_mb: int) -> bytes:
    """Lê no máximo limite + 1 byte: um envio maior é recusado sem entrar inteiro na memória.

    Síncrono de propósito: as rotas de upload são `def` e rodam no threadpool, sem travar o event loop.
    """
    conteudo = arquivo.file.read(limite_mb * MB + 1)
    if len(conteudo) > limite_mb * MB:
        raise ErroNegocio(f"Arquivo acima de {limite_mb} MB", 413, {"arquivo": "muito grande"})
    return conteudo
