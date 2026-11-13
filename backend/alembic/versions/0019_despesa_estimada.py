"""despesa estimada

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-13 14:00:00

Marca o item de despesa preenchido por "Simular despesas" (referência de mercado da atividade). O relatório avisa
enquanto houver valor estimado; digitar o valor real tira a marca.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0019'
down_revision: Union[str, Sequence[str], None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('levantamento_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('estimado', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('levantamento_item', schema=None) as batch_op:
        batch_op.drop_column('estimado')
