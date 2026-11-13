"""Segunda varredura: NF-e cancelada fora do faturamento, planejamento aprovado travado e painel sem descartadas."""
from decimal import Decimal

import pytest

from tests.conftest import _token
from tests.test_fluxo_e_regras import NFE

CNPJ = "44555666000181"
CHAVE = "35260944555666000181550010000000011000000011"
NOTA = NFE.replace("12345678000195", CNPJ).replace("NFe35260912345678000195550010000000011000000011", f"NFe{CHAVE}")
EVENTO = f"""<?xml version="1.0"?><procEventoNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00"><evento><infEvento>
<chNFe>{CHAVE}</chNFe><tpEvento>110111</tpEvento><detEvento><descEvento>Cancelamento</descEvento></detEvento></infEvento></evento>
<retEvento><infEvento><cStat>135</cStat></infEvento></retEvento></procEventoNFe>"""


@pytest.fixture(scope="module")
def pid(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "CANCELADAS LTDA", "cnpj": CNPJ, "regime_tributario": "SIMPLES_NACIONAL", "anexo_simples": "I"}).json()
    return cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-09", "competencia_final": "2026-09"}).json()["id"]


def _enviar(cliente, h, pid, nome, conteudo):
    import io
    import zipfile
    if nome.endswith(".zip"):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            for n, c in conteudo.items():
                z.writestr(n, c)
        conteudo = b.getvalue()
    return cliente.post(f"/api/planejamentos/{pid}/nfe", headers=h, files={"arquivo": (nome, conteudo, "application/octet-stream")}).json()


def _notas(pid):
    from sqlalchemy import func, select

    from app.db.session import SessionLocal
    from app.models import NotaFiscal
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(NotaFiscal).where(NotaFiscal.planejamento_id == pid))


def test_nota_cancelada_nao_entra_e_sai_se_ja_importada(cliente, contador, pid):
    r = _enviar(cliente, contador, pid, "lote.zip", {"nota.xml": NOTA, "cancelamento.xml": EVENTO})
    assert r["importados"] == 0 and "NF 1: cancelada, ignorada" in r["log"] and _notas(pid) == 0

    assert _enviar(cliente, contador, pid, "nota.xml", NOTA.encode())["importados"] == 1 and _notas(pid) == 1
    r = _enviar(cliente, contador, pid, "cancelamento.xml", EVENTO.encode())
    assert "NF 1: cancelada; removida do planejamento" in r["log"] and _notas(pid) == 0


def test_protocolo_de_cancelada_ou_denegada_e_recusado(cliente, contador, pid):
    com_protocolo = NOTA.replace("</NFe>", "</NFe><protNFe><infProt><cStat>101</cStat></infProt></protNFe>")
    r = _enviar(cliente, contador, pid, "nota.xml", com_protocolo.encode())
    assert r["importados"] == 0 and _notas(pid) == 0


@pytest.mark.parametrize("evento", [
    EVENTO.replace("110111", "110110"),  # carta de correção
    EVENTO.replace("<cStat>135</cStat>", "<cStat>136</cStat>"),  # registrado sem vínculo com a NF-e
    EVENTO.split("<retEvento>")[0] + "</procEventoNFe>",  # sem o retorno da SEFAZ
])
def test_evento_que_nao_e_cancelamento_valido_nao_remove_a_nota(cliente, contador, pid, evento):
    assert _enviar(cliente, contador, pid, "nota.xml", NOTA.encode())["importados"] in (0, 1) and _notas(pid) == 1
    r = _enviar(cliente, contador, pid, "evento.xml", evento.encode())
    assert any("evento.xml" in linha for linha in r["log"]) and not any("cancelada" in linha for linha in r["log"])
    assert _notas(pid) == 1


