"""Base da operação: receita bruta, devoluções rateadas e receita líquida por item."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .tipos import ZERO, Ambito, EntradaSimulacao, ItemSaida, Memoria


@dataclass(frozen=True)
class ItemCalculado:
    item: ItemSaida
    receita_liquida: Decimal
    st_interna: bool

    @property
    def tributado_pis_cofins(self) -> bool:
        """CST 01: gera receita e não é monofásico."""
        return self.item.gera_receita and not self.item.monofasico


@dataclass
class BaseCompetencia:
    competencia: str
    receita_bruta: Decimal = ZERO
    devolucoes: Decimal = ZERO
    receita_liquida: Decimal = ZERO
    receita_monofasica: Decimal = ZERO
    receita_interna: Decimal = ZERO
    receita_interestadual: Decimal = ZERO
    remessas_sem_receita: Decimal = ZERO
    compras: Decimal = ZERO
    despesas: Decimal = ZERO
    receita_servico: Decimal = ZERO  # prestação de serviços (NFS-e); já incluída na receita bruta e na líquida

    @property
    def receita_mercadoria(self) -> Decimal:
        return self.receita_liquida - self.receita_servico

    @property
    def receita_nao_monofasica(self) -> Decimal:
        return self.receita_liquida - self.receita_monofasica

    @property
    def participacao_nao_monofasica(self) -> Decimal:
        """Parte das vendas de mercadoria fora do monofásico: dá o crédito das compras no Lucro Real (o serviço não entra)."""
        if self.receita_mercadoria == 0:
            return ZERO
        return (self.receita_mercadoria - self.receita_monofasica) / self.receita_mercadoria


def dividir(a: Decimal, b: Decimal) -> Decimal:
    return ZERO if b == 0 else a / b


def calcular_base(
    entrada: EntradaSimulacao, memoria: Memoria
) -> tuple[dict[str, BaseCompetencia], list[ItemCalculado]]:
    bases = {c: BaseCompetencia(c) for c in entrada.competencias}
    for it in entrada.itens:
        if it.competencia not in bases:
            raise ValueError(f"Item com competência {it.competencia} fora do período do planejamento")
        if it.gera_receita:
            bases[it.competencia].receita_bruta += it.valor
        else:
            bases[it.competencia].remessas_sem_receita += it.valor

    fator_devolucao: dict[str, Decimal] = {}
    for c, b in bases.items():
        b.devolucoes = entrada.devolucoes.get(c, ZERO)
        fator_devolucao[c] = dividir(b.devolucoes, b.receita_bruta)
        b.compras = entrada.compras.get(c, ZERO)
        b.despesas = sum((d.valor for d in entrada.despesas if d.competencia == c), ZERO)

    itens: list[ItemCalculado] = []
    st_ativa = entrada.premissas.aplicar_st_vendas_internas
    for it in entrada.itens:
        rl = it.valor * (1 - fator_devolucao[it.competencia]) if it.gera_receita else ZERO
        st_interna = st_ativa and it.sujeito_st and it.ambito == Ambito.INTERNA and it.gera_receita
        itens.append(ItemCalculado(it, rl, st_interna))
        b = bases[it.competencia]
        b.receita_liquida += rl
        if it.gera_receita and it.monofasico:
            b.receita_monofasica += rl
        if it.ambito == Ambito.INTERNA:
            b.receita_interna += rl
        else:
            b.receita_interestadual += rl

    # serviço entra depois do rateio das devoluções, que são de vendas de mercadoria
    for c, b in bases.items():
        b.receita_servico = entrada.servicos.get(c, ZERO)
        b.receita_bruta += b.receita_servico
        b.receita_liquida += b.receita_servico

    for c, b in bases.items():
        if b.receita_servico:
            memoria.registrar("Base", "Receita de serviços", "informada (NFS-e)", b.receita_servico, c)
        memoria.registrar("Base", "Faturamento bruto", "Σ itens com CFOP que gera receita + serviços", b.receita_bruta, c)
        memoria.registrar("Base", "(−) Devoluções de vendas", "informado; rateado proporcionalmente nos itens", b.devolucoes, c,
                          "Lei 9.249/1995, art. 15; Lei 9.718/1998, art. 3º")
        memoria.registrar("Base", "(=) Receita líquida", "Σ valor × (1 − devoluções ÷ faturamento bruto)", b.receita_liquida, c)
        memoria.registrar("Base", "Receita de produtos monofásicos", "Σ receita líquida dos NCMs monofásicos", b.receita_monofasica, c,
                          "Lei 10.485/2002, Anexos I e II")
    return bases, itens
