"""NFS-e no mesmo envio do XML de NF-e: a receita de serviço do mês vira a soma das notas prestadas, sem contar duas vezes.
E a receita pelo CFOP do movimento mensal deixa de fora o lançamento de venda já em NFC-e (5929)."""
import io
import zipfile
from decimal import Decimal

import pytest

CNPJ = "73946182000161"
TOMADOR = "51830276000138"


def _nacional(n: int, prestador: str, valor: str, competencia: str = "2026-07-15") -> bytes:
    return (f'<?xml version="1.0" encoding="UTF-8"?><NFSe versao="1.00" xmlns="http://www.sped.fazenda.gov.br/nfse">'
            f'<infNFSe Id="NFS3550308{n:041d}"><nNFSe>{n}</nNFSe><emit><CNPJ>{prestador}</CNPJ></emit>'
            f"<valores><vLiq>{valor}</vLiq></valores><DPS><infDPS><dhEmi>{competencia}T10:00:00-03:00</dhEmi>"
            f"<dCompet>{competencia}</dCompet><prest><CNPJ>{prestador}</CNPJ></prest><toma><CNPJ>{TOMADOR}</CNPJ></toma>"
            f"<valores><vServPrest><vServ>{valor}</vServ></vServPrest></valores></infDPS></DPS></infNFSe></NFSe>").encode()


def _abrasf(n: int, valor: str, cancelada: bool = False) -> bytes:
    cancel = "<NfseCancelamento><Confirmacao/></NfseCancelamento>" if cancelada else ""
    return (f'<ConsultarNfseResposta xmlns="http://www.abrasf.org.br/nfse.xsd"><ListaNfse><CompNfse><Nfse><InfNfse>'
            f"<Numero>{n}</Numero><DataEmissao>2026-08-03T09:00:00</DataEmissao><PrestadorServico><IdentificacaoPrestador>"
            f"<CpfCnpj><Cnpj>{CNPJ}</Cnpj></CpfCnpj></IdentificacaoPrestador></PrestadorServico><DeclaracaoPrestacaoServico>"
            f"<InfDeclaracaoPrestacaoServico><Competencia>2026-08-01</Competencia><Servico><Valores>"
            f"<ValorServicos>{valor}</ValorServicos></Valores></Servico></InfDeclaracaoPrestacaoServico>"
            f"</DeclaracaoPrestacaoServico></InfNfse></Nfse>{cancel}</CompNfse></ListaNfse></ConsultarNfseResposta>").encode()


def _nfe(n: int, itens: list[tuple[int, str]]) -> bytes:
    det = "".join(
        f'<det nItem="{i}"><prod><cProd>P{i}</cProd><xProd>PECA</xProd><NCM>87089990</NCM><CFOP>{cfop}</CFOP>'
        f"<qCom>1</qCom><vUnCom>{v}</vUnCom><vProd>{v}</vProd></prod><imposto><ICMS><ICMS00><orig>0</orig>"
        f"<CST>00</CST></ICMS00></ICMS></imposto></det>" for i, (cfop, v) in enumerate(itens, 1))
    return (f'<?xml version="1.0" encoding="UTF-8"?><nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe>'
            f'<infNFe Id="NFe35{n:042d}"><ide><nNF>{n}</nNF><dhEmi>2026-07-10T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>'
            f"<emit><CNPJ>{CNPJ}</CNPJ><enderEmit><UF>SP</UF></enderEmit><CRT>3</CRT></emit>"
            f"<dest><CNPJ>{TOMADOR}</CNPJ><enderDest><UF>SP</UF></enderDest></dest>{det}</infNFe></NFe></nfeProc>").encode()


def _zip(**arquivos: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, x in arquivos.items():
            z.writestr(f"{nome}.xml", x)
    return buf.getvalue()


@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "SERVICOS NFSE LTDA", "cnpj": CNPJ, "regime_tributario": "LUCRO_PRESUMIDO"}).json()
    return cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-07", "competencia_final": "2026-08"}).json()["id"]


def _enviar(cliente, h, pid, nome, conteudo):
    r = cliente.post(f"/api/planejamentos/{pid}/nfe", headers=h, files={"arquivo": (nome, conteudo)})
    assert r.status_code == 200, r.text
    return r.json()


def _servicos(cliente, h, pid):
    return {c: Decimal(str(v)) for c, v in cliente.get(f"/api/planejamentos/{pid}/coleta", headers=h).json()["servicos"].items()}


def test_nfse_soma_por_mes_sem_duplicar(cliente, contador, pid):
    lote = _zip(a=_nacional(1, CNPJ, "1000.00"), b=_nacional(2, CNPJ, "250.50"),
                c=_nacional(3, TOMADOR, "999.00"),  # serviço tomado: não é receita da empresa
                d=_abrasf(7, "400.00"), e=_abrasf(8, "100.00"))
    r = _enviar(cliente, contador, pid, "servicos.zip", lote)
    assert r["importados"] == 4 and any("serviço tomado" in linha for linha in r["log"])
    assert _servicos(cliente, contador, pid) == {"2026-07": Decimal("1250.50"), "2026-08": Decimal("500.00")}
    # reenviar a mesma nota não soma de novo; a cancelada na prefeitura sai da soma
    r = _enviar(cliente, contador, pid, "n1.xml", _nacional(1, CNPJ, "1000.00"))
    assert r["importados"] == 0 and r["ignorados"] == 1
    _enviar(cliente, contador, pid, "cancelada.xml", _abrasf(8, "100.00", cancelada=True))
    assert _servicos(cliente, contador, pid) == {"2026-07": Decimal("1250.50"), "2026-08": Decimal("400.00")}


def test_receita_pelo_cfop_deixa_5929_fora(cliente, contador, pid):
    _enviar(cliente, contador, pid, "venda.xml", _nfe(1, [(5102, "300.00"), (5929, "700.00")]))
    s = next(x for x in cliente.get(f"/api/planejamentos/{pid}/coleta", headers=contador).json()["saidas"]
             if x["competencia"] == "2026-07")
    assert Decimal(str(s["valor"])) == 1000 and Decimal(str(s["receita"])) == 300
    assert [(f["cfop"], Decimal(str(f["valor"])), f["sem_regra"]) for f in s["fora"]] == [(5929, 700, False)]
