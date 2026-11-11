"""Criptografia dos arquivos em repouso (documentos e relatórios) e de campos sensíveis do banco.

Envelope: cada arquivo tem a própria chave (DEK, 256 bits, aleatória), cifrada pela chave mestra (KEK) da
variável CHAVE_ARQUIVOS. AES-256-GCM cifra e autentica: arquivo adulterado ou trocado pelo de outro documento
(o nome gerado entra como dado associado) falha na leitura em vez de devolver lixo.

Formato:
    "PTC1" | versão (1) | tamanho do id (1) | id da KEK | nonce da DEK (12) | DEK cifrada (48) | nonce (12) | conteúdo cifrado + tag (16)

Linha de comando (rodar com a mesma configuração da API):
    python -m app.services.cripto --gerar-chave        nova chave mestra (guarde fora do Render!)
    python -m app.services.cripto --cifrar-existentes  cifra os arquivos ainda em texto puro (idempotente)
    python -m app.services.cripto --recifrar-chaves    reescreve só o cabeçalho com a KEK atual (rotação)
"""
from __future__ import annotations

import argparse
import base64
import secrets
import struct
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

MARCA = b"PTC1"  # a única definição: pgdas.py e documentos.py importam daqui
VERSAO = 1
_NONCE = 12
_DEK_CIFRADA = 32 + 16  # 32 bytes + tag do GCM


class ErroCripto(Exception):
    """Arquivo adulterado, chave errada ou chave mestra desconhecida."""


@dataclass(frozen=True)
class Chave:
    id: str
    material: bytes


def _decodificar(texto: str, origem: str) -> bytes:
    try:
        chave = base64.b64decode(texto.strip(), validate=True)
    except ValueError as e:
        raise ErroCripto(f"{origem}: chave não está em base64") from e
    if len(chave) != 32:
        raise ErroCripto(f"{origem}: a chave precisa ter 32 bytes (256 bits)")
    return chave


def chave_atual() -> Chave:
    s = get_settings()
    return Chave(s.chave_arquivos_id, _decodificar(s.chave_arquivos_efetiva, "CHAVE_ARQUIVOS"))


def _chaves() -> dict[str, bytes]:
    """Atual + antigas (CHAVES_ARQUIVOS_ANTIGAS="id:base64,id:base64"), para ler durante a rotação."""
    s = get_settings()
    chaves = {}
    for item in filter(None, (x.strip() for x in s.chaves_arquivos_antigas.split(","))):
        kid, _, valor = item.partition(":")
        chaves[kid.strip()] = _decodificar(valor, f"CHAVES_ARQUIVOS_ANTIGAS ({kid.strip()})")
    atual = chave_atual()
    chaves[atual.id] = atual.material
    return chaves


def eh_cifrado(dados: bytes) -> bool:
    return dados[:4] == MARCA


def _aad_dek(kid: bytes, aad: bytes) -> bytes:
    return b"dek|" + kid + b"|" + aad


def cifrar(dados: bytes, aad: bytes) -> bytes:
    k = chave_atual()
    kid = k.id.encode()
    if not 0 < len(kid) < 256:
        raise ErroCripto("CHAVE_ARQUIVOS_ID precisa ter de 1 a 255 caracteres")
    dek = AESGCM.generate_key(bit_length=256)
    nonce_dek, nonce = secrets.token_bytes(_NONCE), secrets.token_bytes(_NONCE)
    dek_cifrada = AESGCM(k.material).encrypt(nonce_dek, dek, _aad_dek(kid, aad))
    corpo = AESGCM(dek).encrypt(nonce, dados, aad)
    return MARCA + struct.pack("BB", VERSAO, len(kid)) + kid + nonce_dek + dek_cifrada + nonce + corpo


def _abrir_cabecalho(blob: bytes) -> tuple[bytes, bytes, bytes, int]:
    """(id da KEK, nonce da DEK, DEK cifrada, início do nonce do conteúdo)."""
    if not eh_cifrado(blob) or len(blob) < 6:
        raise ErroCripto("não é um arquivo cifrado")
    versao, n = struct.unpack("BB", blob[4:6])
    if versao != VERSAO:
        raise ErroCripto(f"versão {versao} do formato não suportada")
    i = 6
    kid = blob[i:i + n]
    i += n
    nonce_dek = blob[i:i + _NONCE]
    i += _NONCE
    dek_cifrada = blob[i:i + _DEK_CIFRADA]
    i += _DEK_CIFRADA
    if len(blob) < i + _NONCE + 16:
        raise ErroCripto("arquivo cifrado truncado")
    return kid, nonce_dek, dek_cifrada, i


