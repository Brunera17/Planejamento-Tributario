"""O exemplo da carga precisa chegar a 100%, sem pendências, aprovado e com PDF final."""
import io
import json
from pypdf import PdfReader
from sqlalchemy import func, select

from decimal import Decimal

from app.models import (FolhaMensal, HistoricoStatus, ItemDespesa, Levantamento, LevantamentoItem, NotaFiscal, NotaItem,
                        Planejamento, RelatorioPdf, Simulacao, Usuario)
from app.seeds.exemplo import carregar_exemplo, concluir_exemplo
from app.services import progresso, relatorio_pdf
from app.services.entrada import ITEM_FOLHA, montar_entrada


def test_exemplo_completo(fabrica_sessao):
    with fabrica_sessao() as db:
        p = carregar_exemplo(db)
        db.commit()
        pct, blocos = progresso.calcular(db, p)
        assert pct == 100, [(b.codigo, b.pendencias[:3]) for b in blocos if b.pendencias]
        assert all(b.preenchidos == b.esperados for b in blocos)
        ids_notas = select(NotaFiscal.id).where(NotaFiscal.planejamento_id == p.id)
        n_notas = db.scalar(select(func.count()).select_from(ids_notas.subquery()))
        n_itens = db.scalar(select(func.count()).select_from(NotaItem).where(NotaItem.nota_fiscal_id.in_(ids_notas)))
        assert n_notas and n_itens

        concluir_exemplo(db, p)
        sim = db.scalar(select(Simulacao).where(Simulacao.planejamento_id == p.id))
        assert p.status == "APROVADO"
        assert (sim.tipo, sim.pendencias, sim.desatualizada) == ("FINAL", None, False)
        assert sim.aprovada_em is not None
        rel = db.scalar(select(RelatorioPdf).where(RelatorioPdf.planejamento_id == p.id))
        assert rel.preliminar is False
        texto = "\n".join(pag.extract_text() for pag in PdfReader(io.BytesIO(relatorio_pdf.ler(rel))).pages)  # cifrado no disco
        for trecho in ["Bens próprios", "Utilitário de entregas", "14/03/2023", "R$ 110.450,00", "Todos os 27 documentos",
                       "Não se aplica: A empresa não", "exemplo-doc-1-2026-06.pdf"]:
            assert trecho in texto, trecho
        assert texto.count("Outras: Taxa de licença de funcionamento") == 1  # uma linha, com os três meses

        concluir_exemplo(db, carregar_exemplo(db))  # repetir a carga não duplica
        assert len(db.scalars(select(Simulacao).where(Simulacao.planejamento_id == p.id)).all()) == 1

        # retenção: aprovada a simulação, as notas e os itens são apagados; o PDF final continua sem pendências
        assert db.scalar(select(func.count()).select_from(NotaFiscal).where(NotaFiscal.planejamento_id == p.id)) == 0
        assert db.scalar(select(func.count()).select_from(NotaItem)
                         .where(NotaItem.nota_fiscal_id.not_in(select(NotaFiscal.id)))) == 0
        motivo = db.scalar(select(HistoricoStatus.motivo).where(HistoricoStatus.planejamento_id == p.id,
                                                                 HistoricoStatus.status_para == "APROVADO"))
        assert motivo == f"Simulação v{sim.versao} aprovada; {n_notas} notas e {n_itens} itens apagados"
        assert progresso.calcular(db, p)[0] == 100  # sem as notas, o aprovado não volta a acusar saídas pendentes
        contador = db.scalar(select(Usuario).where(Usuario.usuario == "contador"))
        dados = relatorio_pdf.coletar(db, sim, contador, None)
        assert (dados.progresso, dados.pendencias, dados.preliminar) == (100, [], False)


def test_reabrir_aprovado_exige_notas_de_novo(cliente, contador, fabrica_sessao):
    with fabrica_sessao() as db:
        p = carregar_exemplo(db)
        concluir_exemplo(db, p)
        db.commit()
        pid = p.id
        sim = db.scalar(select(Simulacao).where(Simulacao.planejamento_id == pid))
        sid, gravado = sim.id, json.loads(sim.resultado_json)["crescimento"]
    r = cliente.get(f"/api/simulacoes/{sid}/crescimento", headers=contador, params={"rbt12": ["3000000"]})
    assert r.status_code == 422 and "apagadas" in r.json()["erro"]
    r = cliente.get(f"/api/simulacoes/{sid}/crescimento", headers=contador)
    assert r.status_code == 200 and r.json() == gravado and gravado  # os valores gravados continuam
    assert cliente.get(f"/api/planejamentos/{pid}/progresso", headers=contador).json()["progresso"] == 100

    xml = b"<nfeProc/>"  # o conteúdo nem é lido: a recusa vem antes
    r = cliente.post(f"/api/planejamentos/{pid}/nfe", headers=contador, files={"arquivo": ("n.xml", xml)})
    assert r.status_code == 409 and "aprovado" in r.json()["erro"]

    r = cliente.post(f"/api/planejamentos/{pid}/status", headers=contador, json={"status": "EM_COLETA", "motivo": "Refazer"})
    assert r.status_code == 200 and r.json()["progresso"] < 100  # reaberto, as notas apagadas voltam a faltar
    r = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador)
    assert r.status_code == 422 and "Importe as notas" in r.json()["erro"]  # nunca simula com receita zero
    with fabrica_sessao() as db:  # o exemplo é compartilhado pela suíte: volta a ficar aprovado
        db.get(Planejamento, pid).status = "APROVADO"
        db.commit()


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
