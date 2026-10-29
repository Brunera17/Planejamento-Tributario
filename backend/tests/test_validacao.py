import pytest

from app.utils.validacao import cnpj_valido, normalizar_regime, telefone_valido


@pytest.mark.parametrize("cnpj,ok", [
    ("11.222.333/0001-81", True),
    ("11222333000181", True),
    ("11.222.333/0001-82", False),
    ("00000000000000", False),
    ("1122233300018", False),
    ("12.ABC.345/01DE-35", True),   # exemplo oficial de CNPJ alfanumérico (Receita Federal)
    ("12.ABC.345/01DE-36", False),
])
def test_cnpj(cnpj, ok):
    assert cnpj_valido(cnpj) is ok


@pytest.mark.parametrize("texto,regime", [
    ("Simples Nacional", "SIMPLES_NACIONAL"),
    ("LUCRO PRESUMIDO", "LUCRO_PRESUMIDO"),
    ("lucro real", "LUCRO_REAL"),
    ("Lucro Arbitrado", None),
])
def test_regime(texto, regime):
    assert normalizar_regime(texto) == regime


def test_telefone():
    assert telefone_valido("(11) 98765-4321")
    assert not telefone_valido("98765-4321")
