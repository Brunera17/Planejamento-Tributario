"""Calculadora do Simples Nacional por nota: DAS aproximado de cada nota (ou valor digitado), sem planejamento.

Cada linha usa o seu anexo e o mesmo RBT12 (o da empresa), como no PGDAS-D. Saem do DAS da linha: o ICMS quando a
mercadoria tem ST, o PIS e a COFINS quando é monofásica e o ISS quando o tomador o reteve (LC 123/2006, art. 18,
§4º-A, e art. 21, §4º).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .simples import FATOR_R_MINIMO, AliquotaSimples, aliquota_efetiva, anexo_pelo_fator_r, fator_r, reparticao
from .tipos import ZERO, FaixaSimples, Parametros


@dataclass(frozen=True)
class LinhaNota:
    descricao: str
    valor: Decimal
    anexo: str = "I"
    competencia: str | None = None  # AAAA-MM; agrupa a previsão do DAS do mês
    st: bool = False
    monofasico: bool = False
    iss_retido: bool = False
    fator_r: bool = False  # atividade do §5º-J: o anexo (III ou V) sai do Fator R


@dataclass
class ResultadoLinha:
    linha: LinhaNota
    anexo: str
    aliquota: Decimal  # alíquota efetiva da linha, já sem os tributos que saem do DAS
    das: Decimal
    tributos: dict[str, Decimal]


@dataclass
class ResultadoCalculadora:
    rbt12: Decimal
    linhas: list[ResultadoLinha]
    das: Decimal
    receita: Decimal
    tributos: dict[str, Decimal]
    por_competencia: dict[str, Decimal]
    faixas: dict[str, dict[str, Decimal]]  # por anexo usado: faixa, alíquota nominal, efetiva, quanto falta para a próxima
    fator_r: Decimal | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def aliquota_media(self) -> Decimal:
        return ZERO if self.receita == 0 else self.das / self.receita


def _fora_do_das(linha: LinhaNota) -> set[str]:
    fora = set()
    if linha.st:
        fora.add("ICMS")
    if linha.monofasico:
        fora |= {"PIS", "COFINS"}
    if linha.iss_retido:
        fora.add("ISS")
    return fora


def calcular(
    linhas: list[LinhaNota],
    rbt12: Decimal,
    faixas: dict[str, list[FaixaSimples]],
    parametros: Parametros = Parametros(),
    folha_12m: Decimal | None = None,
    receita_12m: Decimal | None = None,
) -> ResultadoCalculadora:
    """faixas: tabela vigente de cada anexo. O Fator R usa a receita dos 12 meses informada ou, sem ela, o RBT12."""
    if rbt12 < 0:
        raise ValueError("RBT12 negativo")
    fr = None
    if any(l.fator_r for l in linhas):
        if folha_12m is None:
            raise ValueError("Informe a folha dos 12 meses para calcular o Fator R")
        fr = fator_r(folha_12m, receita_12m if receita_12m is not None else rbt12)

    aliquotas: dict[str, AliquotaSimples] = {}
    resultado = ResultadoCalculadora(rbt12, [], ZERO, ZERO, {}, {}, {}, fr)
    for l in linhas:
        anexo = anexo_pelo_fator_r(fr) if l.fator_r else l.anexo
        if anexo not in faixas:
            raise ValueError(f"Tabela do Anexo {anexo} não cadastrada")
        if anexo not in aliquotas:
            aliquotas[anexo] = aliquota_efetiva(rbt12, faixas[anexo])
        fora = _fora_do_das(l)
        partes = {k: v for k, v in reparticao(aliquotas[anexo]).items() if k not in fora}
        tributos = {k: l.valor * v for k, v in partes.items()}
        das = sum(tributos.values(), ZERO)
        resultado.linhas.append(ResultadoLinha(l, anexo, sum(partes.values(), ZERO), das, tributos))
        resultado.das += das
        resultado.receita += l.valor
        for k, v in tributos.items():
            resultado.tributos[k] = resultado.tributos.get(k, ZERO) + v
        if l.competencia:
            resultado.por_competencia[l.competencia] = resultado.por_competencia.get(l.competencia, ZERO) + das

    for anexo, a in aliquotas.items():
        f = a.faixa
        ultima = f.faixa == max(x.faixa for x in faixas[anexo])
        resultado.faixas[anexo] = {
            "faixa": Decimal(f.faixa),
            "aliquota_nominal": f.aliq_nominal,
            "parcela_deduzir": f.parcela_deduzir,
            "aliquota_efetiva": a.efetiva,
            "falta_proxima_faixa": ZERO if ultima else max(f.rbt12_ate - rbt12, ZERO),
        }
    resultado.avisos = _avisos(resultado, parametros)
    return resultado


def _avisos(r: ResultadoCalculadora, p: Parametros) -> list[str]:
    """RBT12 do próximo mês ≈ RBT12 atual + receita destas notas (sem descontar o mês que sai da janela)."""
    avisos = []
    depois = r.rbt12 + r.receita
    if r.rbt12 > p.teto_simples:
        avisos.append("RBT12 acima do teto de R$ 4,8 milhões: a empresa está sujeita à exclusão do Simples")
    elif depois > p.teto_simples:
        avisos.append("Com estas notas a receita dos 12 meses passa do teto de R$ 4,8 milhões")
    if r.rbt12 > p.sublimite_simples:
        avisos.append("RBT12 acima do sublimite de R$ 3,6 milhões: ICMS e ISS são recolhidos fora do DAS")
    elif depois > p.sublimite_simples:
        avisos.append("Com estas notas a receita dos 12 meses passa do sublimite de R$ 3,6 milhões: ICMS e ISS sairão do DAS")
    elif r.rbt12 > p.sublimite_simples * p.alerta_sublimite:
        avisos.append(f"RBT12 já passou de {p.alerta_sublimite:.0%} do sublimite de R$ 3,6 milhões")
    for anexo, f in r.faixas.items():
        if 0 < f["falta_proxima_faixa"] <= r.receita:
            avisos.append(f"Anexo {anexo}: estas notas levam o RBT12 à faixa {int(f['faixa']) + 1} no próximo mês")
    if r.fator_r is not None and r.fator_r < FATOR_R_MINIMO:
        avisos.append(f"Fator R de {r.fator_r:.2%}: abaixo de 28%, a atividade vai para o Anexo V")
    return avisos