def test_compras_do_mes_zeram_quando_a_ultima_entrada_e_cancelada(cliente, contador):
    cnpj, fornecedor = "55666777000181", "12345678000195"
    chave = f"352609{fornecedor}550010000000021000000021"
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "COMPRADORA LTDA", "cnpj": cnpj, "regime_tributario": "SIMPLES_NACIONAL", "anexo_simples": "I"}).json()
    pid = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-09", "competencia_final": "2026-09"}).json()["id"]
    entrada = (NFE.replace("NFe35260912345678000195550010000000011000000011", f"NFe{chave}")
               .replace("<dest><CPF>12345678909</CPF>", f"<dest><CNPJ>{cnpj}</CNPJ>").replace("<nNF>1</nNF>", "<nNF>2</nNF>")
               .replace("<CFOP>5117</CFOP>", "<CFOP>5102</CFOP>"))
    _enviar(cliente, contador, pid, "entrada.xml", entrada.encode())
    compras = lambda: cliente.get(f"/api/planejamentos/{pid}/coleta", headers=contador).json()["compras"].get("2026-09")  # noqa: E731
    assert Decimal(compras()) == Decimal("500.00")
    _enviar(cliente, contador, pid, "cancelamento.xml", EVENTO.replace(CHAVE, chave).encode())
    assert Decimal(compras()) == 0


@pytest.fixture(scope="module")
def aprovado(cliente, contador):
    """Planejamento próprio com uma simulação, marcado como aprovado direto no banco."""
    from app.db.session import SessionLocal
    from app.models import Planejamento
    cnpj, chave = "77888999000181", "35260977888999000181550010000000011000000011"
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "APROVADA LTDA", "cnpj": cnpj, "regime_tributario": "SIMPLES_NACIONAL", "anexo_simples": "I"}).json()
    pid = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-09", "competencia_final": "2026-09"}).json()["id"]
    nota = NFE.replace("12345678000195", cnpj).replace("NFe35260912345678000195550010000000011000000011", f"NFe{chave}")
    _enviar(cliente, contador, pid, "nota.xml", nota.encode())
    assert cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).status_code == 201
    with SessionLocal() as db:
        db.get(Planejamento, pid).status = "APROVADO"
        db.commit()
    return pid


@pytest.mark.parametrize("metodo,rota,corpo", [
    ("put", "compras", [{"competencia": "2026-09", "valor": "1.00"}]),
    ("put", "folha", [{"competencia": "2026-09", "folha": "1.00", "pro_labore": "1.00"}]),
    ("put", "estoque-st", {"valor": "1.00"}),
    ("delete", "composicao-compras", None),
    ("put", "sem-bens?sem_bens=false", None),
])
def test_planejamento_aprovado_nao_aceita_alteracao(cliente, aprovado, metodo, rota, corpo):
    analista = _token(cliente, "analista")  # sessão nova: outro teste da suíte encerra as do analista
    assert cliente.get(f"/api/planejamentos/{aprovado}", headers=analista).json()["status"] == "APROVADO"
    extra = {"json": corpo} if corpo is not None else {}
    r = getattr(cliente, metodo)(f"/api/planejamentos/{aprovado}/{rota}", headers=analista, **extra)
    assert r.status_code == 409 and "reabri" in r.json()["erro"]


def test_painel_ignora_oportunidade_descartada(cliente, contador, aprovado):
    from sqlalchemy import func, select

    from app.db.session import SessionLocal
    from app.models import OportunidadeRegistro, Simulacao

    def recuperacoes():
        return Decimal(str(cliente.get("/api/dashboard", headers=contador).json()["recuperacoes_identificadas"]))

    antes = recuperacoes()
    with SessionLocal() as db:
        sid = db.scalar(select(func.max(Simulacao.id)).where(Simulacao.planejamento_id == aprovado))
        for situacao, impacto in (("DESCARTADA", "1000.00"), ("ABERTA", "250.00")):
            db.add(OportunidadeRegistro(simulacao_id=sid, codigo="ICMS_ST_INTERNAS", titulo="t", impacto=Decimal(impacto),
                                        prioridade="ALTA", acao="a", situacao=situacao))
        db.commit()
    assert recuperacoes() - antes == Decimal("250.00")
