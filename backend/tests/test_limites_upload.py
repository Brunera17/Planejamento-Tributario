"""Limites de envio: ZIP de NF-e lido em fluxo (contra "zip bomb") e uploads lidos com teto."""
import io
import zipfile

import pytest

from app.core.config import get_settings
from app.core.erros import ErroNegocio
from app.services.nfe_xml import ler_arquivos
from tests.test_api import NFE

MB = 1024 * 1024


def _zip(arquivos: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    return buf.getvalue()


@pytest.fixture
def limites(monkeypatch):
    s = get_settings()

    def aplicar(**valores):
        for k, v in valores.items():
            monkeypatch.setattr(s, k, v)
    return aplicar


def test_zip_dentro_dos_limites_le_as_notas():
    notas, erros = ler_arquivos("lote.zip", _zip({"a.xml": NFE.encode(), "leia-me.txt": b"x"}))
    assert len(notas) == 1 and erros == []


def test_xml_grande_demais_dentro_do_zip_e_ignorado(limites):
    limites(nfe_xml_max_mb=1)
    bomba = b"<a>" + b" " * (2 * MB) + b"</a>"  # comprime para poucos KB
    notas, erros = ler_arquivos("lote.zip", _zip({"bomba.xml": bomba, "a.xml": NFE.encode()}))
    assert len(notas) == 1
    assert "bomba.xml" in erros[0] and "acima de 1 MB" in erros[0]


def test_soma_descompactada_acima_do_limite_recusa_o_lote(limites):
    limites(nfe_xml_max_mb=2, nfe_zip_descompactado_max_mb=1)
    grande = b"<a>" + b" " * (MB // 2 + 10) + b"</a>"
    with pytest.raises(ErroNegocio) as e:
        ler_arquivos("lote.zip", _zip({"1.xml": grande, "2.xml": grande, "3.xml": grande}))
    assert e.value.status == 413


def test_quantidade_de_xml_acima_do_limite_recusa_o_lote(limites):
    limites(nfe_zip_max_arquivos=2)
    with pytest.raises(ErroNegocio) as e:
        ler_arquivos("lote.zip", _zip({f"{i}.xml": NFE.encode() for i in range(3)}))
    assert e.value.status == 413


def test_zip_corrompido_e_recusado():
    with pytest.raises(ErroNegocio) as e:
        ler_arquivos("lote.zip", b"PK\x03\x04 isto nao e um zip")
    assert e.value.status == 415


def _pid(cliente, contador):
    return next(x for x in cliente.get("/api/planejamentos", headers=contador).json() if x["cnpj"] == "11444777000161")["id"]


def test_upload_de_nfe_acima_do_limite_responde_413(cliente, contador, limites):
    limites(nfe_xml_max_mb=1)
    arq = {"arquivo": ("nota.xml", b"<a>" + b" " * (MB + 1) + b"</a>", "text/xml")}
    r = cliente.post(f"/api/planejamentos/{_pid(cliente, contador)}/nfe", headers=contador, files=arq)
    assert r.status_code == 413


def test_upload_de_relatorio_contabil_acima_do_limite_responde_413(cliente, contador, limites):
    limites(relatorio_contabil_max_mb=1)
    arq = {"arquivo": ("rel.xlsx", b"PK\x03\x04" + b"0" * (MB + 1), "application/octet-stream")}
    r = cliente.post(f"/api/planejamentos/{_pid(cliente, contador)}/relatorio-contabil", headers=contador, files=arq)
    assert r.status_code == 413


def test_importacao_de_empresas_acima_de_10_mb_responde_413(cliente, contador):
    arq = {"arquivo": ("empresas.csv", b"a" * (10 * MB + 1), "text/csv")}
    assert cliente.post("/api/empresas/importacao/previa", headers=contador, files=arq).status_code == 413
