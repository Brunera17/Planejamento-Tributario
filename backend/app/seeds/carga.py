"""Carga inicial do banco.

Uso:
    python -m app.seeds.carga            # tabelas legais, catálogo, documentos, pesos e usuários de demonstração
    python -m app.seeds.carga --demo     # + planejamento de demonstração (caso de referência)
"""
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.seguranca import gerar_hash
from app.db.session import SessionLocal
from app.models import (
    CfopRegra,
    CompraMensal,
    DevolucaoMensal,
    Empresa,
    GrupoDespesa,
    ItemDespesa,
    Levantamento,
    LevantamentoItem,
    NcmRegra,
    NotaFiscal,
    NotaItem,
    ParametroTributario,
    PesoProgresso,
    Planejamento,
    ReformaCronograma,
    SimplesFaixa,
    TipoDocumento,
    Usuario,
)
from app.seeds.exemplo import carregar_exemplo, concluir_exemplo
from app.seeds.tabelas import ler
from app.services import progresso
from app.services.progresso import PESOS_PADRAO

TIPOS_DOCUMENTO = [
    "Relatório financeiro de caixa ou planilha financeira",
    "Extrato bancário",
    "Extrato de aplicação financeira PJ",
    "Relatório de inadimplência (vencidos há mais de 6 meses)",
    "XML ou relatório de saídas",
    "Relatório de entradas",
    "Relatório de tarifas do marketplace",
    "Extrato do PGDAS-D (RBT12)",
    "Inventário de estoque",
]

# despesa da planilha de referência -> item do catálogo
DE_PARA_DESPESAS = {
    "Publicidade e propaganda": "Publicidade e Propaganda",
    "Fretes": "Fretes",
    "Tarifas armazenamento Mercado Livre": "Tarifas de Armazenamento (marketplace)",
    "Tarifas envios Mercado Livre": "Tarifas de Envio (marketplace)",
    "Tarifas vendas Mercado Livre": "Tarifas de Venda / Comissão (marketplace)",
    "Tarifas de envio Full Mercado Livre": "Tarifas de Envio Full (marketplace)",
    "Contabilidade": "Honorários Contábeis",
    "Escritório": "Material de Escritório",
    "Garantia": "Garantia",
    "Tarifas Mercado Livre – campanhas de publicidade": "Campanhas de Publicidade (marketplace)",
}


def _upsert(db: Session, modelo, chave: dict, valores: dict):
    obj = db.scalar(select(modelo).filter_by(**chave))
    if obj is None:
        obj = modelo(**chave)
        db.add(obj)
    for k, v in valores.items():
        setattr(obj, k, v)
    return obj


def carregar_tabelas(db: Session) -> None:
    s = ler("simples_anexo1.json")
    inicio = date.fromisoformat(s["vigencia_inicio"])
    for f in s["faixas"]:
        _upsert(db, SimplesFaixa, {"anexo": s["anexo"], "faixa": f["faixa"], "vigencia_inicio": inicio},
                {k: Decimal(v) for k, v in f.items() if k != "faixa"})
    for p in ler("parametros.json"):
        _upsert(db, ParametroTributario, {"chave": p["chave"], "vigencia_inicio": date(2000, 1, 1)},
                {"valor": Decimal(p["valor"]), "descricao": p["descricao"], "fundamento": p["fundamento"]})
    for a in ler("reforma_cronograma.json")["anos"]:
        _upsert(db, ReformaCronograma, {"ano": a["ano"]},
                {"cbs": Decimal(a["cbs"]), "ibs": Decimal(a["ibs"]), "fator_icms": Decimal(a["fator_icms"]),
                 "situacao": a["situacao"]})
    for c in ler("cfop_regras.json"):
        _upsert(db, CfopRegra, {"cfop": c["cfop"]}, {"natureza": c["natureza"], "gera_receita": c["gera_receita"]})
    for n in ler("ncm_regras.json"):
        _upsert(db, NcmRegra, {"ncm": n["ncm"]}, {k: n[k] for k in (
            "monofasico", "confianca", "sujeito_st", "indicio_ncm_incorreto", "fundamento", "produto_exemplo",
            "observacao", "requer_revisao", "acao_recomendada", "cst_ibs_cbs", "cclass_trib", "beneficio_reforma")})


