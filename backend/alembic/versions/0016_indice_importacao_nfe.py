"""indice da importacao na nota fiscal

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-11 21:00:00

nota_fiscal.importacao_id não tinha índice: apagar uma importação (ON DELETE SET NULL) varria a tabela inteira de
notas, e o relatório contábil faz join por essa coluna. Só índice: nada depende das outras migrações.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# CONCURRENTLY no Postgres: não trava gravações em nota_fiscal durante o deploy (precisa rodar fora de transação);
# o SQLite ignora a opção
def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index("ix_nota_fiscal_importacao", "nota_fiscal", ["importacao_id"], postgresql_concurrently=True)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index("ix_nota_fiscal_importacao", table_name="nota_fiscal", postgresql_concurrently=True)
