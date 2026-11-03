"""icms st nas notas

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-03 19:00:00

Base e valor do ICMS-ST de cada item da NF-e (vBCST/vICMSST ou vBCSTRet/vICMSSTRet), usados no crédito do
estoque que sai da substituição tributária (Portaria CAT 28/2020, art. 4º). Notas importadas antes ficam sem o
dado até serem importadas de novo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('nota_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bc_st', sa.Numeric(precision=14, scale=2), nullable=True))
        batch_op.add_column(sa.Column('vl_icms_st', sa.Numeric(precision=14, scale=2), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('nota_item', schema=None) as batch_op:
        batch_op.drop_column('vl_icms_st')
        batch_op.drop_column('bc_st')
