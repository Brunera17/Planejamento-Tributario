"""Conversão de dataclasses do motor para JSON (Decimal → float, Enum → valor)."""
from __future__ import annotations

import dataclasses
import hashlib
import json
from decimal import Decimal
from enum import Enum
from typing import Any


def para_json(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        dados = {f.name: para_json(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        if hasattr(obj, "total") and "total" not in dados:  # propriedade calculada de ResultadoRegime
            dados["total"] = para_json(obj.total)
        return dados
    if isinstance(obj, Decimal):
        return float(round(obj, 10))
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {(k.value if isinstance(k, Enum) else str(k)): para_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        itens = [para_json(v) for v in obj]
        return sorted(itens) if isinstance(obj, set) else itens
    return obj


def hash_entrada(entrada: Any) -> str:
    texto = json.dumps(para_json(entrada), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texto.encode()).hexdigest()
