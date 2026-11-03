"""data de cadastro da empresa

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-03 15:00:00

Data de cadastro na lista de empresas. As empresas que já existiam recebem a data do primeiro
planejamento (a empresa estava cadastrada nessa data); sem planejamento, ficam sem data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('criado_em', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE empresa SET criado_em = (SELECT MIN(p.criado_em) FROM planejamento p WHERE p.empresa_id = empresa.id)")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.drop_column('criado_em')
