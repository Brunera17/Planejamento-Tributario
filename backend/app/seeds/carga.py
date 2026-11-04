"""Carga inicial do banco.

Uso:
    python -m app.seeds.carga            # tabelas legais, catálogo, documentos e pesos (produção)
    python -m app.seeds.carga --demo     # + usuários e planejamentos de demonstração (desenvolvimento)

Em produção, o primeiro usuário (contador) vem de ADMIN_USUARIO, ADMIN_SENHA e ADMIN_NOME, só enquanto não houver
nenhum usuário cadastrado; depois disso, os usuários são mantidos pela tela.
"""
from __future__ import annotations

import argparse
import os
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.seguranca import gerar_hash
from app.db.session import SessionLocal
from app.models import (
    AliquotaUf,
    CfopRegra,
    CompraMensal,
    DevolucaoMensal,
    Empresa,
    GrupoDespesa,
    ItemDespesa,
    Levantamento,
    LevantamentoItem,
    NcmRegra,
    Norma,
    NotaFiscal,
    NotaItem,
    ParametroTributario,
    PesoProgresso,
    Planejamento,
    ReformaCronograma,
    RegraReforma,
    RegraSt,
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


def _incluir_se_falta(db: Session, modelo, chave: dict, valores: dict):
    """Para tabelas que o contador mantém pela tela: a carga só cria o que falta e nunca desfaz um ajuste."""
    obj = db.scalar(select(modelo).filter_by(**chave))
    if obj is None:
        db.add(modelo(**chave, **valores))


def carregar_tabelas(db: Session) -> None:
    for arquivo in ("simples_anexo1.json", "simples_anexo2.json"):
        s = ler(arquivo)
        inicio = date.fromisoformat(s["vigencia_inicio"])
        for f in s["faixas"]:
            _upsert(db, SimplesFaixa, {"anexo": s["anexo"], "faixa": f["faixa"], "vigencia_inicio": inicio},
                    {k: Decimal(v) for k, v in f.items() if k != "faixa"})
    for p in ler("parametros.json"):
        _incluir_se_falta(db, ParametroTributario, {"chave": p["chave"], "vigencia_inicio": date(2000, 1, 1)},
                {"valor": Decimal(p["valor"]), "descricao": p["descricao"], "fundamento": p["fundamento"]})
    reforma = ler("reforma_cronograma.json")
    for a in reforma["anos"]:
        _incluir_se_falta(db, ReformaCronograma, {"ano": a["ano"]},
                          {"cbs": Decimal(a["cbs"]), "ibs": Decimal(a["ibs"]), "fator_icms": Decimal(a["fator_icms"]),
                           "situacao": a["situacao"], "fonte": reforma["fonte"][:300]})
    for c in ler("cfop_regras.json"):
        _incluir_se_falta(db, CfopRegra, {"cfop": c["cfop"]}, {"natureza": c["natureza"], "gera_receita": c["gera_receita"]})
    for n in ler("ncm_regras.json"):
        _upsert(db, NcmRegra, {"ncm": n["ncm"]}, {k: n[k] for k in (
            "monofasico", "confianca", "sujeito_st", "indicio_ncm_incorreto", "fundamento", "produto_exemplo",
            "observacao", "requer_revisao", "acao_recomendada", "cst_ibs_cbs", "cclass_trib", "beneficio_reforma")})
    carregar_normas(db)
    carregar_aliquotas_uf(db)
    carregar_reducoes_reforma(db)


def carregar_reducoes_reforma(db: Session) -> None:
    lc214 = db.scalar(select(Norma.id).where(Norma.codigo == "lc214-2025"))
    for r in ler("reforma_reducoes.json")["regras"]:
        _incluir_se_falta(db, RegraReforma, {"ncm": r["ncm"], "anexo": r["anexo"], "item": r["item"]}, {
            "descricao": r["descricao"], "excecoes": ",".join(r["excecoes"]) or None, "reducao": Decimal(r["reducao"]),
            "condicao": r["condicao"], "cst": "200", "cclass_trib": r["cclass_trib"], "norma_id": lc214,
            "vigencia_inicio": date(2000, 1, 1)})


def carregar_aliquotas_uf(db: Session) -> None:
    for a in ler("aliquotas_uf.json")["aliquotas"]:
        _incluir_se_falta(db, AliquotaUf, {"uf": a["uf"], "vigencia_inicio": date.fromisoformat(a["vigencia_inicio"] or "2000-01-01")}, {
            "aliquota": Decimal(a["aliquota"]), "fcp": Decimal(a["fcp"]), "base_dupla": True, "fonte": a["fonte"][:300],
            "vigencia_fim": date.fromisoformat(a["vigencia_fim"]) if a["vigencia_fim"] else None})


def carregar_normas(db: Session) -> None:
    """Biblioteca de normas e a tabela de ST por NCM. O contador mantém as duas pela tela: a carga só inclui o que falta."""
    for n in ler("normas.json")["normas"]:
        _incluir_se_falta(db, Norma, {"codigo": n["codigo"]}, {k: v for k, v in n.items() if k != "codigo"})
    db.flush()
    ids = {n.codigo: n.id for n in db.scalars(select(Norma))}
    st = ler("st_sp.json")
    for r in st["regras"]:
        _incluir_se_falta(db, RegraSt, {"uf": st["uf"], "ncm": r["ncm"], "item": r["item"], "segmento": r["segmento"].capitalize()}, {
            "cest": r["cest"], "descricao": r["descricao"], "excecoes": ",".join(r["excecoes"]) or None,
            "vigencia_inicio": date.fromisoformat(r["vigencia_inicio"] or "2000-01-01"),
            "vigencia_fim": date.fromisoformat(r["vigencia_fim"]) if r["vigencia_fim"] else None,
            "norma_id": ids.get("portaria-cat-68-2019"), "revogada_por_id": ids.get(r["revogada_por"])})


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


def carregar_primeiro_usuario(db: Session) -> None:
    usuario, senha = os.environ.get("ADMIN_USUARIO", "").strip(), os.environ.get("ADMIN_SENHA", "")
    if not usuario or db.scalar(select(Usuario.id).limit(1)) is not None:
        return
    if len(senha) < 12:
        raise SystemExit("ADMIN_SENHA precisa ter pelo menos 12 caracteres")
    db.add(Usuario(nome=os.environ.get("ADMIN_NOME", "Contador").strip() or "Contador", usuario=usuario,
                   senha_hash=gerar_hash(senha), perfil="CONTADOR"))
    print(f"Primeiro usuário criado: {usuario}")


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
        if args.demo:
            carregar_usuarios_demo(db)
        else:
            carregar_primeiro_usuario(db)
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