def carregar_catalogo(db: Session) -> None:
    for gi, g in enumerate(ler("catalogo_despesas.json")["grupos"], start=1):
        grupo = _upsert(db, GrupoDespesa, {"nome": g["nome"]}, {"ordem": gi})
        db.flush()
        for ii, it in enumerate(g["itens"], start=1):
            _upsert(db, ItemDespesa, {"grupo_id": grupo.id, "nome": it["nome"]}, {
                "ordem": gi * 100 + ii, "dedutivel_irpj_csll": it["d"], "credito_pis_cofins": it["pc"],
                "credito_ibs_cbs": it["ibs"], "natureza": it.get("natureza"), "ativo": it.get("ativo", True)})
    for i, nome in enumerate(TIPOS_DOCUMENTO, start=1):
        _upsert(db, TipoDocumento, {"nome": nome}, {"ordem": i})
    for bloco, peso in PESOS_PADRAO.items():
        if db.get(PesoProgresso, bloco) is None:
            db.add(PesoProgresso(bloco=bloco, peso=peso))


def carregar_usuarios_demo(db: Session) -> None:
    for login, nome, perfil in (("contador", "Contador Demonstração", "CONTADOR"),
                                ("analista", "Analista Demonstração", "ANALISTA")):
        if db.scalar(select(Usuario).where(Usuario.usuario == login)) is None:
            db.add(Usuario(nome=nome, usuario=login, senha_hash=gerar_hash("demo123"), perfil=perfil))


def carregar_demo(db: Session) -> Planejamento:
    """Empresa e planejamento de demonstração com os dados agregados do caso de referência."""
    fx = ler("caso_referencia.json")
    emp = _upsert(db, Empresa, {"cnpj": "11222333000181"}, {
        "razao_social": "AUTOPEÇAS DEMONSTRAÇÃO LTDA", "regime_tributario": fx["regime_atual"], "anexo_simples": "I",
        "uf": fx["uf"], "cnae": "4530703", "atividade": "COMERCIO", "representante_legal": "Representante Demo",
        "telefone": "11999990000"})
    contador = db.scalar(select(Usuario).where(Usuario.usuario == "contador"))
    db.flush()
    comps = fx["competencias"]
    p = db.scalar(select(Planejamento).where(Planejamento.empresa_id == emp.id,
                                              Planejamento.competencia_inicial == comps[0]))
    if p is not None:
        return p
    p = Planejamento(empresa_id=emp.id, competencia_inicial=comps[0], competencia_final=comps[-1],
                     criado_por=contador.id)
    db.add(p)
    db.flush()

    for c in comps:
        for ambito, uf, sufixo in (("Interna", fx["uf"], "INT"), ("Interestadual", "MG", "EST")):
            itens = [i for i in fx["itens"] if i["competencia"] == c and i["ambito"] == ambito]
            nota = NotaFiscal(planejamento_id=p.id, chave_acesso=f"DEMO{c.replace('-', '')}{sufixo}",
                              numero=f"{c}-{sufixo}", data_emissao=date.fromisoformat(c + "-01"), competencia=c,
                              tipo="SAIDA", uf_emitente=fx["uf"], uf_destinatario=uf)
            db.add(nota)
            db.flush()
            db.add_all(NotaItem(nota_fiscal_id=nota.id, n_item=n, ncm=i["ncm"], cfop=i["cfop"],
                                descricao=f"{i['qtd_linhas']} itens agregados", vl_produtos=Decimal(i["valor"]),
                                vl_total=Decimal(i["valor"])) for n, i in enumerate(itens, start=1))
        db.add(CompraMensal(planejamento_id=p.id, competencia=c, valor=Decimal(fx["compras"][c])))
        db.add(DevolucaoMensal(planejamento_id=p.id, competencia=c, valor=Decimal(fx["devolucoes"][c])))

    catalogo = {i.nome: i for i in db.scalars(select(ItemDespesa))}
    for ci, c in enumerate(comps):
        lv = Levantamento(planejamento_id=p.id, competencia=c, criado_por=contador.id)
        db.add(lv)
        db.flush()
        for d in fx["despesas"]:
            item = catalogo[DE_PARA_DESPESAS[d["descricao"]]]
            db.add(LevantamentoItem(levantamento_id=lv.id, item_despesa_id=item.id, valor=Decimal(d["valores"][ci])))
    db.flush()
    progresso.atualizar(db, p)
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--demo", action="store_true", help="carrega também os planejamentos de demonstração e o exemplo completo")
    args = ap.parse_args()
    with SessionLocal() as db:
        carregar_tabelas(db)
        carregar_catalogo(db)
        carregar_usuarios_demo(db)
        db.flush()
        if args.demo:
            p = carregar_demo(db)
            print(f"Planejamento de demonstração: id {p.id}")
            exemplo = carregar_exemplo(db)
            db.commit()
            concluir_exemplo(db, exemplo)
            print(f"Exemplo completo: planejamento {exemplo.id}, {exemplo.progresso}%, {exemplo.status}")
        db.commit()
    print("Carga concluída.")


if __name__ == "__main__":
    main()
