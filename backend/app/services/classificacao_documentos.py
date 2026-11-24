"""Envio em lote na tela de Documentos: sugere o tipo e o mês de cada arquivo, sem gravar nada.

Os formatos que o sistema já lê (XML/ZIP de NF-e, extrato do PGDAS-D, relatório de movimentação da Domínio) são
reconhecidos pelo conteúdo. Os demais (planilhas e PDFs de banco, que variam de empresa para empresa) vão por
palavras-chave no nome e no começo do texto; o que não for reconhecido volta em branco para o usuário escolher.
"""
from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass, field

from pypdf import PdfReader

from app.services import nfe_xml, pgdas, relatorio_contabil
from app.utils.validacao import sem_acentos

# nomes dos tipos como estão no cadastro (seeds/carga.py)
FINANCEIRO = "Relatório financeiro de caixa ou planilha financeira"
EXTRATO = "Extrato bancário"
APLICACAO = "Extrato de aplicação financeira PJ"
INADIMPLENCIA = "Relatório de inadimplência (vencidos há mais de 6 meses)"
SAIDAS = "XML ou relatório de saídas"
ENTRADAS = "Relatório de entradas"
MARKETPLACE = "Relatório de tarifas do marketplace"
PGDAS = "Extrato do PGDAS-D (RBT12)"
INVENTARIO = "Inventário de estoque"

# ordem importa: o mais específico primeiro ("extrato de aplicação" antes de "extrato")
PALAVRAS = [
    (PGDAS, r"pgdas|simples nacional|rbt12"),
    (INADIMPLENCIA, r"inadimpl|vencid"),
    (INVENTARIO, r"inventario|estoque"),
    (MARKETPLACE, r"marketplace|mercado ?livre|shopee|amazon|magalu|tarifa"),
    (APLICACAO, r"aplicac|cdb|rendimento|investimento|fundo de"),
    (EXTRATO, r"extrato|saldo anterior|conta corrente"),
    (FINANCEIRO, r"fluxo de caixa|financeir|caixa|contas a (pagar|receber)"),
    (ENTRADAS, r"entrada|compra"),
    (SAIDAS, r"saida|venda|faturamento"),
]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DATA = re.compile(r"\b\d{1,2}/(\d{1,2})/(\d{4})\b")
MES_ANO = re.compile(r"(?<!\d)(\d{1,2})[-_./ ]?(20\d{2})(?!\d)|(?<!\d)(20\d{2})[-_./ ]?(\d{1,2})(?!\d)")
MES_NOME = re.compile(r"\b(" + "|".join(MESES) + r")[a-z]*[-_./ ]*(?:de )?(20\d{2})\b")


@dataclass
class Sugestao:
    arquivo: str
    tipo: str | None = None
    competencia: str | None = None
    motivo: str = "Não reconhecido: escolha o tipo e o mês"
    competencias_no_arquivo: list[str] = field(default_factory=list)


def _normal(texto: str) -> str:
    return sem_acentos(texto).lower()


def _meses_do_texto(texto: str) -> Counter:
    """Meses citados no texto (datas dd/mm/aaaa, mm/aaaa, nome do mês), contados."""
    t = _normal(texto)
    c: Counter = Counter()
    for m, a in DATA.findall(t):
        c[f"{a}-{int(m):02d}"] += 1
    for m1, a1, a2, m2 in MES_ANO.findall(t):
        m, a = (m1, a1) if m1 else (m2, a2)
        if 1 <= int(m) <= 12:
            c[f"{a}-{int(m):02d}"] += 1
    for nome, a in MES_NOME.findall(t):
        c[f"{a}-{MESES.index(nome) + 1:02d}"] += 1
    return c


def _escolher_mes(s: Sugestao, contagem: Counter, competencias: list[str]) -> None:
    """Mês mais citado dentro do período do planejamento; vários meses ficam listados para o aviso."""
    dentro = [(comp, n) for comp, n in contagem.most_common() if comp in competencias]
    if dentro:
        s.competencia = dentro[0][0]
        s.competencias_no_arquivo = sorted(comp for comp, _ in dentro)


