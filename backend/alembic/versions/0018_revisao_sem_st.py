"""revisão: produção própria sem ST

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-13 10:00:00

O contador marca na revisão de produtos o que é produção própria (lanche, pizza do restaurante): a tabela de ST é por
NCM e não distingue o produto industrializado revendido do preparado na casa.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0018'
down_revision: Union[str, Sequence[str], None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('revisao_produto', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sem_st', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('revisao_produto', schema=None) as batch_op:
        batch_op.drop_column('sem_st')
