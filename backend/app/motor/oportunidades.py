"""Regras de oportunidade de economia/recuperação e pontos críticos da simulação."""
from __future__ import annotations

from decimal import Decimal

from .base import BaseCompetencia, ItemCalculado
from .icms import ResultadoIcms
from .presumido import inss_patronal
from .real import PisCofinsNaoCumulativo
from .simples import AliquotaSimples
from .tipos import ZERO, Ambito, EntradaSimulacao, Oportunidade, PontoCritico, Regime, ResultadoRegime


def _pct(v: Decimal, casas: int = 1) -> str:
    return f"{v * 100:.{casas}f}%".replace(".", ",")


def _brl(v: Decimal) -> str:
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _lista_despesas(nomes: list[str], limite: int = 8) -> str:
    if len(nomes) <= limite:
        return "Não constam do levantamento: " + "; ".join(nomes) + "."
    return (f"{len(nomes)} itens do catálogo não constam do levantamento, entre eles: " + "; ".join(nomes[:limite]) +
            ". A lista completa está nas pendências do planejamento.")


def avaliar_oportunidades(
    entrada: EntradaSimulacao,
    bases: dict[str, BaseCompetencia],
    itens: list[ItemCalculado],
    icms: ResultadoIcms,
    aliq: AliquotaSimples,
    simples: ResultadoRegime,
    pc_lr: PisCofinsNaoCumulativo,
) -> list[Oportunidade]:
    p, pr, f = entrada.parametros, entrada.premissas, aliq.faixa
    no_simples = pr.regime_atual == Regime.SIMPLES_NACIONAL
    aliq_pc_nc = p.pis_nao_cumulativo + p.cofins_nao_cumulativo
    receita = sum((b.receita_liquida for b in bases.values()), ZERO)
    ops: list[Oportunidade] = []

    if no_simples:
        cpp = next(t.valor for t in simples.tributos if t.tributo == "CPP")
        ops.append(Oportunidade(
            "CPP_DAS", "CPP (INSS patronal) embutida no DAS", cpp - inss_patronal(entrada), "ALTA",
            f"No Anexo I, {_pct(f.p_cpp, 0)} do DAS é CPP, paga sobre o faturamento, haja ou não empregados. "
            "No LP/LR o INSS patronal incide só sobre folha e pró-labore. Valor = CPP do DAS − INSS estimado sobre a folha."))

        mono = sum((b.receita_monofasica for b in bases.values()), ZERO)
        if mono > 0:
            ops.append(Oportunidade(
                "SEGREGACAO_MONOFASICO", "Segregação dos monofásicos no PGDAS-D (recuperação)",
                mono * aliq.parcela(f.p_pis + f.p_cofins), "ALTA",
                "Se as NF-e saem com CST 99 e a receita monofásica não é segregada, o PIS/COFINS é pago em duplicidade no DAS. "
                "Retificar o PGDAS-D dos últimos 5 anos, restituir/compensar e parametrizar o ERP (CST 04)."))

        st = sum((i.receita_liquida for i in itens if i.item.sujeito_st and i.item.ambito == Ambito.INTERNA), ZERO)
        if st > 0:
            ops.append(Oportunidade(
                "ICMS_ST_INTERNAS", "ICMS-ST nas vendas internas (recuperação)", st * aliq.parcela(f.p_icms), "ALTA",
                "Itens sujeitos à ST com CSOSN 102: a receita deveria ser segregada como ST no PGDAS-D, sem a parcela do ICMS. "
                "Confirmar a retenção nas NF-e de entrada (vICMSSTRet) e retificar."))

        suspeitos = sum((i.receita_liquida for i in itens if i.item.ncm in entrada.ncms_indicio_incorreto), ZERO)
        if suspeitos > 0:
            ops.append(Oportunidade(
                "REVISAO_NCM", "Revisão de NCM – itens com indício de enquadramento monofásico",
                suspeitos * aliq.parcela(f.p_pis + f.p_cofins), "MEDIA",
                "NCMs com indício de classificação incorreta: reclassificados para códigos dos Anexos da Lei 10.485/2002, "
                "passam a monofásico. Confira a classificação na tabela de NCM."))

    rbt12 = simples.detalhes["rbt12"]
    if no_simples and rbt12 >= p.sublimite_simples * p.alerta_sublimite:
        ops.append(Oportunidade(
            "SUBLIMITE", "Sublimite de R$ 3,6 mi – ponto de virada", None, "ALTA",
            f"RBT12 de {_brl(rbt12)} ({_pct(rbt12 / p.sublimite_simples, 0)} do sublimite). Acima de R$ 3,6 mi o ICMS sai do DAS "
            "e passa a ser recolhido no regime normal. Ver simulação de crescimento."))

    share_interna = pr.composicao_compras.get(p.aliq_icms_interna, ZERO)
    compras = sum((b.compras for b in bases.values()), ZERO)
    if share_interna > 0 and p.aliq_icms_interna > p.aliq_icms_interestadual:
        ops.append(Oportunidade(
            "CREDITO_ICMS_INTERNAS", "Crédito de ICMS à alíquota interna nas compras internas",
            compras * share_interna * (p.aliq_icms_interna - p.aliq_icms_interestadual), "MEDIA",
            "O crédito é o ICMS destacado na entrada: compras de fornecedores da mesma UF geram a alíquota interna, "
            "não a interestadual. Ajustar a composição real das entradas por origem."))

    if not pr.excluir_icms_base_pis_cofins:
        icms_trib = sum((icms.debito_por_item.get(i, ZERO) for i, it in enumerate(itens) if it.tributado_pis_cofins), ZERO)
        if icms_trib > 0:
            ops.append(Oportunidade(
                "TEMA_69", "Exclusão do ICMS da base do PIS/COFINS (Tema 69/STF)", icms_trib * aliq_pc_nc, "MEDIA",
                "Aplicável no LP e no LR. Valor = economia no Lucro Real (9,25% sobre o ICMS das vendas não monofásicas); "
                "no LP o ganho é de 3,65%."))

    if not pr.credito_frete_integral:
        extra = sum((pc_lr.despesas_com_credito[c] * (1 - bases[c].participacao_nao_monofasica)
                     for c in entrada.competencias), ZERO) * aliq_pc_nc
        if extra > 0:
            ops.append(Oportunidade(
                "CREDITO_FRETE_INTEGRAL", "Crédito integral de PIS/COFINS sobre fretes e armazenagem (LR)", extra, "MEDIA",
                "Tarifas de envio e armazenagem são frete/armazenagem na venda (Lei 10.833/2003, art. 3º, IX). "
                "A simulação adota o crédito proporcional (conservador); a tese do crédito integral acrescenta este valor."))

    if entrada.despesas_nao_informadas:
        ops.append(Oportunidade(
            "DESPESAS_NAO_INFORMADAS", "Despesas dedutíveis e creditáveis não informadas", None, "ALTA",
            _lista_despesas(entrada.despesas_nao_informadas) +
            " Reduzem o IRPJ/CSLL no Lucro Real e podem gerar créditos."))

    devol = sum(entrada.devolucoes.values(), ZERO)
    bruto = sum((b.receita_bruta for b in bases.values()), ZERO)
    if devol > 0:
        ops.append(Oportunidade(
            "DEVOLUCOES", "Devoluções de vendas", None, "MEDIA",
            f"Incorporadas ao estudo: {_brl(devol)} no período ({_pct(devol / bruto)} do faturamento bruto), deduzidas em todos os "
            "regimes. Garantir a dedução no PGDAS-D e o estorno do ICMS das devoluções."))

    if any(not i.item.gera_receita and i.item.ambito == Ambito.INTERESTADUAL for i in itens):
        ops.append(Oportunidade(
            "REMESSAS_FULFILLMENT", "Remessas para fulfillment em outros estados", None, "MEDIA",
            "Há remessas interestaduais sem receita (ex.: CFOP 6.949/6.905). Avaliar a inscrição estadual no estado do CD "
            "e o estudo de filial em UF com incentivo ao e-commerce."))

    if no_simples and pr.vendas_b2c:
        ops.append(Oportunidade(
            "REFORMA_POR_FORA", "Reforma – opção pelo IBS/CBS por fora do DAS", None, "BAIXA",
            "Não recomendada para vendas a consumidor final (B2C), que não aproveitam crédito."))

    e = entrada.estoque_st
    if e is not None:
        ano, mes = e.inicio_uso.split("-")
        uso = (f"em 12 parcelas mensais lançadas como outros créditos na apuração do ICMS, a partir de {mes}/{ano}" if e.regime_rpa
               else f"abatido do ICMS do DAS no PGDAS-D a partir de {mes}/{ano}, com o saldo passando para os meses seguintes")
        ops.append(Oportunidade(
            "CREDITO_ESTOQUE_ST", "Crédito do ICMS-ST do estoque (fim da ST)", e.credito, "ALTA",
            f"Mercadorias saíram da ST{f' pela {e.norma}' if e.norma else ''}. O ICMS-ST pago no estoque de {e.corte} vira crédito, {uso} "
            "(Portaria CAT 28/2020). Levantar o inventário dessa data, montar o relatório por item com as notas de entrada mais recentes "
            "e escriturar o inventário (Bloco H, para quem entrega a EFD). Valor estimado pelas notas de entrada com ST."))

    if receita == 0:
        return []
    return ops


