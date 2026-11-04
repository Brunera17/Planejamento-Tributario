"""Anexo do Simples Nacional da empresa: o do cadastro, ou o sugerido pelo CNAE ou pela atividade."""
from __future__ import annotations

ANEXOS_CALCULADOS = {"I": "comércio", "II": "indústria"}
ROMANOS = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}


def anexo_pelo_cnae(cnae: str | None) -> str | None:
    """Comércio (divisões 45 a 47 da CNAE) vai para o Anexo I; indústria de transformação (10 a 33), para o II.

    Serviços ficam sem sugestão: o anexo (III, IV ou V) depende da atividade e, em vários casos, do Fator R.
    """
    digitos = "".join(c for c in (cnae or "") if c.isdigit())
    if len(digitos) < 2:
        return None
    divisao = int(digitos[:2])
    if 45 <= divisao <= 47:
        return "I"
    if 10 <= divisao <= 33:
        return "II"
    return None


def anexo_da_empresa(anexo_cadastro: str | None, cnae: str | None, atividade: str | None) -> tuple[str, str]:
    """(anexo, de onde veio): cadastro > CNAE > atividade > Anexo I."""
    if anexo_cadastro:
        return anexo_cadastro, "cadastro"
    if sugerido := anexo_pelo_cnae(cnae):
        return sugerido, "CNAE"
    if atividade == "INDUSTRIA":
        return "II", "atividade"
    if atividade == "SERVICO":
        return "III", "atividade"  # III, IV ou V: o contador confirma no cadastro
    return "I", "atividade" if atividade == "COMERCIO" else "padrão"
