"""Calculadora do Simples Nacional por nota: DAS aproximado de cada nota (ou valor digitado), sem planejamento.

Cada linha usa o seu anexo e o mesmo RBT12 (o da empresa), como no PGDAS-D. Saem do DAS da linha: o ICMS quando a
mercadoria tem ST, o PIS e a COFINS quando é monofásica e o ISS quando sai do DAS: retido pelo tomador (art. 21,
§4º), em valor fixo (art. 18, §22-A) ou isento pelo município (art. 18, §20). Acima do sublimite o ISS é recolhido fora
do DAS, pela alíquota do município (art. 13-A).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from .simples import FATOR_R_MINIMO, AliquotaSimples, aliquota_efetiva, anexo_pelo_fator_r, fator_r, reparticao
from .tipos import ZERO, FaixaSimples, Parametros

CENTAVO = Decimal("0.01")


@dataclass(frozen=True)
class LinhaNota:
    descricao: str
    valor: Decimal
    anexo: str = "I"
    competencia: str | None = None  # AAAA-MM; agrupa a previsão do DAS do mês
    st: bool = False
    monofasico: bool = False
    iss_fora_do_das: str | None = None  # RETIDO, FIXO ou ISENTO
    fator_r: bool = False  # atividade do §5º-J: o anexo (III ou V) sai do Fator R


@dataclass
class ResultadoLinha:
    linha: LinhaNota
    anexo: str
    aliquota: Decimal  # alíquota efetiva da linha, já sem os tributos que saem do DAS
    das: Decimal
    tributos: dict[str, Decimal]
    iss_municipio: Decimal = ZERO  # acima do sublimite: ISS fora do DAS, pela alíquota do município


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
    iss_municipio: Decimal = ZERO
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
    if linha.iss_fora_do_das:
        fora.add("ISS")
    return fora


def calcular(
    linhas: list[LinhaNota],
    rbt12: Decimal,
    faixas: dict[str, list[FaixaSimples]],
    parametros: Parametros = Parametros(),
    folha_12m: Decimal | None = None,
    receita_12m: Decimal | None = None,
    aliq_iss_municipio: Decimal | None = None,
) -> ResultadoCalculadora:
    """faixas: tabela vigente de cada anexo. O Fator R usa a receita dos 12 meses informada ou, sem ela, o RBT12.
    aliq_iss_municipio: usada só com RBT12 acima do sublimite, para o ISS das notas de serviço fora do DAS."""
    if rbt12 < 0:
        raise ValueError("RBT12 negativo")
    fr = None
    if any(l.fator_r for l in linhas):
        if folha_12m is None:
            raise ValueError("Informe a folha dos 12 meses para calcular o Fator R")
        fr = fator_r(folha_12m, receita_12m if receita_12m is not None else rbt12)
    iss_por_fora = rbt12 > parametros.sublimite_simples
    sem_aliquota_iss = False

    aliquotas: dict[str, AliquotaSimples] = {}
    atividades: dict[tuple[str, bool], dict[str, Decimal]] = {}
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
        iss_municipio = ZERO
        if iss_por_fora and anexo in ("III", "IV", "V") and not l.iss_fora_do_das:
            if aliq_iss_municipio is None:
                sem_aliquota_iss = True
            else:
                iss_municipio = l.valor * aliq_iss_municipio
                resultado.iss_municipio += iss_municipio
        resultado.linhas.append(ResultadoLinha(l, anexo, sum(partes.values(), ZERO), das, tributos, iss_municipio))
        resultado.receita += l.valor
        # o PGDAS-D separa a receita por atividade (anexo, com ou sem ST/monofásico/ISS fora) e arredonda cada tributo nela
        atividade = atividades.setdefault((anexo, bool(fora)), {})
        for k, v in tributos.items():
            atividade[k] = atividade.get(k, ZERO) + v
        if l.competencia:
            resultado.por_competencia[l.competencia] = resultado.por_competencia.get(l.competencia, ZERO) + das

    for atividade in atividades.values():
        for k, v in atividade.items():
            resultado.tributos[k] = resultado.tributos.get(k, ZERO) + v.quantize(CENTAVO, ROUND_HALF_UP)
    resultado.das = sum(resultado.tributos.values(), ZERO)
    resultado.por_competencia = {m: v.quantize(CENTAVO, ROUND_HALF_UP) for m, v in resultado.por_competencia.items()}

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
    if sem_aliquota_iss:
        resultado.avisos.append("Informe a alíquota de ISS do município: acima do sublimite o ISS dos serviços é pago fora do DAS")
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
        avisos.append(f"Fator R de {r.fator_r * 100:.2f}%".replace(".", ",") + ": abaixo de 28%, a atividade vai para o Anexo V")
    return avisos
