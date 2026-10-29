import re
import unicodedata

REGIMES = {
    "SIMPLES NACIONAL": "SIMPLES_NACIONAL",
    "SIMPLES": "SIMPLES_NACIONAL",
    "LUCRO PRESUMIDO": "LUCRO_PRESUMIDO",
    "PRESUMIDO": "LUCRO_PRESUMIDO",
    "LUCRO REAL": "LUCRO_REAL",
    "REAL": "LUCRO_REAL",
}
UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


def somente_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def normalizar_cnpj(valor: str | None) -> str:
    """Remove máscara; aceita o CNPJ numérico e o alfanumérico (IN RFB 2.229/2024)."""
    return re.sub(r"[^0-9A-Z]", "", str(valor or "").upper())


def cnpj_valido(cnpj: str) -> bool:
    d = normalizar_cnpj(cnpj)
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", d) or d == d[0] * 14:
        return False

    def dv(base: str) -> str:
        pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(base):]
        resto = sum((ord(c) - 48) * p for c, p in zip(base, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)

    return d[12] == dv(d[:12]) and d[13] == dv(d[:13])


def sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def normalizar_regime(valor: str | None) -> str | None:
    if not valor:
        return None
    chave = sem_acentos(str(valor)).upper().replace("_", " ").strip()
    return REGIMES.get(chave)


def telefone_valido(valor: str | None) -> bool:
    return len(somente_digitos(valor)) in (10, 11)
