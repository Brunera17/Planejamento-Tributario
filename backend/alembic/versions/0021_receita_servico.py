"""receita de serviço por mês

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-23 10:00:00

Receita de prestação de serviços por competência do planejamento, para a análise de empresas com comércio e serviço:
anexo do serviço no Simples, presunção do serviço no Lucro Presumido e ISS no LP e no LR.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0021'
down_revision: Union[str, Sequence[str], None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'receita_servico_mensal',
        sa.Column('planejamento_id', sa.Integer(), nullable=False),
        sa.Column('valor', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('competencia', sa.String(length=7), nullable=False),
        sa.CheckConstraint('valor >= 0', name='ck_receita_servico_valor'),
        sa.ForeignKeyConstraint(['planejamento_id'], ['planejamento.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('planejamento_id', 'competencia', name='uq_receita_servico_mensal'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('receita_servico_mensal')
