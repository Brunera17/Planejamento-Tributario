from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import mapped_column

Dinheiro = Numeric(14, 2)
Aliquota = Numeric(12, 8)

PK = Annotated[int, mapped_column(primary_key=True)]
Competencia = Annotated[str, mapped_column(String(7))]  # AAAA-MM
Valor = Annotated[Decimal, mapped_column(Dinheiro)]


def agora() -> datetime:
    return datetime.now(UTC)


Momento = Annotated[datetime, mapped_column(DateTime(timezone=True), default=agora)]
