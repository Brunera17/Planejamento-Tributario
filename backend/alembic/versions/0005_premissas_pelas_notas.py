"""premissas pelas notas

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-03 10:00:00

Campos do XML que preenchem as premissas (regime do fornecedor, origem e alíquota do ICMS,
consumidor final) e o bloco de progresso "Premissas", com peso tirado de Compras.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('nota_fiscal', schema=None) as batch_op:
        batch_op.add_column(sa.Column('crt_emitente', sa.String(length=1), nullable=True))
        batch_op.add_column(sa.Column('consumidor_final', sa.Boolean(), nullable=True))
    with op.batch_alter_table('nota_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('orig_icms', sa.String(length=1), nullable=True))
        batch_op.add_column(sa.Column('cst_icms', sa.String(length=3), nullable=True))
        batch_op.add_column(sa.Column('aliq_icms', sa.Numeric(precision=12, scale=8), nullable=True))

    # só mexe no peso de Compras se ainda for o padrão; um peso ajustado pelo escritório fica como está
    op.execute("UPDATE peso_progresso SET peso = 10 WHERE bloco = 'COMPRAS' AND peso = 15")
    op.execute("INSERT INTO peso_progresso (bloco, peso, alterado_em) SELECT 'PREMISSAS', 5, CURRENT_TIMESTAMP "
               "WHERE NOT EXISTS (SELECT 1 FROM peso_progresso WHERE bloco = 'PREMISSAS')")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM peso_progresso WHERE bloco = 'PREMISSAS'")
    op.execute("UPDATE peso_progresso SET peso = 15 WHERE bloco = 'COMPRAS' AND peso = 10")
    with op.batch_alter_table('nota_item', schema=None) as batch_op:
        batch_op.drop_column('aliq_icms')
        batch_op.drop_column('cst_icms')
        batch_op.drop_column('orig_icms')
    with op.batch_alter_table('nota_fiscal', schema=None) as batch_op:
        batch_op.drop_column('consumidor_final')
        batch_op.drop_column('crt_emitente')
