"""Planejamentos, coleta de dados, importação de NF-e, progresso e pendências."""
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, UploadFile
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import DB, Contador, UsuarioAtual, obter_planejamento
from app.core.config import get_settings
from app.core.erros import ErroNegocio, NaoEncontrado
from app.models import (
    CompraMensal,
    CompraOrigem,
    DevolucaoMensal,
    Empresa,
    FolhaMensal,
    HistoricoStatus,
    ImportacaoNfe,
    Levantamento,
    LevantamentoGrupo,
    LevantamentoItem,
    NotaFiscal,
    NotaItem,
    OutraDespesa,
    Planejamento,
    PremissaPlanejamento,
    RevisaoProduto,
    Usuario,
)
from app.schemas.planejamento import (
    FolhaCompetencia,
    LevantamentoEntrada,
    OrigemCompra,
    PlanejamentoEntrada,
    PlanejamentoSaida,
    ProgressoSaida,
    StatusEntrada,
    ValorCompetencia,
)
from app.services import estoque_st, nfe_canceladas, planilha_mensal, progresso, relatorio_contabil, retencao, revisao_produtos
from app.motor.lei_monofasico import Enquadramento, avaliar
from app.schemas.comum import Esquema
from app.seeds import tabelas
from app.services.entrada import PREMISSAS
from app.services.auditoria import auditar, auditar_uma_vez
from app.services.nfe_xml import ler_arquivos
from app.services.simulacao import marcar_desatualizada
from app.utils.paginacao import Deslocamento, Limite, pagina
from app.utils.upload import ler_limitado
from app.utils.validacao import somente_digitos

router = APIRouter(prefix="/planejamentos", tags=["Planejamentos e coleta"])

# status do planejamento -> status dos levantamentos mensais (fora de "em preenchimento", o mês fica só para consulta)
STATUS_LEVANTAMENTO = {"EM_COLETA": "EM_PREENCHIMENTO", "EM_CONFERENCIA": "ENVIADO", "PRONTO_PARA_SIMULAR": "CONFERIDO"}

OBSERVACOES = [
    "Todas as despesas, notas fiscais, comprovantes, contas bancárias e bens devem obrigatoriamente estar registrados "
    "no CNPJ (não é permitido usar o CPF dos sócios).",
    "É muito importante que o empresário mantenha o inventário de estoque atualizado (no mínimo uma contagem por ano).",
    "As despesas dedutíveis e os custos só podem ser utilizados com documentos válidos (nota fiscal, cupom fiscal, faturas etc.).",
]

TRANSICOES = {  # (de, para) -> exige contador?
    ("EM_COLETA", "EM_CONFERENCIA"): False,
    ("EM_CONFERENCIA", "PRONTO_PARA_SIMULAR"): True,
    ("EM_CONFERENCIA", "EM_COLETA"): True,
    ("PRONTO_PARA_SIMULAR", "EM_COLETA"): True,
    ("SIMULADO", "EM_COLETA"): True,
    ("APROVADO", "EM_COLETA"): True,
}


def _saida(p: Planejamento) -> PlanejamentoSaida:
    faltam, recebidos_em = progresso.documentos_recebidos(Session.object_session(p), p)
    return PlanejamentoSaida(
        id=p.id, empresa_id=p.empresa_id, razao_social=p.empresa.razao_social, cnpj=p.empresa.cnpj,
        regime_tributario=p.empresa.regime_tributario, competencia_inicial=p.competencia_inicial,
        competencia_final=p.competencia_final, status=p.status, progresso=p.progresso, sem_bens=p.sem_bens,
        criado_em=p.criado_em, documentos_faltando=faltam, documentos_recebidos_em=recebidos_em)


def _recusar_se_aprovado(db: Session, p: Planejamento) -> None:
    """Importar notas num planejamento aprovado desfaria a retenção. A linha fica travada (Postgres) até o fim da
    importação, então uma aprovação simultânea espera e não apaga notas que ainda estão entrando."""
    db.refresh(p, with_for_update={"of": Planejamento})  # só a linha do planejamento: a empresa vem por outer join
    if p.status == "APROVADO":
        raise ErroNegocio("Planejamento aprovado: reabra-o (volta para Em coleta) antes de importar notas", 409)


def _alterou(db: Session, p: Planejamento) -> None:
    """Toda gravação de dado de entrada recalcula o progresso e desatualiza as simulações."""
    db.flush()
    progresso.atualizar(db, p)
    marcar_desatualizada(db, p.id)
    db.commit()


def _competencia_valida(p: Planejamento, c: str) -> None:
    if c not in p.competencias():
        raise ErroNegocio(f"Competência {c} fora do período do planejamento", campos={"competencia": "fora do período"})