def pontos_criticos(entrada: EntradaSimulacao, simples: ResultadoRegime) -> list[PontoCritico]:
    pr = entrada.premissas
    pts: list[PontoCritico] = []
    difal = [i for i in entrada.itens if i.difal is not None and i.gera_receita]
    if difal:
        ufs = sorted({i.difal.uf for i in difal})
        pts.append(PontoCritico("DIFAL", f"{_brl(sum((i.valor for i in difal), ZERO))} em vendas a consumidor final não contribuinte de "
                                         f"{len(ufs)} estado(s) ({', '.join(ufs)}). No Lucro Presumido e no Lucro Real o DIFAL dessas vendas, "
                                         "com o FCP, é pago ao estado de destino e já está no ICMS; no Simples não é devido (STF, ADI 5464)."))
    if not entrada.folha_informada:
        pts.append(PontoCritico("FOLHA", "Folha e pró-labore não informados: LP e LR calculados sem INSS sobre folha; "
                                         "cada R$ 1.000/mês de pró-labore acrescenta R$ 600 de INSS por trimestre."))
    if pr.estoque_inicial is None or pr.estoque_final is None:
        pts.append(PontoCritico("ESTOQUE", "CMV no Lucro Real calculado pelas compras do período, sem inventário "
                                           "(estoque inicial = final). Com estoque crescendo, o lucro tributável é maior."))
    else:
        compras = sum((entrada.compras.get(c, ZERO) for c in entrada.competencias), ZERO)
        if pr.estoque_inicial + compras - pr.estoque_final < 0:
            pts.append(PontoCritico("CMV_NEGATIVO", "Custo das mercadorias negativo: o estoque final é maior que o estoque inicial "
                                                    "mais as compras. Confira os valores, pois isso aumenta o lucro no Lucro Real."))
    if entrada.icms_entradas_real is None:
        texto = "Crédito de ICMS estimado pela composição das compras por origem (sem XML de entrada)."
        if not entrada.composicao_informada:
            texto = ("Origem das compras não informada: o crédito de ICMS assume 100% de compras internas. "
                     "Se parte vier de outros estados ou for importada, o crédito é menor e o ICMS a recolher, maior.")
        pts.append(PontoCritico("CREDITO_ICMS", texto))
    if entrada.ncms_confianca_media or entrada.ncms_indicio_incorreto:
        pts.append(PontoCritico("NCM", f"Monofásico: {len(entrada.ncms_confianca_media)} NCM(s) com confiança média e "
                                       f"{len(entrada.ncms_indicio_incorreto)} com indício de NCM incorreto."))
    if simples.detalhes.get("rbt12_estimado") == 1:
        pts.append(PontoCritico("RBT12", "RBT12 estimado pela média do período × 12 (sem extrato do PGDAS-D)."))
    pts.append(PontoCritico("REFORMA", "Alíquotas de IBS/CBS são projeções oficiais, sujeitas à Resolução do Senado."))
    pts.append(PontoCritico("OPCAO", "A troca de regime é formalizada em janeiro e vale para todo o ano-calendário."))
    return pts
