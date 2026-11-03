"""normas e substituicao tributaria

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-03 17:00:00

Biblioteca de normas (resumo, link oficial e uso no cálculo) e a lista de mercadorias na ST do ICMS por NCM,
com vigência. Os dados entram pela carga inicial (app.seeds.carga).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('norma',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=40), nullable=False),
    sa.Column('titulo', sa.String(length=160), nullable=False),
    sa.Column('apelido', sa.String(length=80), nullable=True),
    sa.Column('esfera', sa.String(length=10), nullable=False),
    sa.Column('uf', sa.String(length=2), nullable=True),
    sa.Column('tributos', sa.String(length=60), nullable=False),
    sa.Column('resumo', sa.Text(), nullable=False),
    sa.Column('uso_no_calculo', sa.Text(), nullable=True),
    sa.Column('url', sa.String(length=300), nullable=False),
    sa.Column('situacao', sa.String(length=10), nullable=False),
    sa.Column('alterado_por', sa.Integer(), nullable=True),
    sa.Column('alterado_em', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['alterado_por'], ['usuario.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('codigo')
    )
    op.create_table('regra_st',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uf', sa.String(length=2), nullable=False),
    sa.Column('ncm', sa.String(length=8), nullable=False),
    sa.Column('excecoes', sa.String(length=200), nullable=True),
    sa.Column('cest', sa.String(length=9), nullable=True),
    sa.Column('segmento', sa.String(length=80), nullable=False),
    sa.Column('item', sa.String(length=10), nullable=True),
    sa.Column('descricao', sa.Text(), nullable=False),
    sa.Column('norma_id', sa.Integer(), nullable=True),
    sa.Column('revogada_por_id', sa.Integer(), nullable=True),
    sa.Column('alterado_por', sa.Integer(), nullable=True),
    sa.Column('alterado_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('vigencia_inicio', sa.Date(), nullable=False),
    sa.Column('vigencia_fim', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['alterado_por'], ['usuario.id'], ),
    sa.ForeignKeyConstraint(['norma_id'], ['norma.id'], ),
    sa.ForeignKeyConstraint(['revogada_por_id'], ['norma.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_regra_st_uf_ncm', 'regra_st', ['uf', 'ncm'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_regra_st_uf_ncm', table_name='regra_st')
    op.drop_table('regra_st')
    op.drop_table('norma')
