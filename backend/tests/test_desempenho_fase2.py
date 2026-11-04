"""Desempenho: as agregações no banco dão o mesmo resultado da soma item a item, e a memória por requisição
não devolve dado velho depois de uma gravação."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.models import Empresa, NotaFiscal, NotaItem, Planejamento, Usuario
from app.services import memo, premissas_auto, revisao_produtos
from app.services.reducoes_reforma import TabelaReducoes
from app.services.substituicao import Regra, TabelaSt


@pytest.fixture
def db(fabrica_sessao):
    """Sessão desfeita no fim: os dados do teste não vazam para os outros."""
    with fabrica_sessao() as s:
        yield s
        s.rollback()


def _planejamento(db) -> Planejamento:
    emp = Empresa(razao_social="DESEMPENHO FASE 2 LTDA", cnpj="71555222000140", regime_tributario="LUCRO_PRESUMIDO", uf="SP")
    db.add(emp)
    db.flush()
    p = Planejamento(empresa_id=emp.id, competencia_inicial="2026-07", competencia_final="2026-07",
                     criado_por=db.scalar(select(Usuario.id).limit(1)))
    db.add(p)
    db.flush()
    return p


def _nota(db, p, chave, tipo, itens, **campos):
    nf = NotaFiscal(planejamento_id=p.id, chave_acesso=chave, numero=chave[-4:], data_emissao=date(2026, 7, 10),
                    competencia="2026-07", tipo=tipo, **campos)
    db.add(nf)
    db.flush()
    for n, (ncm, cfop, valor, extra) in enumerate(itens, start=1):
        db.add(NotaItem(nota_fiscal_id=nf.id, n_item=n, ncm=ncm, cfop=cfop, vl_produtos=valor, vl_total=valor, **extra))
    db.flush()
    return nf


def test_premissas_agregadas_somam_como_item_a_item(db):
    p = _planejamento(db)
    # compra interna de fornecedor do regime normal, em dois itens do mesmo grupo
    _nota(db, p, "E" * 40 + "0001", "ENTRADA", [("87089990", 1102, Decimal("100"), {"orig_icms": "0"}),
                                               ("87089990", 1102, Decimal("50"), {"orig_icms": "0"})],
          uf_emitente="SP", crt_emitente="3")
    # compra importada de outro estado, de fornecedor do Simples
    _nota(db, p, "E" * 40 + "0002", "ENTRADA", [("87089990", 2102, Decimal("200"), {"orig_icms": "1"})],
          uf_emitente="MG", crt_emitente="1")
    # vendas: 60 a consumidor final em duas notas, 50 a empresa
    for i, (final, valor) in enumerate([(True, "30"), (True, "30"), (False, "50")], start=1):
        _nota(db, p, "S" * 40 + f"{i:04d}", "SAIDA", [("87089990", 5102, Decimal(valor), {"cst_icms": "00"})],
              uf_destinatario="SP", consumidor_final=final)

    auto = premissas_auto.derivar.sem_memo(db, p)

    interna = premissas_auto.aliquota_interna(db, p)
    assert auto.composicao == {interna: Decimal("0.4286"), Decimal("0.04"): Decimal("0.5714")}
    assert auto.fonte_composicao.startswith("2 notas de compra")  # notas distintas, não itens
    assert auto.premissas["pct_compras_credito_ibs_cbs"].valor == Decimal("0.4286")
    assert auto.premissas["vendas_b2c"].valor is True  # 60 de 110
    assert "54,5%" in auto.premissas["vendas_b2c"].fonte
    assert auto.premissas["aplicar_st_vendas_internas"].valor is False


def test_memoria_vale_ate_a_proxima_gravacao(db):
    p = _planejamento(db)
    primeira = revisao_produtos.analisar(db, p)
    assert revisao_produtos.analisar(db, p) is primeira  # mesma requisição, sem gravação: reaproveita

    _nota(db, p, "S" * 40 + "0009", "SAIDA", [("87089990", 5102, Decimal("10"), {})], uf_destinatario="SP")
    depois_do_flush = revisao_produtos.analisar(db, p)
    assert depois_do_flush is not primeira
    assert len(depois_do_flush) == len(primeira) + 1

    db.execute(update(NotaItem).where(NotaItem.ncm == "87089990").values(vl_total=Decimal("20")))
    assert revisao_produtos.analisar(db, p) is not depois_do_flush  # gravação em massa também apaga


def test_memoria_nao_atravessa_sessoes(fabrica_sessao):
    with fabrica_sessao() as a, fabrica_sessao() as b:
        p = a.scalars(select(Planejamento)).first()
        pb = b.get(Planejamento, p.id)
        assert revisao_produtos.analisar(a, p) is not revisao_produtos.analisar(b, pb)
        memo.limpar(a)
        assert memo.CHAVE not in a.info


def test_tabela_st_e_reducoes_lembram_por_ncm():
    regras = [Regra("8708", ("870899",), "Autopeças", "1.0", date(2020, 1, 1), date(2026, 9, 30), None),
              Regra("870899", (), "Autopeças", "1.1", date(2020, 1, 1), None, None)]
    tabela = TabelaSt(sorted(regras, key=lambda r: -len(r.ncm)))
    assert tabela.vigente("87089990", "2026-07").item == "1.1"  # exceção da regra geral, regra específica vale
    assert tabela.vigente("87081000", "2026-07").item == "1.0"
    assert tabela.vigente("87081000", "2026-10") is None  # depois do fim da vigência
    assert tabela.vigente("87081000", "2026-07") is tabela.vigente("87081000", "2026-07")

    reducoes = TabelaReducoes([])
    assert reducoes.buscar("10063021") is None
    assert "10063021" in reducoes._por_ncm  # a ausência também fica lembrada
