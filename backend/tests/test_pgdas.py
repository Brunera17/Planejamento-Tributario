"""Extrato do PGDAS-D: RBT12 e anexo declarados, lidos do PDF enviado em Documentos."""
import io
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.models import Documento, TipoDocumento
from app.services import documentos, pgdas
from app.services.pgdas import ler

CNPJ = "71563428000190"


def _extrato(atividade: str, rbt12: str = "1.380.250,75", pa: str = "06/2026") -> bytes:
    """PDF com as linhas que o extrato do PGDAS-D traz (período, RBT12 e atividade do estabelecimento)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for linha in ["Extrato do Simples Nacional", f"Período de Apuração (PA): {pa}",
                  "2.2) Receitas Brutas Anteriores", "Mercado Interno Mercado Externo Total",
                  f"Receita bruta acumulada nos doze meses anteriores ao PA (RBT12) {rbt12} 0,00 {rbt12}",
                  "2.8) Informações da Declaração por Estabelecimento", f"Atividade: {atividade}"]:
        c.drawString(40, y, linha)
        y -= 18
    c.save()
    return buf.getvalue()


def test_leitura_do_extrato():
    e = ler(_extrato("Revenda de mercadorias, exceto para o exterior - Sem substituição tributária"), "extrato.pdf")
    assert e.competencia == "2026-06" and e.rbt12 == Decimal("1380250.75") and e.anexos == {"I"}
    e = ler(_extrato("Venda de mercadorias industrializadas pelo contribuinte, exceto para o exterior"))
    assert e.anexos == {"II"}
    assert ler(b"nao e pdf").lido is False


def test_extrato_preenche_o_rbt12_e_avisa_anexo_diferente(cliente, contador):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": "EXTRATO PGDAS LTDA", "cnpj": CNPJ, "regime_tributario": "SIMPLES_NACIONAL", "uf": "SP",
        "cnae": "4530703", "atividade": "COMERCIO"}).json()
    assert emp["anexo_simples"] == "I"  # sugerido pelo CNAE de comércio
    pid = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-06", "competencia_final": "2026-06"}).json()["id"]
    tipos = cliente.get(f"/api/planejamentos/{pid}/documentos", headers=contador).json()["tipos"]
    tipo = next(t["id"] for t in tipos if "PGDAS" in t["nome"])
    pdf = _extrato("Venda de mercadorias industrializadas pelo contribuinte, exceto para o exterior")
    r = cliente.post(f"/api/planejamentos/{pid}/documentos/2026-06/{tipo}", headers=contador, files={"arquivo": ("extrato.pdf", pdf)})
    assert r.status_code == 201, r.text

    coleta = cliente.get(f"/api/planejamentos/{pid}/coleta", headers=contador).json()
    auto = coleta["premissas_auto"]["rbt12_informado"]
    assert Decimal(str(auto["valor"])) == Decimal("1380250.75") and "PGDAS-D de 06/2026" in auto["fonte"]

    venda = (f'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe35{1:042d}"><ide><nNF>1</nNF>'
             f"<dhEmi>2026-06-10T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide><emit><CNPJ>{CNPJ}</CNPJ><enderEmit><UF>SP</UF></enderEmit></emit>"
             "<dest><CNPJ>11222333000181</CNPJ><enderDest><UF>SP</UF></enderDest></dest>"
             '<det nItem="1"><prod><cProd>A</cProd><xProd>PECA</xProd><NCM>87089990</NCM><CFOP>5102</CFOP><qCom>1</qCom>'
             "<vUnCom>1000</vUnCom><vProd>1000.00</vProd></prod></det></infNFe></NFe></nfeProc>").encode()
    assert cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador, files={"arquivo": ("v.xml", venda)}).status_code == 200
    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    assert "declara Anexo II, mas o cálculo usa o Anexo I" in (sim.get("pendencias") or "")


# ------------------------------------------------------------------ leitura gravada no envio (etapa 3b)

def _planejamento_com_extrato(cliente, contador, cnpj, rbt12="2.000.000,00"):
    emp = cliente.post("/api/empresas", headers=contador, json={
        "razao_social": f"PGDAS NO BANCO {cnpj}", "cnpj": cnpj, "regime_tributario": "SIMPLES_NACIONAL", "uf": "SP",
        "cnae": "4530703", "atividade": "COMERCIO"}).json()
    pid = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": emp["id"], "competencia_inicial": "2026-06", "competencia_final": "2026-06"}).json()["id"]
    tipos = cliente.get(f"/api/planejamentos/{pid}/documentos", headers=contador).json()["tipos"]
    tipo = next(t["id"] for t in tipos if "PGDAS" in t["nome"])
    r = cliente.post(f"/api/planejamentos/{pid}/documentos/2026-06/{tipo}", headers=contador,
                     files={"arquivo": ("extrato.pdf", _extrato("Revenda de mercadorias", rbt12=rbt12))})
    assert r.status_code == 201, r.text
    return pid, r.json()["id"], tipos


def _rbt12(cliente, contador, pid):
    auto = cliente.get(f"/api/planejamentos/{pid}/coleta", headers=contador).json()["premissas_auto"]
    return Decimal(str(auto["rbt12_informado"]["valor"])) if "rbt12_informado" in auto else None


def test_leitura_gravada_no_envio_e_o_pdf_nao_e_relido(cliente, contador, fabrica_sessao, monkeypatch):
    pid, doc_id, _ = _planejamento_com_extrato(cliente, contador, "81520477000108")
    with fabrica_sessao() as db:
        gravado = db.get(Documento, doc_id).pgdas_extrato
    assert gravado == {"lido": True, "competencia": "2026-06", "rbt12": "2000000.00", "anexos": ["I"], "servicos": False}

    def nao_releia(*_a, **_k):
        raise AssertionError("o PDF não deveria ser lido de novo")
    monkeypatch.setattr(pgdas, "ler", nao_releia)
    assert _rbt12(cliente, contador, pid) == Decimal("2000000.00")


def test_extrato_antigo_sem_leitura_cai_no_arquivo_e_o_comando_preenche(cliente, contador, fabrica_sessao):
    pid, doc_id, _ = _planejamento_com_extrato(cliente, contador, "81520477000280", rbt12="900.000,00")
    with fabrica_sessao() as db:
        db.get(Documento, doc_id).pgdas_extrato = None  # como um envio de antes desta versão
        db.commit()
    assert _rbt12(cliente, contador, pid) == Decimal("900000.00")  # lê do arquivo, sem gravar
    with fabrica_sessao() as db:
        assert db.get(Documento, doc_id).pgdas_extrato is None
        assert pgdas.preencher(db) >= 1
        assert db.get(Documento, doc_id).pgdas_extrato["rbt12"] == "900000.00"
        assert pgdas.preencher(db) == 0  # idempotente


def test_pdf_de_outro_tipo_nao_e_lido_como_pgdas(cliente, contador, fabrica_sessao):
    pid, _, tipos = _planejamento_com_extrato(cliente, contador, "81520477000361")
    outro = next(t["id"] for t in tipos if "PGDAS" not in t["nome"])
    r = cliente.post(f"/api/planejamentos/{pid}/documentos/2026-06/{outro}", headers=contador,
                     files={"arquivo": ("balancete.pdf", _extrato("Revenda de mercadorias"))})
    assert r.status_code == 201, r.text
    with fabrica_sessao() as db:
        assert db.get(Documento, r.json()["id"]).pgdas_extrato is None


def test_preencher_deixa_null_o_arquivo_sumido(cliente, contador, fabrica_sessao):
    """Arquivo sumido fica NULL e é tentado de novo — nunca marcado como "não lido" para sempre."""
    pid, doc_id, _ = _planejamento_com_extrato(cliente, contador, "81520477000523")
    with fabrica_sessao() as db:
        doc = db.get(Documento, doc_id)
        doc.pgdas_extrato = None
        db.commit()
        documentos.caminho(doc.arquivo).unlink()
        pgdas.preencher(db)
        assert db.get(Documento, doc_id).pgdas_extrato is None


def test_tipo_pgdas_independe_de_maiusculas(fabrica_sessao):
    with fabrica_sessao() as db:
        tipo = TipoDocumento(nome="Extrato pgdas do mês")
        db.add(tipo)
        db.flush()
        assert pgdas.eh_tipo_pgdas(db, tipo.id)
        db.rollback()


def test_comando_de_preenchimento_roda_como_no_start_do_container(tmp_path):
    """O CMD do Dockerfile roda `python -m app.services.pgdas`; o CI só monta a imagem, então o teste roda aqui."""
    import os
    import subprocess
    import sys

    from sqlalchemy import create_engine

    from app.db.session import Base

    url = f"sqlite:///{(tmp_path / 'start.db').as_posix()}"
    Base.metadata.create_all(create_engine(url))
    env = {**os.environ, "DATABASE_URL": url, "UPLOAD_DIR": str(tmp_path)}
    r = subprocess.run([sys.executable, "-m", "app.services.pgdas"], env=env, capture_output=True, text=True,
                       cwd=os.path.dirname(os.path.dirname(__file__)), timeout=120)
    assert r.returncode == 0, r.stderr
    assert "extrato(s) lido(s) e gravado(s)" in r.stdout


def test_preencher_grava_nao_lido_e_ignora_arquivo_cifrado(cliente, contador, fabrica_sessao):
    """PDF que abre mas não é extrato: grava "não lido" (como no envio) e não é reaberto a cada cálculo.
    Arquivo já cifrado (etapa 4): fica NULL — sem decifrar, "ilegível" seria falso."""
    _, doc_ilegivel, _ = _planejamento_com_extrato(cliente, contador, "81520477000604")
    _, doc_cifrado, _ = _planejamento_com_extrato(cliente, contador, "81520477000795")
    with fabrica_sessao() as db:
        for doc_id, conteudo in ((doc_ilegivel, b"%PDF-1.7 escaneado, sem texto"), (doc_cifrado, b"PTC1...")):
            doc = db.get(Documento, doc_id)
            doc.pgdas_extrato = None
            documentos.caminho(doc.arquivo).write_bytes(conteudo)
        db.commit()
        pgdas.preencher(db)
        assert db.get(Documento, doc_ilegivel).pgdas_extrato["lido"] is False
        assert db.get(Documento, doc_cifrado).pgdas_extrato is None
