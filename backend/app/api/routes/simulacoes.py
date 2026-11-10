"""Execução do motor, resultados, memória de cálculo, oportunidades e exportação."""
import hashlib
import json
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select

from app.api.deps import DB, Contador, UsuarioAtual, obter_planejamento
from app.core.erros import ErroNegocio, NaoEncontrado
from app.models import OportunidadeRegistro, Planejamento, RelatorioPdf, Simulacao, Usuario
from app.motor import engine
from app.schemas.comum import Esquema
from app.services import apresentacao_pptx, cripto, exportacao_excel, memoria_calculo, relatorio_pdf
from app.services import simulacao as servico
from app.services.auditoria import auditar
from app.services.entrada import montar_entrada
from app.services.serializacao import para_json
from app.utils.download import anexo

router = APIRouter(tags=["Simulações"])


class SimulacaoResumo(Esquema):
    id: int
    planejamento_id: int
    versao: int
    tipo: str
    regime_recomendado: str
    pendencias: str | None
    desatualizada: bool
    executada_em: object
    aprovada_em: object | None


class OportunidadeAtualizacao(Esquema):
    situacao: Literal["ABERTA", "CONFIRMADA", "DESCARTADA"]
    motivo: str | None = Field(default=None, max_length=500)


def _simulacao(db, sid: int) -> Simulacao:
    s = db.get(Simulacao, sid)
    if s is None:
        raise NaoEncontrado("Simulação")
    return s


@router.post("/planejamentos/{pid}/simulacoes", response_model=SimulacaoResumo, status_code=201)
def executar(pid: int, db: DB, u: UsuarioAtual):
    return servico.executar(db, obter_planejamento(db, pid), u.id)


@router.get("/planejamentos/{pid}/simulacoes", response_model=list[SimulacaoResumo])
def listar(pid: int, db: DB, _: UsuarioAtual):
    return db.scalars(select(Simulacao).where(Simulacao.planejamento_id == pid).order_by(Simulacao.versao.desc())).all()


@router.get("/simulacoes/{sid}")
def resultado(sid: int, db: DB, _: UsuarioAtual):
    """Resultado completo (sem a memória de cálculo, que tem rota própria)."""
    s = _simulacao(db, sid)
    r = json.loads(s.resultado_json)
    r.pop("memoria", None)
    ops = db.scalars(select(OportunidadeRegistro).where(OportunidadeRegistro.simulacao_id == sid)).all()
    r["oportunidades"] = [{"id": o.id, "codigo": o.codigo, "titulo": o.titulo, "impacto": o.impacto,
                           "prioridade": o.prioridade, "acao": o.acao, "situacao": o.situacao, "motivo": o.motivo}
                          for o in ops]
    return {"simulacao": SimulacaoResumo.model_validate(s), "resultado": r}


@router.get("/simulacoes/{sid}/memoria")
def memoria(sid: int, db: DB, _: UsuarioAtual, secao: str | None = None):
    passos = memoria_calculo.passos(db, _simulacao(db, sid))
    return [p for p in passos if secao is None or p["secao"] == secao]


@router.get("/simulacoes/{sid}/crescimento")
def crescimento(sid: int, db: DB, _: UsuarioAtual, rbt12: list[Decimal] = Query(default=[])):
    """Recalcula a simulação de crescimento para outros valores de RBT12."""
    s = _simulacao(db, sid)
    if not rbt12:
        return json.loads(s.resultado_json)["crescimento"]
    entrada = montar_entrada(db, db.get(Planejamento, s.planejamento_id)).entrada
    if not entrada.itens:  # notas apagadas na aprovação: sem elas o recálculo daria receita zero
        raise ErroNegocio("As notas fiscais deste planejamento foram apagadas na aprovação; "
                          "a simulação de crescimento mostra só os valores calculados")
    return para_json(engine.crescimento(entrada, sorted(rbt12)))


@router.post("/simulacoes/{sid}/aprovar", response_model=SimulacaoResumo)
def aprovar(sid: int, db: DB, u: Contador):
    return servico.aprovar(db, _simulacao(db, sid), u.id)


@router.patch("/oportunidades/{oid}")
def atualizar_oportunidade(oid: int, dados: OportunidadeAtualizacao, db: DB, _: Contador):
    o = db.get(OportunidadeRegistro, oid)
    if o is None:
        raise NaoEncontrado("Oportunidade")
    o.situacao, o.motivo = dados.situacao, dados.motivo
    db.commit()
    return {"id": o.id, "situacao": o.situacao, "motivo": o.motivo}


