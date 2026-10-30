"""Exemplo completo: empresa fictícia com 100% das informações, simulação aprovada e relatório final.

Os valores são fictícios (o faturamento é o do caso de referência reduzido em 15%). Os documentos têm só o
nome do arquivo: o envio real de arquivos ainda não existe no sistema.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Bem,
    CompraMensal,
    CompraOrigem,
    DevolucaoMensal,
    Documento,
    Empresa,
    FolhaMensal,
    GrupoDespesa,
    HistoricoStatus,
    ItemDespesa,
    Levantamento,
    LevantamentoGrupo,
    LevantamentoItem,
    NotaFiscal,
    NotaItem,
    OutraDespesa,
    Planejamento,
    PremissaPlanejamento,
    RevisaoProduto,
    TipoDocumento,
    Usuario,
)
from app.seeds.tabelas import ler
from app.services import progresso, relatorio_pdf, revisao_produtos, simulacao

CNPJ = "34567890000130"
FATOR = Decimal("0.85")
CENTAVO = Decimal("0.01")

# valor mensal dos itens do catálogo que não vêm do caso de referência
DESPESAS_MENSAIS = {
    "Brindes": "0", "Amostras Grátis": "0", "Embalagens": "3850.00",
    "Alimentação de Sócios e Administradores": "0", "Assistência Médica, Odontológica e Convênios": "1240.00",
    "Vale Refeição / Alimentação": "1980.00", "Vale Transporte": "860.00", "Combustíveis e Lubrificantes": "720.00",
    "Manutenção de Veículos": "310.00", "Honorários Advocatícios": "0",
    "Aluguel de Imóveis": "6500.00", "Energia Elétrica": "940.00", "Telefone e Internet": "389.90", "Seguros": "410.00",
    "Revistas e Publicações": "0", "Vigilância e Segurança": "280.00", "Manutenção e Conservação de Imóveis": "150.00",
    "Materiais de Higiene e Limpeza": "120.00", "Copa e Cozinha": "95.00", "Perdas de Mercadorias": "460.00",
    "IPVA Veículos": "0", "IPTU Imóveis e Terrenos": "0", "Despesas com Cartório": "45.00", "Despesas com Correio": "130.00",
    "Softwares": "690.00", "Pedágios": "85.00", "Despesas Bancárias (taxas, tarifas)": "215.00",
    "Taxas de Maquininha de Cartão": "0",
}
DE_PARA = {
    "Publicidade e propaganda": "Publicidade e Propaganda", "Fretes": "Fretes",
    "Tarifas armazenamento Mercado Livre": "Tarifas de Armazenamento (marketplace)",
    "Tarifas envios Mercado Livre": "Tarifas de Envio (marketplace)",
    "Tarifas vendas Mercado Livre": "Tarifas de Venda / Comissão (marketplace)",
    "Tarifas de envio Full Mercado Livre": "Tarifas de Envio Full (marketplace)",
    "Contabilidade": "Honorários Contábeis", "Escritório": "Material de Escritório", "Garantia": "Garantia",
    "Tarifas Mercado Livre – campanhas de publicidade": "Campanhas de Publicidade (marketplace)",
}
FOLHA = {"2026-06": ("18400.00", "6000.00"), "2026-07": ("18400.00", "6000.00"), "2026-08": ("19150.00", "6000.00")}
PREMISSAS = {"rbt12_informado": "2240000.00", "estoque_inicial": "182000.00", "estoque_final": "191500.00"}


def _centavos(v: Decimal) -> Decimal:
    return v.quantize(CENTAVO)


def carregar_exemplo(db: Session) -> Planejamento:
    """Cria o planejamento (sem simular). Repetir a carga devolve o que já existe."""
    existente = db.scalar(select(Planejamento).join(Empresa).where(Empresa.cnpj == CNPJ))
    if existente is not None:
        return existente
    fx = ler("caso_referencia.json")
    comps = fx["competencias"]
    contador = db.scalar(select(Usuario).where(Usuario.usuario == "contador"))
    emp = Empresa(razao_social="DISTRIBUIDORA MODELO DE AUTOPEÇAS LTDA", cnpj=CNPJ, regime_tributario="SIMPLES_NACIONAL",
                  anexo_simples="I", uf="SP", cnae="4530703", atividade="COMERCIO",
                  representante_legal="Helena Exemplo", telefone="1140028922")
    db.add(emp)
    db.flush()
    p = Planejamento(empresa_id=emp.id, competencia_inicial=comps[0], competencia_final=comps[-1], criado_por=contador.id)
    db.add(p)
    db.flush()

    for c in comps:
        for ambito, uf, sufixo in (("Interna", "SP", "INT"), ("Interestadual", "MG", "EST")):
            nota = NotaFiscal(planejamento_id=p.id, chave_acesso=f"EXEMPLO{c.replace('-', '')}{sufixo}", numero=f"{c}-{sufixo}",
                              data_emissao=date.fromisoformat(c + "-15"), competencia=c, tipo="SAIDA", uf_emitente="SP",
                              uf_destinatario=uf)
            db.add(nota)
            db.flush()
            itens = [i for i in fx["itens"] if i["competencia"] == c and i["ambito"] == ambito]
            db.add_all(NotaItem(nota_fiscal_id=nota.id, n_item=n, ncm=i["ncm"], cfop=i["cfop"], descricao="Itens agregados por NCM",
                                vl_produtos=_centavos(Decimal(i["valor"]) * FATOR), vl_total=_centavos(Decimal(i["valor"]) * FATOR))
                       for n, i in enumerate(itens, start=1))
        db.add(CompraMensal(planejamento_id=p.id, competencia=c, valor=_centavos(Decimal(fx["compras"][c]) * FATOR)))
        db.add(DevolucaoMensal(planejamento_id=p.id, competencia=c, valor=_centavos(Decimal(fx["devolucoes"][c]) * FATOR)))
        folha, pro_labore = FOLHA[c]
        db.add(FolhaMensal(planejamento_id=p.id, competencia=c, folha=Decimal(folha), pro_labore=Decimal(pro_labore)))

    db.add_all([CompraOrigem(planejamento_id=p.id, origem="Fornecedores de SP", aliquota=Decimal("0.18"), percentual=Decimal("0.6")),
                CompraOrigem(planejamento_id=p.id, origem="Sul e Sudeste", aliquota=Decimal("0.12"), percentual=Decimal("0.4"))])
    db.add_all(PremissaPlanejamento(planejamento_id=p.id, chave=k, valor=json.dumps(v), alterado_por=contador.id)
               for k, v in PREMISSAS.items())

    catalogo = {i.nome: i for i in db.scalars(select(ItemDespesa).where(ItemDespesa.ativo))}
    grupos = db.scalars(select(GrupoDespesa)).all()
    tipos = db.scalars(select(TipoDocumento)).all()
    gerais = next(g for g in grupos if g.nome == "Despesas Gerais")
    for ci, c in enumerate(comps):
        lv = Levantamento(planejamento_id=p.id, competencia=c, status="CONFERIDO", criado_por=contador.id,
                          enviado_em=datetime(2026, 9, 10, 14, 0, tzinfo=UTC))
        db.add(lv)
        db.flush()
        valores = {nome: Decimal(v) for nome, v in DESPESAS_MENSAIS.items()}
        for d in fx["despesas"]:
            valores[DE_PARA[d["descricao"]]] = _centavos(Decimal(d["valores"][ci]) * FATOR)
        faltando = catalogo.keys() - valores.keys()
        if faltando:
            raise ValueError(f"Itens do catálogo sem valor no exemplo: {sorted(faltando)}")
        db.add_all(LevantamentoItem(levantamento_id=lv.id, item_despesa_id=catalogo[n].id, valor=v)
                   for n, v in valores.items())
        db.add_all(LevantamentoGrupo(levantamento_id=lv.id, grupo_id=g.id, possui_outras=g.id == gerais.id) for g in grupos)
        db.add(OutraDespesa(levantamento_id=lv.id, grupo_id=gerais.id, descricao="Taxa de licença de funcionamento", valor=Decimal("180.00")))
        for t in tipos:
            if "aplicação financeira" in t.nome:
                db.add(Documento(levantamento_id=lv.id, tipo_documento_id=t.id, nao_se_aplica=True,
                                 justificativa="A empresa não mantém aplicações financeiras"))
            else:
                db.add(Documento(levantamento_id=lv.id, tipo_documento_id=t.id, arquivo=f"exemplo-doc-{t.id}-{c}.pdf"))

    db.add_all([Bem(empresa_id=emp.id, tipo="VEICULOS", descricao="Utilitário de entregas", data_aquisicao=date(2023, 3, 14), valor=Decimal("89900.00")),
                Bem(empresa_id=emp.id, tipo="MOVEIS_UTENSILIOS", descricao="Estantes do depósito", data_aquisicao=date(2024, 8, 2), valor=Decimal("14300.00")),
                Bem(empresa_id=emp.id, tipo="MAQUINAS_EQUIPAMENTOS", descricao="Empilhadeira manual", data_aquisicao=date(2025, 1, 20), valor=Decimal("6250.00"))])
    p.observacoes_aceitas_por, p.observacoes_aceitas_em = contador.id, datetime(2026, 9, 10, 14, 0, tzinfo=UTC)
    db.flush()
    for pr in revisao_produtos.analisar(db, p):
        if pr.pendente:
            db.add(RevisaoProduto(planejamento_id=p.id, cod_produto=pr.cod_produto, ncm_nota=pr.ncm_nota, monofasico=pr.monofasico,
                                  motivo="Exemplo: condição conferida na nota do fornecedor", revisado_por=contador.id))
    db.flush()
    progresso.atualizar(db, p)
    return p


def concluir_exemplo(db: Session, p: Planejamento) -> None:
    """Percorre o fluxo até o fim: conferência, simulação final, aprovação e relatório sem marca de preliminar."""
    if p.status == "APROVADO":
        return
    contador = db.scalar(select(Usuario).where(Usuario.usuario == "contador"))
    for de, para in (("EM_COLETA", "EM_CONFERENCIA"), ("EM_CONFERENCIA", "PRONTO_PARA_SIMULAR")):
        db.add(HistoricoStatus(planejamento_id=p.id, status_de=de, status_para=para, usuario_id=contador.id))
        p.status = para
    db.flush()
    sim = simulacao.executar(db, p, contador.id)
    if sim.tipo != "FINAL":
        raise ValueError(f"O exemplo deveria ficar sem pendências: {sim.pendencias}")
    simulacao.aprovar(db, sim, contador.id)
    relatorio_pdf.gerar(db, sim, contador)
