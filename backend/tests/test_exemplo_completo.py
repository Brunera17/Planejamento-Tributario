"""O exemplo da carga precisa chegar a 100%, sem pendências, aprovado e com PDF final."""
from sqlalchemy import select

from decimal import Decimal

from app.models import FolhaMensal, ItemDespesa, Levantamento, LevantamentoItem, RelatorioPdf, Simulacao
from app.seeds.exemplo import carregar_exemplo, concluir_exemplo
from app.services import progresso
from app.services.entrada import ITEM_FOLHA, montar_entrada


def test_exemplo_completo(fabrica_sessao):
    with fabrica_sessao() as db:
        p = carregar_exemplo(db)
        db.commit()
        pct, blocos = progresso.calcular(db, p)
        assert pct == 100, [(b.codigo, b.pendencias[:3]) for b in blocos if b.pendencias]
        assert all(b.preenchidos == b.esperados for b in blocos)

        concluir_exemplo(db, p)
        sim = db.scalar(select(Simulacao).where(Simulacao.planejamento_id == p.id))
        assert p.status == "APROVADO"
        assert (sim.tipo, sim.pendencias, sim.desatualizada) == ("FINAL", None, False)
        assert sim.aprovada_em is not None
        rel = db.scalar(select(RelatorioPdf).where(RelatorioPdf.planejamento_id == p.id))
        assert rel.preliminar is False

        concluir_exemplo(db, carregar_exemplo(db))  # repetir a carga não duplica
        assert len(db.scalars(select(Simulacao).where(Simulacao.planejamento_id == p.id)).all()) == 1


def test_folha_nao_e_deduzida_duas_vezes(fabrica_sessao):
    with fabrica_sessao() as db:
        p = carregar_exemplo(db)
        item = db.scalar(select(ItemDespesa).where(ItemDespesa.nome == ITEM_FOLHA))
        assert item.ativo is False
        lv = db.scalar(select(Levantamento).where(Levantamento.planejamento_id == p.id, Levantamento.competencia == "2026-06"))
        db.add(LevantamentoItem(levantamento_id=lv.id, item_despesa_id=item.id, valor=Decimal("5000.00")))
        db.flush()

        def lancada():
            return [d for d in montar_entrada(db, p).entrada.despesas if d.descricao == ITEM_FOLHA]

        assert lancada() == []  # bloco de folha informado: o item antigo é ignorado

        folha = db.scalar(select(FolhaMensal).where(FolhaMensal.planejamento_id == p.id, FolhaMensal.competencia == "2026-06"))
        folha.folha = None
        db.flush()
        assert [d.valor for d in lancada()] == [Decimal("5000.00")]  # sem bloco de folha, o valor antigo vale
        db.rollback()