@router.get("", response_model=list[PlanejamentoSaida])
def listar(db: DB, _: UsuarioAtual, resposta: Response, status: str | None = None, empresa_id: int | None = None,
           busca: str | None = None, abertos: bool = False, limite: Limite = 50, deslocamento: Deslocamento = 0):
    q = select(Planejamento).join(Empresa).order_by(Planejamento.criado_em.desc(), Planejamento.id.desc())
    if status:
        q = q.where(Planejamento.status == status)
    if abertos:
        q = q.where(Planejamento.status != "APROVADO")
    if empresa_id:
        q = q.where(Planejamento.empresa_id == empresa_id)
    if busca:
        cnpj = somente_digitos(busca)  # o CNPJ é gravado só com dígitos; a busca pode vir com máscara
        q = q.where(or_(Empresa.razao_social.icontains(busca, autoescape=True), *([Empresa.cnpj.contains(cnpj)] if cnpj else [])))
    return [_saida(p) for p in pagina(db, q, limite, deslocamento, resposta)]


@router.post("", response_model=PlanejamentoSaida, status_code=201)
def criar(dados: PlanejamentoEntrada, db: DB, u: Contador):
    emp = db.get(Empresa, dados.empresa_id)
    if emp is None or not emp.ativo:
        raise NaoEncontrado("Empresa")
    if db.scalar(select(Planejamento.id).where(Planejamento.empresa_id == emp.id,
                                               Planejamento.competencia_inicial == dados.competencia_inicial)):
        raise ErroNegocio("Já existe planejamento desta empresa com a mesma competência inicial", 409)
    p = Planejamento(**dados.model_dump(), criado_por=u.id)
    db.add(p)
    db.flush()
    db.add(HistoricoStatus(planejamento_id=p.id, status_para="EM_COLETA", usuario_id=u.id, motivo="Criação"))
    progresso.atualizar(db, p)
    db.commit()
    return _saida(p)


@router.get("/{pid}", response_model=PlanejamentoSaida)
def detalhar(pid: int, db: DB, u: UsuarioAtual):
    p = obter_planejamento(db, pid)
    # a tela dispara vários GETs do mesmo planejamento; registra a abertura uma vez por sessão
    auditar_uma_vez(f"planejamento:{pid}", "PLANEJAMENTO_ABERTO", usuario=u, planejamento=p,
                    recurso_tipo="planejamento", recurso_id=pid)
    return _saida(p)


@router.post("/{pid}/status", response_model=PlanejamentoSaida)
def alterar_status(pid: int, dados: StatusEntrada, db: DB, u: UsuarioAtual):
    p = obter_planejamento(db, pid)
    chave = (p.status, dados.status)
    if chave not in TRANSICOES:
        raise ErroNegocio(f"Transição {p.status} → {dados.status} não permitida", campos={"status": "inválido"})
    if TRANSICOES[chave] and u.perfil != "CONTADOR":
        raise ErroNegocio("Somente o contador pode fazer esta transição", 403)
    if dados.status == "EM_CONFERENCIA" and p.observacoes_aceitas_em is None:
        raise ErroNegocio("Confirme a leitura das observações, na aba Despesas, antes de enviar para conferência", 409)
    if dados.status == "EM_COLETA" and not dados.motivo:
        raise ErroNegocio("Informe o motivo da devolução", campos={"motivo": "obrigatório"})
    db.add(HistoricoStatus(planejamento_id=p.id, status_de=p.status, status_para=dados.status, usuario_id=u.id,
                           motivo=dados.motivo))
    p.status = dados.status
    valores = {"status": STATUS_LEVANTAMENTO[dados.status]}
    if dados.status == "EM_CONFERENCIA":
        valores["enviado_em"] = datetime.now(UTC)
    db.execute(update(Levantamento).where(Levantamento.planejamento_id == pid).values(**valores))
    progresso.atualizar(db, p)  # reaberto depois da aprovação, as notas apagadas voltam a faltar
    db.commit()
    return _saida(p)


@router.get("/{pid}/historico")
def historico(pid: int, db: DB, _: UsuarioAtual):
    obter_planejamento(db, pid)
    nomes = {x.id: x.nome for x in db.scalars(select(Usuario))}
    return [{"de": h.status_de, "para": h.status_para, "usuario": nomes.get(h.usuario_id), "motivo": h.motivo, "data": h.data}
            for h in db.scalars(select(HistoricoStatus).where(HistoricoStatus.planejamento_id == pid)
                                .order_by(HistoricoStatus.data, HistoricoStatus.id))]


@router.get("/{pid}/progresso", response_model=ProgressoSaida)
def ver_progresso(pid: int, db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid)
    pct, blocos = progresso.calcular(db, p)
    return ProgressoSaida(progresso=pct, blocos=[{
        "codigo": b.codigo, "nome": progresso.NOMES[b.codigo], "peso": b.peso, "esperados": b.esperados,
        "preenchidos": b.preenchidos,
        "pendencias": [{"competencia": c, "descricao": d} for c, d in b.pendencias]} for b in blocos])


# ------------------------------------------------------------------ coleta


