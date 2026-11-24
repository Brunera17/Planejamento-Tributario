"""notas de serviço (NFS-e) importadas

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-24 10:00:00

NFS-e lidas do XML (padrão nacional ou municipal ABRASF): a receita de serviço do mês passa a ser a soma das notas, e a
nota reenviada não conta duas vezes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0022'
down_revision: Union[str, Sequence[str], None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'nota_servico',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('planejamento_id', sa.Integer(), nullable=False),
        sa.Column('importacao_id', sa.Integer(), nullable=True),
        sa.Column('chave', sa.String(length=60), nullable=False),
        sa.Column('numero', sa.String(length=20), nullable=False),
        sa.Column('competencia', sa.String(length=7), nullable=False),
        sa.Column('valor', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['planejamento_id'], ['planejamento.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['importacao_id'], ['importacao_nfe.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('planejamento_id', 'chave', name='uq_nota_servico_chave'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('nota_servico')
