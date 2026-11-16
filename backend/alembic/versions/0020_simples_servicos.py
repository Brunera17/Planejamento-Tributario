"""simples: parcela do ISS

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-16 10:00:00

Coluna p_iss em simples_faixa para os Anexos III, IV e V (serviços). As faixas desses anexos entram pela carga das
tabelas legais; nos Anexos I e II a parcela é zero.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0020'
down_revision: Union[str, Sequence[str], None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('simples_faixa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('p_iss', sa.Numeric(precision=12, scale=8), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('simples_faixa', schema=None) as batch_op:
        batch_op.drop_column('p_iss')