def _texto_pdf(conteudo: bytes) -> str:
    try:
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(conteudo)).pages[:3])
    except Exception:  # noqa: BLE001 – PDF protegido, corrompido ou escaneado: fica sem texto
        return ""


def _texto_planilha(nome: str, conteudo: bytes) -> str:
    try:
        linhas, _ = relatorio_contabil._ler_celulas(nome, conteudo)
    except Exception:  # noqa: BLE001
        return ""
    return "\n".join(" ".join(str(c) for c in r if c not in (None, "")) for r in linhas[:40])


def _por_nfe(s: Sugestao, nome: str, conteudo: bytes, cnpj: str, competencias: list[str]) -> bool:
    try:
        notas, _, _ = nfe_xml.ler_arquivos(nome, conteudo)
    except Exception:  # noqa: BLE001 – ZIP inválido ou grande demais: segue para as palavras-chave
        return False
    if not notas:
        return False
    emitidas = sum(n.cnpj_emitente == cnpj for n in notas)
    s.tipo = SAIDAS if emitidas * 2 >= len(notas) else ENTRADAS
    _escolher_mes(s, Counter(n.competencia for n in notas), competencias)
    acao = "emitida" if s.tipo == SAIDAS else "recebida"
    s.motivo = f"{len(notas)} NF-e {acao}{'s' if len(notas) > 1 else ''} pela empresa"
    return True


def _por_relatorio_dominio(s: Sugestao, nome: str, conteudo: bytes, competencias: list[str]) -> bool:
    try:
        r = relatorio_contabil.ler_relatorio(nome, conteudo)
    except Exception:  # noqa: BLE001 – não é o relatório da Domínio
        return False
    s.tipo = SAIDAS if r.tipo == "SAIDA" else ENTRADAS
    meses = Counter(linha.competencia for linha in r.linhas)
    if not meses and r.periodo:
        meses[f"{r.periodo[1]:%Y-%m}"] += 1
    _escolher_mes(s, meses, competencias)
    s.motivo = f"Relatório de movimentação de {'saídas' if s.tipo == SAIDAS else 'entradas'} do sistema contábil"
    return True


def classificar(nome: str, conteudo: bytes, cnpj_empresa: str, competencias: list[str]) -> Sugestao:
    s = Sugestao(nome)
    ext = nome.lower().rsplit(".", 1)[-1]
    if ext in ("xml", "zip") and _por_nfe(s, nome, conteudo, cnpj_empresa, competencias):
        return s
    if ext in ("xls", "xlsx") and _por_relatorio_dominio(s, nome, conteudo, competencias):
        return s
    texto = ""
    if ext == "pdf":
        texto = _texto_pdf(conteudo)
        extrato = pgdas.ler(conteudo, nome) if texto else None
        if extrato and extrato.competencia and re.search(r"simples nacional|pgdas", _normal(texto)):
            s.tipo, s.motivo = PGDAS, f"Extrato do PGDAS-D, período de apuração {extrato.competencia[5:]}/{extrato.competencia[:4]}"
            _escolher_mes(s, Counter({extrato.competencia: 1}), competencias)
            return s
    elif ext in ("xls", "xlsx"):
        texto = _texto_planilha(nome, conteudo)
    elif ext in ("csv", "txt"):
        texto = conteudo[:20000].decode("utf-8", errors="ignore") or conteudo[:20000].decode("latin-1")

    # nome do arquivo pesa mais que o conteúdo: é o que a pessoa escolheu chamar
    for fonte, origem in ((_normal(nome), "nome do arquivo"), (_normal(texto[:5000]), "conteúdo")):
        tipo = next((t for t, padrao in PALAVRAS if re.search(padrao, fonte)), None)
        if tipo:
            s.tipo, s.motivo = tipo, f"Pelo {origem}: confira"
            break
    _escolher_mes(s, _meses_do_texto(nome), competencias)
    if s.competencia is None:
        _escolher_mes(s, _meses_do_texto(texto), competencias)
    if s.tipo is None and ext in ("pdf", "jpg", "jpeg", "png") and not texto:
        s.motivo = "Sem texto legível (imagem ou PDF escaneado): escolha o tipo e o mês"
    return s
