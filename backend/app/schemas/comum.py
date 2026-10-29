from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

CompetenciaStr = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-06"])]
ValorMonetario = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class Esquema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
