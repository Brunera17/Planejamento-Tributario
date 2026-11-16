"""Farmacêuticos e perfumaria (Lei 10.147/2000, art. 1º, I): a base pela lei, com os códigos na NCM vigente.

Os NCM vêm das vendas reais de uma farmácia (setembro de 2026). A base precisa concordar com a classificação que o
escritório usou no PGDAS-D, exceto onde a lei diz o contrário (último bloco).
"""
import pytest

from app.motor.lei_monofasico import Enquadramento, avaliar
from app.seeds.tabelas import lei_monofasico

M, C, N = Enquadramento.MONOFASICO, Enquadramento.CONDICIONAL, Enquadramento.NAO_LISTADO


@pytest.mark.parametrize("ncm,enquadramento,presumido", [
    # alínea a: medicamentos das posições 30.03 e 30.04 e os códigos citados
    ("30049069", M, True),   # acetilcisteína
    ("30049099", M, True),
    ("30043999", M, True),   # corticoide
    ("30039099", M, True),
    ("30066000", M, True),   # contraceptivo hormonal (3006.60.00)
    ("30051010", M, True),   # curativo impregnado de substância farmacêutica
    ("30024129", M, True),   # vacina humana em doses: 3002.20.2 da lei, hoje 3002.41.2
    ("30021239", M, True),   # fração do sangue como medicamento: 3002.10.3 da lei, hoje 3002.12.3
    ("30024992", C, True),   # 3002.90.92 da lei, hoje 3002.49.92: confirmar o produto
    ("30021590", C, False),  # imunológico em doses: fora da tabela 4.3.10 da Receita
    # exceções expressas da lei (amitraz; cipermetrina)
    ("30039056", N, False),
    ("30049046", N, False),
    # alínea b: perfumaria, toucador e higiene pessoal
    ("33059000", M, True),   # tintura de cabelo
    ("33072010", M, True),   # desodorante
    ("33049990", M, True),
    ("34012010", M, True),   # sabão de toucador em outras formas
    ("96032100", M, True),   # escova de dentes
    ("34011190", C, True),   # monofásico fora do Ex 01 (sabões de toucador)
    # fora da lei
    ("33069000", N, False),  # higiene bucal: a Lei 12.839/2013 tirou a posição 33.06
    ("30051090", N, False),  # curativo sem substância farmacêutica
    ("96190000", N, False),  # fralda e absorvente
    ("21069030", N, False),  # suplemento alimentar
    ("38089429", N, False),  # álcool gel (desinfetante)
    ("19059090", N, False),  # salgadinho
])
def test_enquadramento_farmacia(ncm, enquadramento, presumido):
    a = avaliar(ncm, lei_monofasico())
    assert (a.enquadramento, a.monofasico_presumido) == (enquadramento, presumido), a.motivo


def test_excecao_cita_a_lei_e_bebidas_continuam():
    a = avaliar("30049046", lei_monofasico())
    assert "exceção" in a.motivo and "10.147" in a.fundamento
    assert avaliar("22029900", lei_monofasico()).enquadramento == M  # energético: Lei 13.097/2015
    assert avaliar("87089990", lei_monofasico()).enquadramento == M  # autopeça: Lei 10.485/2002
