"""pgdas no banco

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-06 10:00:00

Leitura do extrato do PGDAS-D gravada no documento no momento do envio: o PDF deixa de ser lido e interpretado
a cada cálculo (e, com a criptografia dos arquivos, de ser decifrado). Extratos já enviados continuam lidos do
arquivo até rodar `python -m app.services.pgdas`, que grava a leitura deles.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('documento', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pgdas_extrato', sa.JSON(none_as_null=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('documento', schema=None) as batch_op:
        batch_op.drop_column('pgdas_extrato')