@router.get("/simulacoes/{sid}/excel")
def excel(sid: int, db: DB, u: Contador):
    s = _simulacao(db, sid)
    p = db.get(Planejamento, s.planejamento_id)
    nome = f"PLANEJAMENTO_{p.empresa.cnpj}_{p.competencia_inicial}_{p.competencia_final}_v{s.versao}.xlsx"
    conteudo = exportacao_excel.gerar(s, p)
    auditar("EXCEL_EXPORTADO", usuario=u, planejamento=p, recurso_tipo="simulacao", recurso_id=sid,
            detalhes={"arquivo": nome, "versao": s.versao})
    return Response(conteudo,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.get("/simulacoes/{sid}/apresentacao")
def apresentacao(sid: int, db: DB, u: Contador):
    """Apresentação do planejamento para o cliente, com gráficos editáveis no PowerPoint."""
    s = _simulacao(db, sid)
    p = db.get(Planejamento, s.planejamento_id)
    nome = f"APRESENTACAO_{p.empresa.cnpj}_{p.competencia_inicial}_{p.competencia_final}_v{s.versao}.pptx"
    conteudo = apresentacao_pptx.gerar(db, s, u)
    auditar("APRESENTACAO_EXPORTADA", usuario=u, planejamento=p, recurso_tipo="simulacao", recurso_id=sid,
            detalhes={"arquivo": nome, "versao": s.versao})
    return Response(conteudo,
                    media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


class RelatorioEntrada(Esquema):
    recomendacao: list[str] | None = Field(default=None, description="Itens da recomendação; vazio usa o texto-base")


class RelatorioSaida(Esquema):
    id: int
    planejamento_id: int
    simulacao_id: int
    arquivo: str
    hash_sha256: str
    preliminar: bool
    gerado_por: int
    gerado_em: object


@router.get("/simulacoes/{sid}/recomendacao")
def recomendacao(sid: int, db: DB, _: Contador):
    """Texto-base da recomendação, para o contador revisar antes de emitir o relatório."""
    s = _simulacao(db, sid)
    p = db.get(Planejamento, s.planejamento_id)
    return relatorio_pdf.recomendacao_padrao(json.loads(s.resultado_json), p.empresa.regime_tributario, len(p.competencias()))


@router.post("/simulacoes/{sid}/relatorio-pdf", response_model=RelatorioSaida, status_code=201)
def gerar_relatorio(sid: int, dados: RelatorioEntrada, db: DB, u: Contador):
    itens = [x.strip() for x in (dados.recomendacao or []) if x.strip()]
    rel = relatorio_pdf.gerar(db, _simulacao(db, sid), u, itens or None)
    auditar("RELATORIO_GERADO", usuario=u, planejamento=db.get(Planejamento, rel.planejamento_id),
            recurso_tipo="relatorio_pdf", recurso_id=rel.id,
            detalhes={"arquivo": rel.arquivo, "sha256": rel.hash_sha256, "preliminar": rel.preliminar})
    return rel


@router.get("/planejamentos/{pid}/relatorios")
def listar_relatorios(pid: int, db: DB, _: Contador):
    nomes = {x.id: x.nome for x in db.scalars(select(Usuario))}
    rels = db.scalars(select(RelatorioPdf).where(RelatorioPdf.planejamento_id == pid).order_by(RelatorioPdf.gerado_em.desc()))
    return [{**RelatorioSaida.model_validate(r).model_dump(), "gerado_por_nome": nomes.get(r.gerado_por)} for r in rels]


@router.get("/relatorios/{rid}/download")
def baixar_relatorio(rid: int, db: DB, u: Contador):
    """Os PDFs são somente leitura: o arquivo precisa conferir com o hash gravado na emissão."""
    rel = db.get(RelatorioPdf, rid)
    if rel is None:
        raise NaoEncontrado("Relatório")
    if not relatorio_pdf.caminho(rel).exists():
        raise ErroNegocio("Arquivo do relatório não encontrado no armazenamento", 410)
    try:
        conteudo = relatorio_pdf.ler(rel)
    except cripto.ErroCripto as e:
        raise ErroNegocio("O arquivo arquivado não confere (integridade da criptografia)", 409) from e
    if hashlib.sha256(conteudo).hexdigest() != rel.hash_sha256:
        raise ErroNegocio("O arquivo arquivado não confere com o hash registrado na emissão", 409)
    auditar("RELATORIO_BAIXADO", usuario=u, planejamento=db.get(Planejamento, rel.planejamento_id),
            recurso_tipo="relatorio_pdf", recurso_id=rel.id, detalhes={"arquivo": rel.arquivo})
    return anexo(conteudo, rel.arquivo, media_type="application/pdf")
