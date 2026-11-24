"""Envio em lote na tela de Documentos: sugere o tipo e o mês de cada arquivo, sem gravar nada.

Os formatos que o sistema já lê (XML/ZIP de NF-e e NFS-e, extrato do PGDAS-D, relatório de movimentação da Domínio) são
reconhecidos pelo conteúdo. Os demais (planilhas e PDFs de banco, que variam de empresa para empresa) vão por
palavras-chave no nome e no começo do texto; o que não for reconhecido volta em branco para o usuário escolher.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from pypdf import PdfReader

from app.core.config import get_settings
from app.services import nfe_xml, pgdas, relatorio_contabil
from app.services.nfse_xml import ServicoLido
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

# vence a palavra que aparece primeiro (o título do documento); no empate, a ordem da lista
# ("extrato de aplicação" casa com APLICACAO e EXTRATO na mesma posição)
PALAVRAS = [
    (PGDAS, r"pgdas|simples nacional|rbt12"),
    (INADIMPLENCIA, r"inadimpl|vencid"),
    (INVENTARIO, r"inventario|estoque"),
    # "tarifa" sozinha não: extrato de banco também cobra tarifa
    (MARKETPLACE, r"marketplace|mercado ?livre|shopee|amazon|magalu|tarifas? de (venda|envio|armazenagem|armazenamento)"),
    (APLICACAO, r"extrato (de )?(aplicac|investimento|cdb|fundo)|aplicac|cdb|rendimento|investimento|fundo de"),
    (EXTRATO, r"extrato|saldo anterior|conta corrente|banco"),
    (FINANCEIRO, r"fluxo de caixa|financeir|caixa|contas a (pagar|receber)|despesa"),
    (ENTRADAS, r"entrada|compra"),
    (SAIDAS, r"saida|venda|faturamento"),
]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DATA = re.compile(r"\b\d{1,2}/(\d{1,2})/(\d{4})\b")
# só meses 1–12: "00:00:00 2026-08" não pode virar "mês 00 de 2026" e engolir o ano de agosto
MES = r"(0?[1-9]|1[0-2])"
MES_ANO = re.compile(rf"(?<!\d){MES}[-_./ ]?(20\d{{2}})(?!\d)|(?<!\d)(20\d{{2}})[-_./ ]?{MES}(?!\d)")
MES_NOME = re.compile(r"\b(" + "|".join(MESES) + r")[a-z]*[-_./ ]*(?:de )?(20\d{2})\b")


@dataclass
class Sugestao:
    arquivo: str
    tipo: str | None = None
    competencia: str | None = None
    motivo: str = "Não reconhecido: escolha o tipo e o mês"
    competencias_no_arquivo: list[str] = field(default_factory=list)
    # planilha de despesas: documentos que o cliente responde dentro dela (ver COBERTOS_PELA_PLANILHA)
    cobre: list[str] = field(default_factory=list)


# Quem manda a planilha de despesas não manda esses documentos: as informações vêm nela, por descrição
# (tarifas bancárias, ADS do marketplace…), e a seção "Documentos a serem disponibilizados" é respondida
# ali mesmo. A própria planilha também vale para os outros meses que ela cobre.
COBERTOS_PELA_PLANILHA = [FINANCEIRO, EXTRATO, APLICACAO, INADIMPLENCIA, MARKETPLACE, INVENTARIO]


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
    """Começo de cada aba: a planilha de despesas tem uma aba por período, e a do ano atual não é a primeira."""
    try:
        if nome.lower().endswith(".xlsx"):
            from openpyxl import load_workbook

            livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
            abas = [list(aba.iter_rows(max_row=40, values_only=True)) for aba in livro.worksheets[:24]]
        else:
            abas = [relatorio_contabil._ler_celulas(nome, conteudo)[0][:40]]
    except Exception:  # noqa: BLE001
        return ""
    # data sem o horário: "2026-07-01 00:00:00 2026-08-01" leria "00 2026" como mês e perderia agosto
    cel = lambda c: f"{c:%d/%m/%Y}" if isinstance(c, date) else str(c)
    return "\n".join(" ".join(cel(c) for c in r if c not in (None, "")) for linhas in abas for r in linhas)


POR_PASTA = 50  # XMLs lidos de cada .zip (o de fora e cada um de dentro): basta uma amostra para classificar
MAX_AMOSTRA = 500
ZIP_INTERNO_MAX_MB = 64  # .zip dentro de .zip: o portal junta milhares de XML num só, maior que o upload


def _amostra_zip(conteudo: bytes, notas: list, orcamento: list[int], nivel: int = 0) -> None:
    """Lê uma amostra de NF-e do .zip, descendo em .zip dentro de .zip (até 2 níveis), como exporta o portal.
    `orcamento` é o que ainda pode ser descompactado, compartilhado entre os níveis (proteção contra zip bomb)."""
    cfg = get_settings()
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        xmls = [i for i in infos if i.filename.lower().endswith(".xml")][:POR_PASTA]
        internos = [i for i in infos if i.filename.lower().endswith(".zip")] if nivel < 2 else []
        for info, limite in [(i, cfg.nfe_xml_max_mb * nfe_xml.MB) for i in xmls] + \
                            [(i, ZIP_INTERNO_MAX_MB * nfe_xml.MB) for i in internos]:
            if len(notas) >= MAX_AMOSTRA:
                return
            dados = nfe_xml._ler_entrada(z, info, min(limite, orcamento[0]))
            if dados is None:
                continue
            orcamento[0] -= len(dados)
            if info.filename.lower().endswith(".zip"):
                try:
                    _amostra_zip(dados, notas, orcamento, nivel + 1)
                except zipfile.BadZipFile:
                    continue
            else:
                nfe_xml._ler(info.filename, dados, notas, set(), [])


def _por_nfe(s: Sugestao, nome: str, conteudo: bytes, cnpj: str, competencias: list[str]) -> bool:
    notas: list = []
    try:
        if nome.lower().endswith(".zip"):
            _amostra_zip(conteudo, notas, [get_settings().nfe_zip_descompactado_max_mb * nfe_xml.MB])
        else:
            notas, _, _ = nfe_xml.ler_arquivos(nome, conteudo)
    except Exception:  # noqa: BLE001 – ZIP inválido: segue para as palavras-chave
        return False
    if not notas:
        return False
    # NFS-e prestada pela empresa é documento de saída, como a NF-e emitida; a tomada, de entrada (não há tipo próprio)
    nfse = sum(isinstance(n, ServicoLido) for n in notas)
    emitidas = sum((n.cnpj_prestador if isinstance(n, ServicoLido) else n.cnpj_emitente) == cnpj for n in notas)
    s.tipo = SAIDAS if emitidas * 2 >= len(notas) else ENTRADAS
    _escolher_mes(s, Counter(n.competencia for n in notas), competencias)
    acao = "emitida" if s.tipo == SAIDAS else "recebida"
    tipos = " e ".join(t for t in (f"{len(notas) - nfse} NF-e" if nfse < len(notas) else "", f"{nfse} NFS-e" if nfse else "") if t)
    s.motivo = f"{tipos} {acao}{'s' if len(notas) > 1 else ''} pela empresa"
    if emitidas and emitidas != len(notas):
        s.motivo += f" ({emitidas} emitidas e {len(notas) - emitidas} recebidas)"
    if nome.lower().endswith(".zip"):
        s.motivo += " — amostra do .zip" if len(notas) >= POR_PASTA else ""
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
        achados = [(m.start(), i, t) for i, (t, padrao) in enumerate(PALAVRAS) if (m := re.search(padrao, fonte))]
        if achados:
            tipo = min(achados)[2]
            s.tipo, s.motivo = tipo, f"Pelo {origem}: confira"
            break
    _escolher_mes(s, _meses_do_texto(nome), competencias)
    if s.competencia is None:
        _escolher_mes(s, _meses_do_texto(texto), competencias)
    if s.tipo == FINANCEIRO and "despesa" in _normal(nome + " " + texto[:5000]):
        s.cobre = COBERTOS_PELA_PLANILHA
        s.motivo = "Planilha de despesas: confira"
    if s.tipo is None and ext in ("pdf", "jpg", "jpeg", "png") and not texto:
        s.motivo = "Sem texto legível (imagem ou PDF escaneado): escolha o tipo e o mês"
    return s
