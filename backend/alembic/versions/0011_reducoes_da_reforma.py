"""reducoes da reforma

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-03 23:00:00

Reduções de CBS e IBS por NCM nos anexos da LC 214/2025 (alíquota zero e redução de 60%), usadas na projeção
da Reforma. Os dados entram pela carga inicial.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('regra_reforma',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ncm', sa.String(length=8), nullable=False),
    sa.Column('excecoes', sa.String(length=300), nullable=True),
    sa.Column('anexo', sa.String(length=20), nullable=False),
    sa.Column('item', sa.String(length=10), nullable=True),
    sa.Column('descricao', sa.String(length=200), nullable=False),
    sa.Column('reducao', sa.Numeric(precision=12, scale=8), nullable=False),
    sa.Column('condicao', sa.Text(), nullable=True),
    sa.Column('cst', sa.String(length=3), nullable=False),
    sa.Column('cclass_trib', sa.String(length=6), nullable=True),
    sa.Column('norma_id', sa.Integer(), nullable=True),
    sa.Column('alterado_por', sa.Integer(), nullable=True),
    sa.Column('alterado_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('vigencia_inicio', sa.Date(), nullable=False),
    sa.Column('vigencia_fim', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['alterado_por'], ['usuario.id'], ),
    sa.ForeignKeyConstraint(['norma_id'], ['norma.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_regra_reforma_ncm', 'regra_reforma', ['ncm'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_regra_reforma_ncm', table_name='regra_reforma')
    op.drop_table('regra_reforma')
