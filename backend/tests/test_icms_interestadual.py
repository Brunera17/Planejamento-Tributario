"""Alíquota interestadual do ICMS por item: 4% para importados (Res. Senado 13/2012), 7% ou 12% pelo destino (Res. Senado 22/1989)."""
from decimal import Decimal

import pytest

from app.motor.classificacao import ItemBruto, RegraCfop, RegraNcm, classificar
from app.motor.icms import aliquota_interestadual


@pytest.mark.parametrize("origem, uf_origem, uf_destino, esperada", [
    ("1", "SP", "MG", "0.04"),  # importação direta
    ("2", "SP", "BA", "0.04"),  # importado comprado no mercado interno
    ("3", "SP", "RJ", "0.04"),  # nacional com conteúdo de importação acima de 40%
    ("8", "SP", "PE", "0.04"),  # conteúdo de importação acima de 70%
    ("6", "SP", "MG", "0.12"),  # sem similar nacional (lista da Camex): fora dos 4%
    ("0", "SP", "MG", "0.12"),
    ("0", "SP", "BA", "0.07"),
    ("0", "SP", "ES", "0.07"),
    ("0", "MG", "SP", "0.12"),
    ("0", "BA", "SP", "0.12"),  # do Nordeste para o Sudeste: 12%
    (None, "SP", "GO", "0.07"),
])
def test_aliquota_interestadual(origem, uf_origem, uf_destino, esperada):
    assert aliquota_interestadual(uf_origem, uf_destino, origem) == Decimal(esperada)


def test_sem_uf_usa_o_parametro_mas_importado_sempre_4():
    assert aliquota_interestadual("SP", None, "0") is None
    assert aliquota_interestadual(None, None, "1") == Decimal("0.04")


def test_classificacao_poe_a_aliquota_so_nas_interestaduais():
    brutos = [ItemBruto("2026-07", "87089990", 5102, "SP", Decimal("100"), origem="1"),
              ItemBruto("2026-07", "87089990", 6102, "MG", Decimal("100"), origem="1"),
              ItemBruto("2026-07", "87089990", 6102, "BA", Decimal("100"), origem="0")]
    cls = classificar(brutos, {5102: RegraCfop(5102, True), 6102: RegraCfop(6102, True)},
                      {"87089990": RegraNcm("87089990", True)}, "SP")
    assert [i.aliq_interestadual for i in cls.itens] == [None, Decimal("0.04"), Decimal("0.07")]
