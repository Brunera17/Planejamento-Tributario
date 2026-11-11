"""Resposta de download a partir de bytes (os arquivos ficam cifrados no disco: não dá para usar FileResponse)."""
from urllib.parse import quote

from fastapi.responses import Response


def anexo(conteudo: bytes, nome: str, media_type: str = "application/octet-stream") -> Response:
    """Mesmo Content-Disposition do FileResponse: nome com acento vai em filename* (RFC 5987)."""
    codificado = quote(nome)
    disposicao = (f"attachment; filename*=utf-8''{codificado}" if codificado != nome
                  else f'attachment; filename="{nome}"')
    return Response(conteudo, media_type=media_type,
                    headers={"Content-Disposition": disposicao, "Cache-Control": "no-store"})


def celula_csv(v):
    """Texto que a planilha leria como fórmula ganha um apóstrofo na frente (CSV injection): começa com
    caractere de controle (tab, CR, LF) ou com = + - @, mesmo depois de espaços."""
    if not isinstance(v, str) or not v:
        return v
    return "'" + v if v[0] in "\t\r\n" or v.lstrip()[:1] in ("=", "+", "-", "@") else v
