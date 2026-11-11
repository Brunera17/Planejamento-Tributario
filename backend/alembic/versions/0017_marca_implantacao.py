"""marca de implantação

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-11 10:00:00

Guarda a versão do código já preparada (migrações, cargas e PGDAS-D). No Render grátis a API dorme e acorda num
contêiner novo; com a versão igual, o preparo é pulado e a API sobe mais rápido (app/implantacao.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0017'
down_revision: Union[str, Sequence[str], None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('marca_implantacao',
                    sa.Column('chave', sa.String(length=40), nullable=False),
                    sa.Column('valor', sa.String(length=80), nullable=False),
                    sa.PrimaryKeyConstraint('chave'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('marca_implantacao')