@router.get("/{pid}/coleta")
def ver_coleta(pid: int, db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid)

    def mensal(modelo):
        return {m.competencia: m.valor for m in db.scalars(select(modelo).where(modelo.planejamento_id == pid))}

    return {
        "competencias": p.competencias(),
        "compras": mensal(CompraMensal),
        "devolucoes": mensal(DevolucaoMensal),
        "folha": {f.competencia: {"folha": f.folha, "pro_labore": f.pro_labore}
                  for f in db.scalars(select(FolhaMensal).where(FolhaMensal.planejamento_id == pid))},
        "composicao_compras": [{"origem": o.origem, "aliquota": o.aliquota, "percentual": o.percentual}
                               for o in db.scalars(select(CompraOrigem).where(CompraOrigem.planejamento_id == pid))],
        "premissas": {pr.chave: json.loads(pr.valor) for pr in
                      db.scalars(select(PremissaPlanejamento).where(PremissaPlanejamento.planejamento_id == pid))},
        # premissas_auto, composicao_auto, indicio_st e saidas: das notas, ou do retrato gravado na aprovação
        **retencao.ler(db, p, "coleta"),
    }


def _gravar_mensal(db: Session, p: Planejamento, modelo, valores: list[ValorCompetencia]) -> None:
    for v in valores:
        _competencia_valida(p, v.competencia)
        m = db.scalar(select(modelo).where(modelo.planejamento_id == p.id, modelo.competencia == v.competencia))
        if m is None:
            db.add(modelo(planejamento_id=p.id, competencia=v.competencia, valor=v.valor))
        else:
            m.valor = v.valor


@router.put("/{pid}/compras", status_code=204)
def gravar_compras(pid: int, valores: list[ValorCompetencia], db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid, alterar=True)
    _gravar_mensal(db, p, CompraMensal, valores)
    _alterou(db, p)


@router.put("/{pid}/devolucoes", status_code=204)
def gravar_devolucoes(pid: int, valores: list[ValorCompetencia], db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid, alterar=True)
    _gravar_mensal(db, p, DevolucaoMensal, valores)
    _alterou(db, p)


@router.put("/{pid}/folha", status_code=204)
def gravar_folha(pid: int, valores: list[FolhaCompetencia], db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid, alterar=True)
    for v in valores:
        _competencia_valida(p, v.competencia)
        f = db.scalar(select(FolhaMensal).where(FolhaMensal.planejamento_id == pid,
                                                FolhaMensal.competencia == v.competencia))
        if f is None:
            f = FolhaMensal(planejamento_id=pid, competencia=v.competencia)
            db.add(f)
        f.folha, f.pro_labore = v.folha, v.pro_labore
    _alterou(db, p)


def _movimento_atual(db: Session, pid: int) -> dict[str, dict]:
    atuais: dict[str, dict] = {}
    for modelo, campo in ((CompraMensal, "compras"), (DevolucaoMensal, "devolucoes")):
        for m in db.scalars(select(modelo).where(modelo.planejamento_id == pid)):
            atuais.setdefault(m.competencia, {})[campo] = m.valor
    for f in db.scalars(select(FolhaMensal).where(FolhaMensal.planejamento_id == pid)):
        atuais.setdefault(f.competencia, {}).update(folha=f.folha, pro_labore=f.pro_labore)
    return atuais


