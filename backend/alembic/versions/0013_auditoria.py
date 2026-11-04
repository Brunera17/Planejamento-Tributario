"""auditoria

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-04 18:00:00

Trilha de auditoria encadeada por hash e checkpoint da verificação. No Postgres, um trigger recusa UPDATE e
DELETE em evento_auditoria; só o expurgo de retenção apaga, ligando `planejador.expurgo` na própria transação.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

TRIGGER = """
CREATE OR REPLACE FUNCTION auditoria_somente_insercao() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('planejador.expurgo', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'evento_auditoria aceita somente inserção';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tg_auditoria_somente_insercao
BEFORE UPDATE OR DELETE ON evento_auditoria
FOR EACH ROW EXECUTE FUNCTION auditoria_somente_insercao();
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'evento_auditoria',
        sa.Column('id', ID, primary_key=True),
        sa.Column('momento', sa.DateTime(timezone=True), nullable=False),
        sa.Column('acao', sa.String(40), nullable=False),
        sa.Column('resultado', sa.String(10), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('usuario_login', sa.String(60), nullable=True),
        sa.Column('sessao_id', sa.String(64), nullable=True),
        sa.Column('ip', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(300), nullable=True),
        sa.Column('empresa_id', sa.Integer(), nullable=True),
        sa.Column('empresa_cnpj', sa.String(14), nullable=True),
        sa.Column('planejamento_id', sa.Integer(), nullable=True),
        sa.Column('recurso_tipo', sa.String(30), nullable=True),
        sa.Column('recurso_id', sa.Integer(), nullable=True),
        sa.Column('detalhes', sa.JSON(), nullable=True),
        sa.Column('hash_anterior', sa.String(64), nullable=False),
        sa.Column('hash', sa.String(64), nullable=False),
    )
    op.create_index('ix_auditoria_momento', 'evento_auditoria', ['momento'])
    op.create_index('ix_auditoria_usuario', 'evento_auditoria', ['usuario_id', 'momento'])
    op.create_index('ix_auditoria_empresa', 'evento_auditoria', ['empresa_id', 'momento'])
    op.create_index('ix_auditoria_acao', 'evento_auditoria', ['acao', 'momento'])
    op.create_table(
        'auditoria_checkpoint',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('evento_id', ID, nullable=False),
        sa.Column('hash', sa.String(64), nullable=False),
        sa.Column('verificado_em', sa.DateTime(timezone=True), nullable=False),
    )
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(TRIGGER)


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP TRIGGER IF EXISTS tg_auditoria_somente_insercao ON evento_auditoria")
        op.execute("DROP FUNCTION IF EXISTS auditoria_somente_insercao()")
    op.drop_table('auditoria_checkpoint')
    op.drop_table('evento_auditoria')