def _dek(kid: bytes, nonce_dek: bytes, dek_cifrada: bytes, aad: bytes) -> bytes:
    kek = _chaves().get(kid.decode(errors="replace"))
    if kek is None:
        raise ErroCripto(f"chave mestra '{kid.decode(errors='replace')}' não configurada")
    try:
        return AESGCM(kek).decrypt(nonce_dek, dek_cifrada, _aad_dek(kid, aad))
    except InvalidTag as e:
        raise ErroCripto("chave mestra errada ou cabeçalho adulterado") from e


def decifrar(blob: bytes, aad: bytes) -> bytes:
    kid, nonce_dek, dek_cifrada, i = _abrir_cabecalho(blob)
    dek = _dek(kid, nonce_dek, dek_cifrada, aad)
    try:
        return AESGCM(dek).decrypt(blob[i:i + _NONCE], blob[i + _NONCE:], aad)
    except InvalidTag as e:
        raise ErroCripto("conteúdo adulterado ou trocado de arquivo") from e


def recifrar_cabecalho(blob: bytes, aad: bytes) -> bytes:
    """Rotação: a DEK passa a ser cifrada pela KEK atual; o conteúdo não é tocado."""
    kid, nonce_dek, dek_cifrada, i = _abrir_cabecalho(blob)
    atual = chave_atual()
    if kid.decode() == atual.id:
        return blob
    dek = _dek(kid, nonce_dek, dek_cifrada, aad)
    novo_kid = atual.id.encode()
    novo_nonce = secrets.token_bytes(_NONCE)
    nova_dek = AESGCM(atual.material).encrypt(novo_nonce, dek, _aad_dek(novo_kid, aad))
    return MARCA + struct.pack("BB", VERSAO, len(novo_kid)) + novo_kid + novo_nonce + nova_dek + blob[i:]


# ------------------------------------------------------------------ campos do banco (ex.: segredo do MFA)

def cifrar_campo(valor: str, contexto: str) -> str:
    """Texto pequeno do banco: o contexto (ex.: "mfa:12") amarra o valor à linha — copiar para outra falha."""
    return base64.b64encode(cifrar(valor.encode(), contexto.encode())).decode()


def decifrar_campo(valor: str, contexto: str) -> str:
    return decifrar(base64.b64decode(valor), contexto.encode()).decode()


# ------------------------------------------------------------------ arquivos guardados (disco ou Drive)

def _arquivos():
    from app.services import armazenamento  # aqui: armazenamento -> erros, sem ciclo com este módulo
    a = armazenamento.atual()
    for pasta in armazenamento.PASTAS:
        for nome in a.nomes(pasta):
            yield a, pasta, nome


def cifrar_existentes() -> tuple[int, int]:
    """Cifra o que ainda está em texto puro. Idempotente. Devolve (cifrados, já cifrados)."""
    novos = ja = 0
    for a, pasta, nome in _arquivos():
        dados = a.ler(pasta, nome)
        if eh_cifrado(dados):
            ja += 1
            continue
        a.gravar(pasta, nome, cifrar(dados, nome.encode()))  # no disco, troca atômica
        novos += 1
    return novos, ja


def recifrar_existentes() -> int:
    n = 0
    for a, pasta, nome in _arquivos():
        dados = a.ler(pasta, nome)
        if not eh_cifrado(dados):
            continue
        novo = recifrar_cabecalho(dados, nome.encode())
        if novo is not dados:
            a.gravar(pasta, nome, novo)
            n += 1
    return n


def _principal() -> None:
    p = argparse.ArgumentParser(description="Criptografia dos arquivos em repouso")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--gerar-chave", action="store_true", help="imprime uma chave mestra nova (base64)")
    g.add_argument("--cifrar-existentes", action="store_true", help="cifra os arquivos ainda em texto puro")
    g.add_argument("--recifrar-chaves", action="store_true", help="passa a DEK de cada arquivo para a KEK atual")
    a = p.parse_args()
    if a.gerar_chave:
        print(base64.b64encode(secrets.token_bytes(32)).decode())
    elif a.cifrar_existentes:
        novos, ja = cifrar_existentes()
        print(f"{novos} arquivo(s) cifrado(s); {ja} já estava(m) cifrado(s)")
    else:
        print(f"{recifrar_existentes()} arquivo(s) passado(s) para a chave '{chave_atual().id}'")


if __name__ == "__main__":
    _principal()