@router.get("/{pid}/planilha-mensal")
def baixar_planilha_mensal(pid: int, db: DB, _: UsuarioAtual):
    """Modelo .xlsx do movimento mensal, com as competências do planejamento e o que já foi informado."""
    p = obter_planejamento(db, pid)
    return Response(planilha_mensal.gerar_modelo(p.competencias(), _movimento_atual(db, pid)),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="movimento-mensal-{pid}.xlsx"'})


@router.post("/{pid}/planilha-mensal")
def importar_planilha_mensal(pid: int, arquivo: UploadFile, db: DB, u: UsuarioAtual):
    """Planilha padrão preenchida: grava compras, devoluções, folha e pró-labore; célula vazia não altera."""
    p = obter_planejamento(db, pid, alterar=True)
    _recusar_se_aprovado(db, p)
    if not (arquivo.filename or "").lower().endswith(".xlsx"):
        raise ErroNegocio("Envie a planilha padrão em .xlsx", 415)
    try:
        lidos = planilha_mensal.ler(ler_limitado(arquivo, get_settings().relatorio_contabil_max_mb))
    except planilha_mensal.PlanilhaInvalida as e:
        raise ErroNegocio(str(e), 422, {"arquivo": str(e)}) from e
    for c in lidos:
        _competencia_valida(p, c)
    for modelo, campo in ((CompraMensal, "compras"), (DevolucaoMensal, "devolucoes")):
        _gravar_mensal(db, p, modelo, [ValorCompetencia(competencia=c, valor=v[campo]) for c, v in lidos.items() if campo in v])
    for c, v in lidos.items():
        if not {"folha", "pro_labore"} & v.keys():
            continue
        f = db.scalar(select(FolhaMensal).where(FolhaMensal.planejamento_id == pid, FolhaMensal.competencia == c))
        if f is None:
            f = FolhaMensal(planejamento_id=pid, competencia=c)
            db.add(f)
        f.folha, f.pro_labore = v.get("folha", f.folha), v.get("pro_labore", f.pro_labore)
    _alterou(db, p)
    auditar("PLANILHA_MENSAL_IMPORTADA", usuario=u, planejamento=p, recurso_tipo="planejamento", recurso_id=pid,
            detalhes={"arquivo": arquivo.filename, "competencias": sorted(lidos)})
    return {"competencias": sorted(lidos), "valores": sum(len(v) for v in lidos.values())}


@router.delete("/{pid}/composicao-compras", status_code=204)
def apagar_composicao(pid: int, db: DB, _: UsuarioAtual):
    """Volta a origem das compras para o valor das notas (ou para pendente, sem notas de compra)."""
    p = obter_planejamento(db, pid, alterar=True)
    db.execute(delete(CompraOrigem).where(CompraOrigem.planejamento_id == pid))
    _alterou(db, p)


@router.put("/{pid}/composicao-compras", status_code=204)
def gravar_composicao(pid: int, origens: list[OrigemCompra], db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid, alterar=True)
    if abs(sum((o.percentual for o in origens), Decimal(0)) - 1) > Decimal("0.0001"):
        raise ErroNegocio("A composição das compras deve somar 100%", campos={"percentual": "soma ≠ 100%"})
    db.execute(delete(CompraOrigem).where(CompraOrigem.planejamento_id == pid))
    db.add_all(CompraOrigem(planejamento_id=pid, **o.model_dump()) for o in origens if o.percentual > 0)
    _alterou(db, p)


def _validar_premissa(chave: str, valor) -> str:
    """Devolve o valor em JSON, ou recusa o que quebraria a simulação."""
    if PREMISSAS[chave] is bool:
        if not isinstance(valor, bool):
            raise ErroNegocio("Valor inválido", campos={chave: "use verdadeiro ou falso"})
        return json.dumps(valor)
    try:
        numero = Decimal(str(valor))
    except InvalidOperation as e:
        raise ErroNegocio("Valor inválido", campos={chave: "precisa ser um número"}) from e
    if not numero.is_finite() or numero < 0:
        raise ErroNegocio("Valor inválido", campos={chave: "não pode ser negativo"})
    if chave == "pct_compras_credito_ibs_cbs" and numero > 1:
        raise ErroNegocio("Valor inválido", campos={chave: "precisa ficar entre 0% e 100%"})
    if chave == "rat" and numero not in (Decimal("0.01"), Decimal("0.02"), Decimal("0.03")):
        raise ErroNegocio("Valor inválido", campos={chave: "o RAT é 1%, 2% ou 3%"})
    if chave == "fap" and not Decimal("0.5") <= numero <= Decimal("2"):
        raise ErroNegocio("Valor inválido", campos={chave: "o FAP vai de 0,5000 a 2,0000"})
    if chave == "terceiros" and numero > Decimal("0.1"):
        raise ErroNegocio("Valor inválido", campos={chave: "terceiros acima de 10%: confira o FPAS"})
    return json.dumps(str(numero))


@router.put("/{pid}/premissas", status_code=204)
def gravar_premissas(pid: int, premissas: dict, db: DB, u: Contador):
    """Valor vazio apaga a premissa, e o planejamento volta ao padrão."""
    p = obter_planejamento(db, pid, alterar=True)
    invalidas = set(premissas) - set(PREMISSAS)
    if invalidas:
        raise ErroNegocio("Premissas desconhecidas", campos={k: "não existe" for k in invalidas})
    for chave, valor in premissas.items():
        pr = db.scalar(select(PremissaPlanejamento).where(PremissaPlanejamento.planejamento_id == pid,
                                                          PremissaPlanejamento.chave == chave))
        if valor is None or valor == "":
            if pr:
                db.delete(pr)
            continue
        texto = _validar_premissa(chave, valor)
        if pr is None:
            pr = PremissaPlanejamento(planejamento_id=pid, chave=chave, alterado_por=u.id)
            db.add(pr)
        pr.valor, pr.alterado_por, pr.alterado_em = texto, u.id, datetime.now(UTC)
    db.flush()
    estoque = set(db.scalars(select(PremissaPlanejamento.chave).where(
        PremissaPlanejamento.planejamento_id == pid, PremissaPlanejamento.chave.in_(("estoque_inicial", "estoque_final")))))
    if len(estoque) == 1:
        db.rollback()
        raise ErroNegocio("Informe o estoque inicial e o final, ou deixe os dois vazios",
                          campos={"estoque_inicial": "informe os dois", "estoque_final": "informe os dois"})
    _alterou(db, p)


@router.get("/{pid}/observacoes")
def ver_observacoes(pid: int, db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid)
    quem = db.get(Usuario, p.observacoes_aceitas_por) if p.observacoes_aceitas_por else None
    return {"textos": OBSERVACOES, "aceitas_em": p.observacoes_aceitas_em, "aceitas_por": quem.nome if quem else None}


@router.post("/{pid}/observacoes/aceite", status_code=204)
def aceitar_observacoes(pid: int, db: DB, u: UsuarioAtual):
    """O aceite não entra no cálculo: atualiza o progresso sem desatualizar as simulações."""
    p = obter_planejamento(db, pid)
    p.observacoes_aceitas_por, p.observacoes_aceitas_em = u.id, datetime.now(UTC)
    db.flush()
    progresso.atualizar(db, p)
    db.commit()


# --------------------------------------------------- levantamento de despesas


@router.get("/{pid}/levantamentos/{competencia}")
def ver_levantamento(pid: int, competencia: str, db: DB, _: UsuarioAtual):
    p = obter_planejamento(db, pid)
    _competencia_valida(p, competencia)
    lv = db.scalar(select(Levantamento).where(Levantamento.planejamento_id == pid,
                                              Levantamento.competencia == competencia))
    if lv is None:
        return {"competencia": competencia, "status": None, "itens": {}, "grupos_sem_outras": [], "outras": []}
    return {
        "id": lv.id, "competencia": competencia, "status": lv.status,
        "itens": {i.item_despesa_id: i.valor for i in
                  db.scalars(select(LevantamentoItem).where(LevantamentoItem.levantamento_id == lv.id))},
        "grupos_sem_outras": [g.grupo_id for g in db.scalars(select(LevantamentoGrupo).where(
            LevantamentoGrupo.levantamento_id == lv.id, LevantamentoGrupo.possui_outras.is_(False)))],
        "outras": [{"grupo_id": o.grupo_id, "descricao": o.descricao, "valor": o.valor}
                   for o in db.scalars(select(OutraDespesa).where(OutraDespesa.levantamento_id == lv.id))],
    }


@router.put("/{pid}/levantamentos/{competencia}", status_code=204)
def gravar_levantamento(pid: int, competencia: str, dados: LevantamentoEntrada, db: DB, u: UsuarioAtual):
    """Salvamento parcial: só os itens enviados são alterados."""
    p = obter_planejamento(db, pid, alterar=True)
    _competencia_valida(p, competencia)
    lv = db.scalar(select(Levantamento).where(Levantamento.planejamento_id == pid,
                                              Levantamento.competencia == competencia))
    if lv is None:
        lv = Levantamento(planejamento_id=pid, competencia=competencia, criado_por=u.id)
        db.add(lv)
        db.flush()
    elif lv.status != "EM_PREENCHIMENTO":
        raise ErroNegocio("Levantamento enviado ou conferido não pode ser alterado", 409)
    for it in dados.itens:
        atual = db.scalar(select(LevantamentoItem).where(LevantamentoItem.levantamento_id == lv.id,
                                                         LevantamentoItem.item_despesa_id == it.item_despesa_id))
        if it.valor is None:
            if atual:
                db.delete(atual)
        elif atual:
            atual.valor = it.valor
        else:
            db.add(LevantamentoItem(levantamento_id=lv.id, item_despesa_id=it.item_despesa_id, valor=it.valor))
    if dados.outras is not None:
        db.execute(delete(OutraDespesa).where(OutraDespesa.levantamento_id == lv.id))
        db.add_all(OutraDespesa(levantamento_id=lv.id, **o.model_dump()) for o in dados.outras)
        db.execute(delete(LevantamentoGrupo).where(LevantamentoGrupo.levantamento_id == lv.id))
        com_outras = {o.grupo_id for o in dados.outras}
        db.add_all(LevantamentoGrupo(levantamento_id=lv.id, grupo_id=g, possui_outras=True) for g in com_outras)
        db.add_all(LevantamentoGrupo(levantamento_id=lv.id, grupo_id=g, possui_outras=False)
                   for g in set(dados.grupos_sem_outras) - com_outras)
    lv.alterado_em = datetime.now(UTC)
    _alterou(db, p)


# ------------------------------------------------------------------ NF-e


@router.post("/{pid}/nfe")
def importar_nfe(pid: int, arquivo: UploadFile, db: DB, u: UsuarioAtual):
    """XML de NF-e avulso ou .zip com vários XML. Notas já importadas (mesma chave) são ignoradas."""
    p = obter_planejamento(db, pid)
    _recusar_se_aprovado(db, p)
    nome = arquivo.filename or "arquivo"
    if not nome.lower().endswith((".xml", ".zip")):
        raise ErroNegocio("Envie um XML de NF-e ou um .zip com XMLs", 415)
    s = get_settings()
    limite = s.nfe_zip_max_mb if nome.lower().endswith(".zip") else s.nfe_xml_max_mb
    notas, erros, cancelados = ler_arquivos(nome, ler_limitado(arquivo, limite))
    cancelados = nfe_canceladas.lembrar(pid, cancelados)  # inclui as canceladas em envios anteriores
    imp = ImportacaoNfe(planejamento_id=pid, origem="XML", arquivo=nome, importado_por=u.id, lidos=len(notas),
                        importados=0, ignorados=0)
    db.add(imp)
    db.flush()
    comps = set(p.competencias())
    log = list(erros)
    # em lote: uma consulta para as chaves já importadas e uma inserção para todas as notas e itens novos
    existentes = _notas_existentes(db, pid, [n.chave_acesso for n in notas if n.competencia in comps])
    sem_st = _itens_sem_st(db, list(existentes.values()))
    vistas: dict[str, list] = {}  # chave -> itens da nota nova; a mesma nota pode vir repetida no .zip
    novas: list[tuple[dict, list]] = []
    # cancelada por evento (no mesmo envio ou depois): a nota nova é ignorada e a já importada sai do cálculo
    canceladas = list(_notas_existentes(db, pid, list(cancelados)).values()) if cancelados else []
    for nf in canceladas:
        log.append(f"NF {nf.numero}: cancelada; removida do planejamento")
    for n in notas:
        if n.chave_acesso in cancelados:
            imp.ignorados += 1
            log.append(f"NF {n.numero}: cancelada, ignorada")
            continue
        if n.competencia not in comps:
            imp.ignorados += 1
            log.append(f"NF {n.numero}: competência {n.competencia} fora do período")
            continue
        nota = existentes.get(n.chave_acesso)
        if nota is not None or n.chave_acesso in vistas:
            imp.ignorados += 1
            completados = 0
            # notas importadas antes de o sistema ler o ICMS-ST (ou repetidas no .zip sem a ST): esta cópia completa a base
            com_st = {i.n_item: i for i in n.itens if i.bc_st}
            if nota is None:
                for item in vistas[n.chave_acesso]:
                    if item.n_item in com_st and item.bc_st is None:
                        item.bc_st, item.vl_icms_st = com_st[item.n_item].bc_st, com_st[item.n_item].vl_icms_st
                        completados += 1
            else:
                for item in sem_st.get(nota.id, []):
                    if item.n_item in com_st and item.bc_st is None:
                        item.bc_st, item.vl_icms_st = com_st[item.n_item].bc_st, com_st[item.n_item].vl_icms_st
                        completados += 1
                if nota.dest_contribuinte is None and n.dest_contribuinte is not None:
                    nota.dest_contribuinte = n.dest_contribuinte  # notas de antes da leitura do indIEDest (DIFAL)
            log.append(f"NF {n.numero}: já importada" + (f"; base do ICMS-ST completada em {completados} item(ns)" if completados else ""))
            continue
        if n.cnpj_emitente == p.empresa.cnpj:
            # nota própria: venda (tpNF 1) ou entrada emitida pela empresa, como a devolução de venda (CFOP 1202)
            tipo = "SAIDA" if n.tipo_nf == 1 else "ENTRADA"
        elif n.cnpj_destinatario == p.empresa.cnpj:
            tipo = "ENTRADA"
            for i in n.itens:  # nota do fornecedor: o CFOP passa a ser o da entrada (5102 -> 1102)
                i.cfop = relatorio_contabil.cfop_de_entrada(i.cfop)
        else:
            imp.ignorados += 1
            log.append(f"NF {n.numero}: empresa não é emitente nem destinatária")
            continue
        vistas[n.chave_acesso] = n.itens
        novas.append((dict(planejamento_id=pid, importacao_id=imp.id, chave_acesso=n.chave_acesso, numero=n.numero,
                           data_emissao=n.data_emissao, competencia=n.competencia, tipo=tipo,
                           uf_emitente=n.uf_emitente, uf_destinatario=n.uf_destinatario,
                           crt_emitente=n.crt_emitente, consumidor_final=n.consumidor_final,
                           dest_contribuinte=n.dest_contribuinte), n.itens))
        imp.importados += 1
    # notas de fornecedor de importações antigas: o CFOP passa para o lado da entrada e o mês é recalculado
    antigas = relatorio_contabil.entradas_com_cfop_do_fornecedor(db, pid)
    comps_entrada = ({nf["competencia"] for nf, _ in novas if nf["tipo"] == "ENTRADA"} | {c for _, c in antigas}
                     | {nf.competencia for nf in canceladas if nf.tipo == "ENTRADA"})
    antes = relatorio_contabil.somar_entradas(db, pid, comps_entrada) if comps_entrada else {}
    if canceladas:
        ids_canceladas = [nf.id for nf in canceladas]
        db.execute(delete(NotaItem).where(NotaItem.nota_fiscal_id.in_(ids_canceladas)))
        db.execute(delete(NotaFiscal).where(NotaFiscal.id.in_(ids_canceladas)))
    for item, _ in antigas:
        item.cfop = relatorio_contabil.cfop_de_entrada(item.cfop)
    if novas:
        # INSERT em lote sem RETURNING (no SQLite o ORM inseriria nota a nota para saber cada id);
        # os ids vêm depois numa consulta pelas chaves
        for k in range(0, len(novas), LOTE_ITENS):
            db.execute(insert(NotaFiscal), [nf for nf, _ in novas[k:k + LOTE_ITENS]])
        ids = {chave: nf.id for chave, nf in _notas_existentes(db, pid, [nf["chave_acesso"] for nf, _ in novas]).items()}
        itens = [{"nota_fiscal_id": ids[nf["chave_acesso"]], **vars(i)} for nf, lidos in novas for i in lidos]
        for k in range(0, len(itens), LOTE_ITENS):
            db.execute(insert(NotaItem), itens[k:k + LOTE_ITENS])
    avisos = []
    if comps_entrada:
        depois = relatorio_contabil.somar_entradas(db, pid, comps_entrada)
        # mês sem nota de entrada restante (a última foi cancelada) não aparece na soma: vale zero
        depois = {c: depois.get(c, (Decimal(0), Decimal(0))) for c in comps_entrada}
        avisos = relatorio_contabil.preencher_pelas_entradas(db, p, antes, depois)
    imp.status = "CONCLUIDA"
    imp.log = "\n".join(log + avisos) or None
    _alterou(db, p)
    auditar("NFE_IMPORTADA", usuario=u, planejamento=p, recurso_tipo="importacao_nfe", recurso_id=imp.id,
            detalhes={"arquivo": nome, "lidos": imp.lidos, "importados": imp.importados, "ignorados": imp.ignorados,
                      "erros": len(erros)})
    return {"id": imp.id, "lidos": imp.lidos, "importados": imp.importados, "ignorados": imp.ignorados, "log": log,
            "avisos": avisos}


LOTE_ITENS = 1000  # itens por INSERT na importação de NF-e
LOTE_CHAVES = 500  # chaves por IN na consulta das notas já importadas


def _notas_existentes(db: Session, pid: int, chaves: list[str]) -> dict[str, NotaFiscal]:
    out: dict[str, NotaFiscal] = {}
    unicas = list(dict.fromkeys(chaves))
    for k in range(0, len(unicas), LOTE_CHAVES):
        for nf in db.scalars(select(NotaFiscal).where(NotaFiscal.planejamento_id == pid,
                                                      NotaFiscal.chave_acesso.in_(unicas[k:k + LOTE_CHAVES]))):
            out[nf.chave_acesso] = nf
    return out


def _itens_sem_st(db: Session, notas: list[NotaFiscal]) -> dict[int, list[NotaItem]]:
    """Itens das notas já importadas que ainda não têm a base do ICMS-ST, por nota."""
    out: dict[int, list[NotaItem]] = {}
    ids = [nf.id for nf in notas]
    for k in range(0, len(ids), LOTE_CHAVES):
        for item in db.scalars(select(NotaItem).where(NotaItem.nota_fiscal_id.in_(ids[k:k + LOTE_CHAVES]),
                                                      NotaItem.bc_st.is_(None))):
            out.setdefault(item.nota_fiscal_id, []).append(item)
    return out


@router.post("/{pid}/relatorio-contabil")
def importar_relatorio_contabil(pid: int, arquivo: UploadFile, db: DB, u: UsuarioAtual):
    """Relatório "Movimentação de Produtos – ICMS – PIS – COFINS" do Domínio (.xls ou .xlsx), de saídas ou de entradas."""
    p = obter_planejamento(db, pid, alterar=True)
    _recusar_se_aprovado(db, p)
    nome = arquivo.filename or "relatorio.xls"
    if not nome.lower().endswith((".xls", ".xlsx")):
        raise ErroNegocio("Envie o relatório em .xls ou .xlsx", 415)
    conteudo = ler_limitado(arquivo, get_settings().relatorio_contabil_max_mb)
    try:
        resumo = relatorio_contabil.importar(db, p, nome, conteudo, u.id)
    except relatorio_contabil.RelatorioInvalido as e:
        db.rollback()
        raise ErroNegocio(str(e), 422, {"arquivo": str(e)}) from e
    _alterou(db, p)
    auditar("RELATORIO_CONTABIL_IMPORTADO", usuario=u, planejamento=p, recurso_tipo="relatorio_contabil",
            detalhes={"arquivo": nome, "tipo": resumo.tipo, "linhas": resumo.linhas,
                      "notas_importadas": resumo.notas_importadas, "notas_ignoradas": resumo.notas_ignoradas})
    return {
        "tipo": resumo.tipo, "empresa_relatorio": resumo.empresa_relatorio, "linhas": resumo.linhas,
        "notas_importadas": resumo.notas_importadas, "notas_ignoradas": resumo.notas_ignoradas,
        "valor_importado": resumo.valor_importado, "por_competencia": resumo.por_competencia, "avisos": resumo.avisos,
    }


# ------------------------------------------------------------------ revisão de produtos


class RevisaoEntrada(Esquema):
    cod_produto: str = Field(default="", max_length=60)
    ncm_nota: str = Field(pattern=r"^\d{8}$")
    ncm_corrigido: str | None = Field(default=None, pattern=r"^\d{8}$")
    monofasico: bool | None = None
    motivo: str = Field(min_length=5, max_length=500)


@router.get("/{pid}/revisao")
def ver_revisao(pid: int, db: DB, _: UsuarioAtual):
    produtos = revisao_produtos.analisar(db, obter_planejamento(db, pid))
    return {"resumo": revisao_produtos.resumo(produtos), "produtos": revisao_produtos.serializar(db, produtos)}


@router.get("/{pid}/revisao/exportar")
def exportar_revisao(pid: int, db: DB, u: UsuarioAtual):
    p = obter_planejamento(db, pid)
    texto = revisao_produtos.exportar_csv(revisao_produtos.analisar(db, p))
    auditar("REVISAO_EXPORTADA", usuario=u, planejamento=p, recurso_tipo="planejamento", recurso_id=pid)
    return Response("\ufeff" + texto, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="REVISAO_{p.empresa.cnpj}.csv"'})


@router.put("/{pid}/revisao", status_code=204)
def revisar_produto(pid: int, dados: RevisaoEntrada, db: DB, u: Contador):
    p = obter_planejamento(db, pid, alterar=True)
    produtos = revisao_produtos.analisar(db, p)
    if not any(x.cod_produto == dados.cod_produto and x.ncm_nota == dados.ncm_nota for x in produtos):
        raise NaoEncontrado("Produto")
    ncm = dados.ncm_corrigido or dados.ncm_nota
    condicional = avaliar(ncm, tabelas.lei_monofasico()).enquadramento == Enquadramento.CONDICIONAL
    if condicional and dados.monofasico is None:
        raise ErroNegocio("Este NCM depende de Ex ou destinação: informe se o produto é monofásico",
                          campos={"monofasico": "obrigatório"})
    r = db.scalar(select(RevisaoProduto).where(RevisaoProduto.planejamento_id == pid, RevisaoProduto.cod_produto == dados.cod_produto,
                                               RevisaoProduto.ncm_nota == dados.ncm_nota))
    if r is None:
        r = RevisaoProduto(planejamento_id=pid, cod_produto=dados.cod_produto, ncm_nota=dados.ncm_nota, revisado_por=u.id)
        db.add(r)
    # fora dos condicionais quem decide é a lei: a revisão não pode contrariá-la
    r.ncm_corrigido = dados.ncm_corrigido if dados.ncm_corrigido != dados.ncm_nota else None
    r.monofasico = dados.monofasico if condicional else None
    r.motivo, r.revisado_por, r.revisado_em = dados.motivo.strip(), u.id, datetime.now(UTC)
    _revisao_da_empresa_mudou(db, p)
    _alterou(db, p)


def _revisao_da_empresa_mudou(db: Session, p: Planejamento) -> None:
    """A revisão vale para os outros planejamentos da empresa (os que não têm decisão própria sobre o produto)."""
    db.flush()
    for outro in db.scalars(select(Planejamento).where(Planejamento.empresa_id == p.empresa_id, Planejamento.id != p.id,
                                                       Planejamento.status != "APROVADO")):
        progresso.atualizar(db, outro)
        marcar_desatualizada(db, outro.id)


@router.delete("/{pid}/revisao/{revisao_id}", status_code=204)
def desfazer_revisao(pid: int, revisao_id: int, db: DB, _: Contador):
    p = obter_planejamento(db, pid, alterar=True)
    r = db.get(RevisaoProduto, revisao_id)
    if r is None or r.planejamento_id != pid:
        raise NaoEncontrado("Revisão")
    db.delete(r)
    _revisao_da_empresa_mudou(db, p)
    _alterou(db, p)


# ------------------------------------------------------------------ estoque que saiu da ST


class EstoqueStEntrada(Esquema):
    valor: Decimal | None = Field(default=None, ge=0, description="Custo do estoque das mercadorias excluídas na véspera da exclusão")


def _estoque_st(db: Session, p: Planejamento) -> dict | None:
    return retencao.ler(db, p, "estoque_st")


@router.get("/{pid}/estoque-st")
def ver_estoque_st(pid: int, db: DB, _: UsuarioAtual):
    """Crédito estimado do ICMS-ST do estoque das mercadorias que saíram da ST (null se nenhuma saiu)."""
    return _estoque_st(db, obter_planejamento(db, pid))


@router.put("/{pid}/estoque-st")
def gravar_estoque_st(pid: int, dados: EstoqueStEntrada, db: DB, u: UsuarioAtual):
    p = obter_planejamento(db, pid, alterar=True)
    pr = db.scalar(select(PremissaPlanejamento).where(PremissaPlanejamento.planejamento_id == pid,
                                                      PremissaPlanejamento.chave == estoque_st.CHAVE))
    if dados.valor is None:
        if pr:
            db.delete(pr)
    else:
        if pr is None:
            pr = PremissaPlanejamento(planejamento_id=pid, chave=estoque_st.CHAVE, alterado_por=u.id)
            db.add(pr)
        pr.valor, pr.alterado_por, pr.alterado_em = json.dumps(str(dados.valor)), u.id, datetime.now(UTC)
    _alterou(db, p)
    return _estoque_st(db, p)
