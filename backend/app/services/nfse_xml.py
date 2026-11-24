"""Leitura de XML de NFS-e: padrão nacional (infNFSe/DPS) e padrão municipal ABRASF (CompNfse/InfNfse).

Os nomes das tags são procurados sem o namespace, que muda de prefeitura para prefeitura. Um XML pode trazer várias
notas (a consulta de lote da prefeitura devolve uma lista).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass
class ServicoLido:
    chave: str
    numero: str
    competencia: str  # AAAA-MM
    valor: Decimal  # valor do serviço (receita bruta), antes de retenções e deduções
    cnpj_prestador: str
    cnpj_tomador: str | None
    cancelada: bool = False
    descricao: str = ""
    iss_retido: bool = False  # retido pelo tomador ou intermediário: sai do DAS


def _no(raiz, *nomes: str):
    for nome in nomes:
        achados = raiz.xpath(f".//*[local-name()='{nome}']")
        if achados:
            return achados[0]
    return None


def _txt(raiz, *nomes: str) -> str:
    no = _no(raiz, *nomes)
    return (no.text or "").strip() if no is not None else ""


def _cnpj(raiz, *blocos: str) -> str | None:
    for bloco in blocos:
        no = _no(raiz, bloco)
        if no is not None:
            doc = _txt(no, "CNPJ", "Cnpj", "CPF", "Cpf")
            if doc:
                return re.sub(r"\D", "", doc)
    return None


def _competencia(*textos: str) -> str:
    for t in textos:
        m = re.match(r"(\d{4})-?(\d{2})", t)
        if m and 1 <= int(m[2]) <= 12:
            return f"{m[1]}-{m[2]}"
    raise ValueError("NFS-e sem data de competência ou de emissão")


def _valor(t: str) -> Decimal:
    try:
        return Decimal(t)
    except InvalidOperation as e:
        raise ValueError("NFS-e sem o valor do serviço") from e


def ler(raiz) -> list[ServicoLido]:
    notas = []
    for inf in raiz.xpath(".//*[local-name()='infNFSe'] | self::*[local-name()='infNFSe']"):  # padrão nacional
        prest = _cnpj(inf, "emit", "prest")
        if not prest:
            raise ValueError("NFS-e sem o CNPJ do prestador")
        chave = re.sub(r"\D", "", inf.get("Id", ""))
        numero = _txt(inf, "nNFSe")
        notas.append(ServicoLido(
            chave=chave or f"{prest}-{numero}", numero=numero,
            competencia=_competencia(_txt(inf, "dCompet"), _txt(inf, "dhEmi"), _txt(inf, "dhProc")),
            valor=_valor(_txt(inf, "vServ")), cnpj_prestador=prest, cnpj_tomador=_cnpj(inf, "toma"),
            descricao=_txt(inf, "xDescServ") or _txt(inf, "xTribNac"),
            iss_retido=_txt(inf, "tpRetISSQN") in ("2", "3")))  # 1 = não retido
    for inf in raiz.xpath(".//*[local-name()='InfNfse']"):  # ABRASF
        prest = _cnpj(inf, "PrestadorServico", "Prestador", "IdentificacaoPrestador")
        if not prest:
            raise ValueError("NFS-e sem o CNPJ do prestador")
        numero = _txt(inf, "Numero")
        comp = inf.getparent().getparent() if inf.getparent() is not None else None  # CompNfse
        cancelada = comp is not None and _no(comp, "NfseCancelamento") is not None
        notas.append(ServicoLido(
            chave=f"{prest}-{numero}", numero=numero,
            competencia=_competencia(_txt(inf, "Competencia"), _txt(inf, "DataEmissao")),
            valor=_valor(_txt(inf, "ValorServicos")), cnpj_prestador=prest,
            cnpj_tomador=_cnpj(inf, "TomadorServico", "Tomador"), cancelada=cancelada,
            descricao=_txt(inf, "Discriminacao"), iss_retido=_txt(inf, "IssRetido") == "1"))  # 1 = sim, 2 = não
    return notas

