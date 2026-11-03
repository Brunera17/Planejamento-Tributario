"""difal

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-03 21:00:00

Alíquota interna de cada estado (com FCP, base dupla e vigência) para o DIFAL das vendas a consumidor final não
contribuinte de outro estado (EC 87/2015 e LC 190/2022), e o indicador de contribuinte do destinatário na nota.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('aliquota_uf',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uf', sa.String(length=2), nullable=False),
    sa.Column('aliquota', sa.Numeric(precision=12, scale=8), nullable=False),
    sa.Column('fcp', sa.Numeric(precision=12, scale=8), nullable=False),
    sa.Column('base_dupla', sa.Boolean(), nullable=False),
    sa.Column('fonte', sa.String(length=300), nullable=True),
    sa.Column('alterado_por', sa.Integer(), nullable=True),
    sa.Column('alterado_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('vigencia_inicio', sa.Date(), nullable=False),
    sa.Column('vigencia_fim', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['alterado_por'], ['usuario.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('uf', 'vigencia_inicio', name='uq_aliquota_uf')
    )
    with op.batch_alter_table('nota_fiscal', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dest_contribuinte', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('nota_fiscal', schema=None) as batch_op:
        batch_op.drop_column('dest_contribuinte')
    op.drop_table('aliquota_uf')
