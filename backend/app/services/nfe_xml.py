"""Leitura de XML de NF-e (layout 4.00), avulsos ou dentro de um .zip."""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from lxml import etree

NS = {"n": "http://www.portalfiscal.inf.br/nfe"}
ZERO = Decimal("0")


@dataclass
class ItemLido:
    n_item: int
    cod_produto: str
    descricao: str
    ncm: str
    cfop: int
    quantidade: Decimal
    vl_unitario: Decimal
    vl_produtos: Decimal
    vl_total: Decimal
    vl_icms: Decimal
    cst_pis: str | None = None
    orig_icms: str | None = None  # 0 nacional; 1, 2, 3 e 8 importados ou com conteúdo importado acima de 40%
    cst_icms: str | None = None  # CST (regime normal) ou CSOSN (Simples) do ICMS
    aliq_icms: Decimal | None = None  # pICMS destacado
    # ICMS-ST: retido pelo próprio fornecedor (vBCST/vICMSST) ou em etapa anterior (vBCSTRet/vICMSSTRet, CST 60 e CSOSN 500)
    bc_st: Decimal | None = None
    vl_icms_st: Decimal | None = None


@dataclass
class NotaLida:
    chave_acesso: str
    numero: str
    data_emissao: date
    tipo_nf: int  # 0 = entrada, 1 = saída
    cnpj_emitente: str
    cnpj_destinatario: str | None
    uf_emitente: str | None
    uf_destinatario: str | None
    crt_emitente: str | None = None  # 1 e 4 = Simples Nacional; 2 e 3 = regime normal
    consumidor_final: bool | None = None  # indFinal
    itens: list[ItemLido] = field(default_factory=list)

    @property
    def competencia(self) -> str:
        return f"{self.data_emissao:%Y-%m}"


def _txt(no, caminho: str, padrao: str = "") -> str:
    r = no.find(caminho, NS)
    return r.text.strip() if r is not None and r.text else padrao


def _dec(no, caminho: str) -> Decimal:
    v = _txt(no, caminho)
    return Decimal(v) if v else ZERO


def ler_xml(conteudo: bytes) -> NotaLida:
    raiz = etree.fromstring(conteudo, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    inf = raiz.find(".//n:infNFe", NS)
    if inf is None:
        raise ValueError("Arquivo não é uma NF-e (infNFe não encontrado)")
    ide = inf.find("n:ide", NS)
    emissao = _txt(ide, "n:dhEmi") or _txt(ide, "n:dEmi")
    nota = NotaLida(
        chave_acesso=inf.get("Id", "").removeprefix("NFe"),
        numero=_txt(ide, "n:nNF"),
        data_emissao=date.fromisoformat(emissao[:10]),
        tipo_nf=int(_txt(ide, "n:tpNF", "1")),
        cnpj_emitente=_txt(inf, "n:emit/n:CNPJ"),
        cnpj_destinatario=_txt(inf, "n:dest/n:CNPJ") or None,
        uf_emitente=_txt(inf, "n:emit/n:enderEmit/n:UF") or None,
        uf_destinatario=_txt(inf, "n:dest/n:enderDest/n:UF") or None,
        crt_emitente=_txt(inf, "n:emit/n:CRT") or None,
        consumidor_final=(_txt(ide, "n:indFinal") == "1") if _txt(ide, "n:indFinal") else None,
    )
    for det in inf.findall("n:det", NS):
        prod = det.find("n:prod", NS)
        vprod = _dec(prod, "n:vProd")
        total = vprod - _dec(prod, "n:vDesc") + _dec(prod, "n:vFrete") + _dec(prod, "n:vSeg") + _dec(prod, "n:vOutro")
        icms = det.find("n:imposto/n:ICMS", NS)
        vicms, orig, cst_icms, aliq, bc_st, icms_st = ZERO, None, None, None, None, None
        if icms is not None and len(icms):
            g = icms[0]
            vicms = _dec(g, "n:vICMS")
            orig = _txt(g, "n:orig") or None
            cst_icms = _txt(g, "n:CST") or _txt(g, "n:CSOSN") or None
            aliq = _dec(g, "n:pICMS") / 100 if _txt(g, "n:pICMS") else None
            for base, valor in (("n:vBCST", "n:vICMSST"), ("n:vBCSTRet", "n:vICMSSTRet")):
                if _txt(g, base):
                    bc_st, icms_st = _dec(g, base), _dec(g, valor)
                    break
        pis = det.find("n:imposto/n:PIS", NS)
        cst_pis = _txt(pis[0], "n:CST") if pis is not None and len(pis) else ""
        nota.itens.append(ItemLido(
            n_item=int(det.get("nItem", "0")),
            cod_produto=_txt(prod, "n:cProd"),
            descricao=_txt(prod, "n:xProd")[:200],
            ncm=_txt(prod, "n:NCM"),
            cfop=int(_txt(prod, "n:CFOP", "0")),
            quantidade=_dec(prod, "n:qCom"),
            vl_unitario=_dec(prod, "n:vUnCom"),
            vl_produtos=vprod,
            vl_total=total,
            vl_icms=vicms,
            cst_pis=cst_pis or None,
            orig_icms=orig,
            cst_icms=cst_icms,
            aliq_icms=aliq,
            bc_st=bc_st,
            vl_icms_st=icms_st,
        ))
    return nota


def ler_arquivos(nome: str, conteudo: bytes) -> tuple[list[NotaLida], list[str]]:
    """Retorna (notas lidas, erros por arquivo)."""
    notas, erros = [], []
    if nome.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            for info in z.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".xml"):
                    continue
                try:
                    notas.append(ler_xml(z.read(info)))
                except Exception as e:  # noqa: BLE001 – arquivo inválido vira linha do relatório
                    erros.append(f"{info.filename}: {e}")
    else:
        try:
            notas.append(ler_xml(conteudo))
        except Exception as e:  # noqa: BLE001
            erros.append(f"{nome}: {e}")
    return notas, erros
