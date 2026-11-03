"""cronograma da reforma editavel

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-03 12:00:00

Fonte e autoria no cronograma da Reforma, histórico de alterações e a CBS de 11,3% calculada pelo TCU
(Acórdão 2933/2026-Plenário) no lugar da projeção de 8,8%. Só troca os anos que ainda têm o valor da
carga inicial: um ano ajustado à mão fica como está.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FONTE_ANTIGA = "EC 132/2023 e LC 214/2025 – alíquotas de referência projetadas: CBS 8,8%, IBS 17,7%"
FONTE_NOVA = ("CBS de referência 11,3% (TCU, Acórdão 2933/2026-Plenário, 28/10/2026; pendente de resolução do Senado); "
              "2027 e 2028 reduzida em 0,1 ponto (LC 214/2025, art. 347)")
TROCAS = {2027: ("0.087", "0.112"), 2028: ("0.087", "0.112"), 2029: ("0.088", "0.113"), 2030: ("0.088", "0.113"),
          2031: ("0.088", "0.113"), 2032: ("0.088", "0.113"), 2033: ("0.088", "0.113")}


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('reforma_cronograma', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fonte', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('alterado_por', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('alterado_em', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key('fk_reforma_cronograma_alterado_por', 'usuario', ['alterado_por'], ['id'])
    op.create_table('reforma_historico',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ano', sa.Integer(), nullable=False),
    sa.Column('cbs', sa.Numeric(precision=12, scale=8), nullable=False),
    sa.Column('ibs', sa.Numeric(precision=12, scale=8), nullable=False),
    sa.Column('fator_icms', sa.Numeric(precision=12, scale=8), nullable=False),
    sa.Column('fonte', sa.String(length=300), nullable=True),
    sa.Column('substituido_por_fonte', sa.String(length=300), nullable=False),
    sa.Column('alterado_por', sa.Integer(), nullable=True),
    sa.Column('alterado_em', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['alterado_por'], ['usuario.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    con = op.get_bind()
    trocou = False
    for ano, (antiga, nova) in TROCAS.items():
        linha = con.execute(sa.text("SELECT cbs, ibs, fator_icms FROM reforma_cronograma WHERE ano = :a"), {"a": ano}).first()
        if linha is None or abs(float(linha.cbs) - float(antiga)) > 1e-9:
            continue  # ano ajustado à mão (ou inexistente): não mexe
        con.execute(sa.text(
            "INSERT INTO reforma_historico (ano, cbs, ibs, fator_icms, fonte, substituido_por_fonte, alterado_em) "
            "VALUES (:a, :c, :i, :f, :fa, :fn, CURRENT_TIMESTAMP)"),
            {"a": ano, "c": linha.cbs, "i": linha.ibs, "f": linha.fator_icms, "fa": FONTE_ANTIGA, "fn": FONTE_NOVA})
        con.execute(sa.text("UPDATE reforma_cronograma SET cbs = :c, fonte = :fn, alterado_em = CURRENT_TIMESTAMP WHERE ano = :a"),
                    {"c": nova, "fn": FONTE_NOVA, "a": ano})
        trocou = True
    con.execute(sa.text("UPDATE reforma_cronograma SET fonte = :fa WHERE fonte IS NULL"), {"fa": FONTE_ANTIGA})
    if trocou:  # as simulações foram calculadas com a CBS antiga
        con.execute(sa.text("UPDATE simulacao SET desatualizada = :v"), {"v": True})


def downgrade() -> None:
    """Downgrade schema."""
    con = op.get_bind()
    for ano, (antiga, nova) in TROCAS.items():
        con.execute(sa.text("UPDATE reforma_cronograma SET cbs = :c WHERE ano = :a AND cbs = :n"), {"c": antiga, "a": ano, "n": nova})
    op.drop_table('reforma_historico')
    with op.batch_alter_table('reforma_cronograma', schema=None) as batch_op:
        batch_op.drop_constraint('fk_reforma_cronograma_alterado_por', type_='foreignkey')
        batch_op.drop_column('alterado_em')
        batch_op.drop_column('alterado_por')
        batch_op.drop_column('fonte')
