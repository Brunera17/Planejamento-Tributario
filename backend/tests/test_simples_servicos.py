"""Simples Nacional de serviços: tabelas dos Anexos III, IV e V, Fator R e teto de 5% do ISS no DAS."""
from decimal import Decimal as D

import pytest

from app.motor.simples import aliquota_efetiva, anexo_pelo_fator_r, fator_r, reparticao
from app.seeds.tabelas import faixas_simples


@pytest.mark.parametrize("anexo", ["III", "IV", "V"])
def test_tabela_tem_seis_faixas_e_reparticao_fecha_100(anexo):
    faixas = faixas_simples(anexo)
    assert [f.faixa for f in faixas] == [1, 2, 3, 4, 5, 6]
    for f in faixas:
        assert f.p_irpj + f.p_csll + f.p_cofins + f.p_pis + f.p_cpp + f.p_icms + f.p_ipi + f.p_iss == 1
        assert f.p_icms == 0 and f.p_ipi == 0
    assert faixas[-1].p_iss == 0  # acima do sublimite o ISS sai do DAS


def test_anexo_iv_nao_tem_cpp_no_das():
    assert all(f.p_cpp == 0 for f in faixas_simples("IV"))


def test_aliquota_efetiva_anexo_iii():
    # (500.000 × 13,5% − 17.640) ÷ 500.000
    assert aliquota_efetiva(D("500000"), list(faixas_simples("III"))).efetiva == D("0.09972")


def test_reparticao_sem_teto_soma_a_efetiva():
    a = aliquota_efetiva(D("500000"), list(faixas_simples("III")))
    r = reparticao(a)
    assert sum(r.values()) == a.efetiva
    assert r["ISS"] == a.efetiva * D("0.325")


def test_iss_limitado_a_5_por_cento_e_excesso_vai_aos_federais():
    a = aliquota_efetiva(D("3600000"), list(faixas_simples("III")))  # efetiva 17,51%: ISS bruto 5,87%
    r = reparticao(a)
    assert r["ISS"] == D("0.05")
    assert sum(r.values()) == a.efetiva
    excesso = a.efetiva * D("0.335") - D("0.05")
    assert r["IRPJ"] == a.efetiva * D("0.04") + excesso * D("0.04") / D("0.665")


def test_fator_r():
    assert fator_r(D("280000"), D("1000000")) == D("0.28")
    assert anexo_pelo_fator_r(D("0.28")) == "III"
    assert anexo_pelo_fator_r(D("0.2799")) == "V"
    assert fator_r(D("1000"), D("0")) == 0
