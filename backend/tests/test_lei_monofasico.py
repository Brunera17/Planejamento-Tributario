"""A base da lei precisa reproduzir a classificação revisada do caso de referência, sem digitação manual."""
import pytest

from app.motor.lei_monofasico import Enquadramento, ItemLei, avaliar
from app.seeds.tabelas import ler


def tabela() -> list[ItemLei]:
    return [ItemLei(i["anexo"], i["item"], i["codigo"], i["prefixo"], tuple(i["ex"]), i["condicao"], i["padrao"])
            for i in ler("lei_10485.json")["itens"]]


def test_base_completa():
    t = tabela()
    assert len([i for i in t if i.anexo == "I"]) == 51
    assert [i.item for i in t if i.anexo == "II"] == list(range(1, 16))


def test_reproduz_os_18_ncms_do_caso_de_referencia():
    divergencias = [(r["ncm"], r["monofasico"]) for r in ler("ncm_regras.json")
                    if avaliar(r["ncm"], tabela()).monofasico_presumido != r["monofasico"]]
    assert divergencias == []


@pytest.mark.parametrize("ncm,esperado", [
    ("87088000", Enquadramento.MONOFASICO),      # posição 87.08 inteira
    ("90328929", Enquadramento.MONOFASICO),      # 9032.89.2: subitem na lei
    ("85113020", Enquadramento.MONOFASICO),      # posição 85.11
    ("40169990", Enquadramento.CONDICIONAL),     # Ex 03 e 05
    ("84818099", Enquadramento.CONDICIONAL),     # Ex 01 e 02
    ("84818092", Enquadramento.CONDICIONAL),     # Anexo II: destinação
    ("40093100", Enquadramento.CONDICIONAL),     # Anexo II: com acessórios
    ("73181500", Enquadramento.NAO_LISTADO),
    ("40169300", Enquadramento.NAO_LISTADO),
])
def test_enquadramento(ncm, esperado):
    assert avaliar(ncm, tabela()).enquadramento == esperado


def test_vale_a_entrada_mais_especifica_e_cita_fundamento():
    a = avaliar("84318000", tabela())
    assert a.item.anexo == "II" and a.fundamento == "Lei 10.485/2002, Anexo II, item 2"
    b = avaliar("84314100", tabela())
    assert b.enquadramento == Enquadramento.MONOFASICO and b.fundamento == "Lei 10.485/2002, Anexo I, código 8431.41.00"
