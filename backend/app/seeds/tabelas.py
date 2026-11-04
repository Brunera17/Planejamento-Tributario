"""Leitura das tabelas legais da carga inicial (arquivos JSON em seeds/dados)."""
from __future__ import annotations

import json
from dataclasses import fields
from decimal import Decimal
from functools import cache
from pathlib import Path

from app.motor.classificacao import RegraCfop, RegraNcm
from app.motor.lei_monofasico import ItemLei
from app.motor.tipos import AnoReforma, FaixaSimples, Parametros

DADOS = Path(__file__).parent / "dados"


def ler(nome: str):
    return json.loads((DADOS / nome).read_text(encoding="utf-8"))


ANEXOS_SIMPLES = {"I": "simples_anexo1.json", "II": "simples_anexo2.json"}


@cache
def faixas_simples(anexo: str = "I") -> tuple[FaixaSimples, ...]:
    return tuple(
        FaixaSimples(
            faixa=f["faixa"],
            **{k: Decimal(f.get(k, "0")) for k in ("rbt12_de", "rbt12_ate", "aliq_nominal", "parcela_deduzir",
                                                   "p_irpj", "p_csll", "p_cofins", "p_pis", "p_cpp", "p_icms", "p_ipi")},
        )
        for f in ler(ANEXOS_SIMPLES[anexo])["faixas"]
    )


@cache
def reforma() -> tuple[AnoReforma, ...]:
    return tuple(
        AnoReforma(a["ano"], Decimal(a["cbs"]), Decimal(a["ibs"]), Decimal(a["fator_icms"]))
        for a in ler("reforma_cronograma.json")["anos"]
    )


def parametros(valores: dict[str, Decimal] | None = None) -> Parametros:
    """Parâmetros a partir de {chave: valor}; sem argumento, usa a carga inicial."""
    if valores is None:
        valores = {p["chave"]: Decimal(p["valor"]) for p in ler("parametros.json")}
    nomes = {f.name for f in fields(Parametros)}
    return Parametros(**{k: v for k, v in valores.items() if k in nomes})


@cache
def regras_cfop() -> dict[int, RegraCfop]:
    return {r["cfop"]: RegraCfop(r["cfop"], r["gera_receita"]) for r in ler("cfop_regras.json")}


@cache
def regras_ncm() -> dict[str, RegraNcm]:
    return {r["ncm"]: RegraNcm(r["ncm"], r["monofasico"], r["sujeito_st"]) for r in ler("ncm_regras.json")}


@cache
def lei_monofasico() -> tuple[ItemLei, ...]:
    return tuple(ItemLei(i["anexo"], i["item"], i["codigo"], i["prefixo"], tuple(i["ex"]), i["condicao"], i["padrao"])
                 for i in ler("lei_10485.json")["itens"])
