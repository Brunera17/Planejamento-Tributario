"""simples anexo ii

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-04 10:00:00

Parcela do IPI na repartição do DAS (Anexo II, indústria, da LC 123/2006). As faixas do Anexo II entram pela
carga inicial; o anexo usado no cálculo é o do cadastro da empresa, ou o sugerido pelo CNAE.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('simples_faixa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('p_ipi', sa.Numeric(precision=12, scale=8), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('simples_faixa', schema=None) as batch_op:
        batch_op.drop_column('p_ipi')
