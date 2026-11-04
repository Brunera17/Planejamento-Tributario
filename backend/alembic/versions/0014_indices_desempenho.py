"""indices de desempenho

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-04 20:00:00

Índices para os filtros mais usados: as notas do planejamento por tipo e competência (motor, progresso, revisão
e premissas filtram sempre assim) e o histórico de status do planejamento. Só índices: nada depende das outras
migrações.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_nota_fiscal_planejamento_tipo_competencia", "nota_fiscal",
                    ["planejamento_id", "tipo", "competencia"])
    op.create_index("ix_historico_status_planejamento", "historico_status", ["planejamento_id"])


def downgrade() -> None:
    op.drop_index("ix_historico_status_planejamento", table_name="historico_status")
    op.drop_index("ix_nota_fiscal_planejamento_tipo_competencia", table_name="nota_fiscal")
