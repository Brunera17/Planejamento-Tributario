import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import { Botao, Card, Erro } from "../components/ui";
import { brl, editarMoeda, lerMoeda, percentual } from "../lib/formato";
import { dataBr, DetalheEstoqueSt, useEstoqueSt, usoDoCredito } from "./EstoqueSt";

type Origem = { origem: string; aliquota: number; percentual: number };
type Automatica = { valor: string | number | boolean; fonte: string };
type Coleta = {
  composicao_compras: Origem[];
  premissas: Record<string, string | boolean>;
  premissas_auto: Record<string, Automatica>;
  composicao_auto: { linhas: { aliquota: number; percentual: number }[]; fonte: string } | null;
  indicio_st: string | null;
  compras: Record<string, number>;
};
type Parametro = { chave: string; valor: number };
type Marca = "notas" | "pgdas" | "lei" | "pendente" | null;

const MOEDAS = {
  rbt12_informado: { rotulo: "RBT12 (PGDAS-D)", ajuda: "Receita bruta dos últimos 12 meses. Com o extrato do PGDAS-D enviado em Documentos, vem preenchido; vazio, o sistema estima pela média do período × 12." },
  estoque_inicial: { rotulo: "Estoque inicial", ajuda: "Com o estoque final, dá o custo das mercadorias no Lucro Real. Sem estoque, informe 0,00 nos dois." },
  estoque_final: { rotulo: "Estoque final", ajuda: "Com o estoque inicial, dá o custo das mercadorias no Lucro Real. Sem estoque, informe 0,00 nos dois." },
  adicoes_lr: { rotulo: "Adições", ajuda: "Despesas indedutíveis e outras adições ao lucro real." },
  exclusoes_lr: { rotulo: "Exclusões", ajuda: "Receitas e valores que saem da base do lucro real." },
  prejuizo_fiscal_compensar: { rotulo: "Prejuízo fiscal", ajuda: "Saldo a compensar, limitado a 30% do lucro do período (Lei 9.065/1995, art. 15)." },
} as const;
type ChaveMoeda = keyof typeof MOEDAS;
const OPCOES = [
  {
    chave: "aplicar_st_vendas_internas",
    padrao: false,
    rotulo: "ICMS-ST nas vendas internas",
    ajuda: "Para períodos em que os produtos estavam na substituição tributária: o ICMS sai do DAS e do débito nas vendas internas.",
  },
  {
    chave: "excluir_icms_base_pis_cofins",
    padrao: false,
    rotulo: "ICMS fora da base do PIS/COFINS",
    ajuda: "Tema 69 do STF. Vale para o Lucro Presumido e o Lucro Real.",
  },
  {
    chave: "credito_frete_integral",
    padrao: false,
    rotulo: "Crédito integral sobre fretes",
    ajuda: "Desmarcado, o crédito de PIS/COFINS do frete é proporcional às vendas não monofásicas (posição conservadora).",
  },
  { chave: "vendas_b2c", padrao: true, rotulo: "Venda a consumidor final", ajuda: "Usado na análise da opção pelo IBS/CBS fora do DAS." },
] as const;
const AVISO_SIMULACAO = "Salvo. As simulações deste planejamento ficam desatualizadas: gere uma nova na aba Simulações.";
const entrada = "num w-full rounded border border-border bg-white px-2 py-1 disabled:bg-bg";
const soNumero = (v: string) => v.replace(/[^\d.,]/g, "");
const mesmo = (a: unknown, b: unknown) => (typeof a === "boolean" || typeof b === "boolean" ? a === b : Number(a) === Number(b));

function Info({ aberta, alternar, rotulo }: { aberta: boolean; alternar: () => void; rotulo: string }) {
  return (
    <button
      type="button"
      onClick={alternar}
      aria-expanded={aberta}
      aria-label={`Como funciona: ${rotulo}`}
      className={`inline-flex h-4 w-4 items-center justify-center rounded-full border text-[10px] leading-none font-semibold ${aberta ? "border-brand bg-brand text-white" : "border-text-muted text-text-muted hover:border-brand hover:text-brand"}`}
    >
      i
    </button>
  );
}

const MARCAS: Record<Exclude<Marca, null>, { texto: string; classe: string }> = {
  notas: { texto: "das notas", classe: "text-brand" },
  pgdas: { texto: "do PGDAS-D", classe: "text-brand" },
  lei: { texto: "pela lei", classe: "text-brand" },
  pendente: { texto: "pendente", classe: "font-medium text-alert-ink" },
};

/** Bloco de um assunto: título e, dentro, os campos em ficha. */
function Bloco({ titulo, colunas = 1, acao, children }: { titulo: string; colunas?: 1 | 2 | 3; acao?: ReactNode; children: ReactNode }) {
  const grade = { 1: "", 2: "sm:grid-cols-2", 3: "sm:grid-cols-3" }[colunas];
  return (
    <section>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <h3 className="font-semibold">{titulo}</h3>
        {acao}
      </div>
      <div className={`grid grid-cols-1 overflow-hidden rounded-md border-t border-l border-border bg-white ${grade}`}>{children}</div>
    </section>
  );
}

/** Caixa no estilo dos campos do DANFE: rótulo pequeno, valor, de onde ele veio e a explicação só quando pedida. */
function Caixa({ rotulo, ajuda, marca, largo, children }: { rotulo: string; ajuda: ReactNode; marca: Marca; largo?: boolean; children: ReactNode }) {
  const [aberta, setAberta] = useState(false);
  return (
    <div className={`border-r border-b border-border px-3 py-2 ${largo ? "sm:col-span-2" : ""} ${marca === "pendente" ? "[&_input]:border-alert/60" : ""}`}>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-text-muted">
        <span className="flex items-center gap-1.5">
          {rotulo}
          <Info aberta={aberta} alternar={() => setAberta(!aberta)} rotulo={rotulo} />
        </span>
        {marca && <span className={MARCAS[marca].classe}>{MARCAS[marca].texto}</span>}
      </div>
      {children}
      {aberta && <div className="mt-1.5 text-xs text-text-muted">{ajuda}</div>}
    </div>
  );
}

export function Premissas({ pid }: { pid: number }) {
  const { data } = useQuery({ queryKey: ["coleta", pid], queryFn: async () => (await api.get<Coleta>(`/planejamentos/${pid}/coleta`)).data });
  const { data: parametros } = useQuery({ queryKey: ["parametros"], queryFn: async () => (await api.get<Parametro[]>("/tabelas/parametros")).data });
  const { data: st, isFetched } = useEstoqueSt(pid);
  if (!data || !parametros || !isFetched) return <p>Carregando…</p>;
  const interna = Number(parametros.find((p) => p.chave === "aliq_icms_interna")?.valor ?? 0.18);
  return <FormPremissas pid={pid} coleta={data} interna={interna} st={st ?? null} />;
}

function FormPremissas({ pid, coleta, interna, st }: { pid: number; coleta: Coleta; interna: number; st: ReturnType<typeof useEstoqueSt>["data"] | null }) {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const qc = useQueryClient();
  const informado = (k: string) => coleta.premissas[k] != null;
  const auto = coleta.premissas_auto;
  // informado pelo contador > tirado das notas > padrão
  const valor = (k: string) => (informado(k) ? coleta.premissas[k] : auto[k]?.valor);

  const origens = [
    { origem: "Compras internas (fornecedor da mesma UF)", rotulo: "internas", aliquota: interna },
    { origem: "Interestaduais a 12% (regra geral)", rotulo: "12%", aliquota: 0.12 },
    { origem: "Interestaduais a 7% (de Sul e Sudeste para Norte, Nordeste, Centro-Oeste e ES)", rotulo: "7%", aliquota: 0.07 },
    { origem: "Importados (4%, Resolução do Senado 13/2012)", rotulo: "importados", aliquota: 0.04 },
  ];
  const compInformada = coleta.composicao_compras.length > 0;
  const compAuto = coleta.composicao_auto;
  const compBase = compInformada ? coleta.composicao_compras : (compAuto?.linhas ?? []);

  const inicial = () => ({
    moedas: Object.fromEntries((Object.keys(MOEDAS) as ChaveMoeda[]).map((k) => [k, valor(k) != null ? editarMoeda(Number(valor(k))) : ""])) as Record<
      ChaveMoeda,
      string
    >,
    opcoes: Object.fromEntries(OPCOES.map((o) => [o.chave, (valor(o.chave) as boolean | undefined) ?? o.padrao])) as Record<string, boolean>,
    pct: valor("pct_compras_credito_ibs_cbs") != null ? editarMoeda(Number(valor("pct_compras_credito_ibs_cbs")) * 100) : "",
    rat: valor("rat") != null ? String(Math.round(Number(valor("rat")) * 100)) : "",
    fap: valor("fap") != null ? Number(valor("fap")).toLocaleString("pt-BR", { minimumFractionDigits: 4, maximumFractionDigits: 4 }) : "",
    terceiros: valor("terceiros") != null ? editarMoeda(Number(valor("terceiros")) * 100) : "",
    comp: Object.fromEntries(
      origens.map((l) => {
        const o = compBase.find((x) => Math.abs(Number(x.aliquota) - l.aliquota) < 0.0001);
        return [l.aliquota, o ? editarMoeda(Number(o.percentual) * 100) : ""];
      }),
    ) as Record<string, string>,
    estoqueSt: st?.estoque != null ? editarMoeda(Number(st.estoque)) : "",
  });
  const [f, setF] = useState(inicial);
  const [base, setBase] = useState(inicial);
  const [erro, setErro] = useState<string | null>(null);
  const [salvo, setSalvo] = useState(false);
  const [detalheSt, setDetalheSt] = useState(false);
  useEffect(() => {
    const novo = inicial();
    setF(novo);
    setBase(novo);
  }, [coleta, st]); // eslint-disable-line react-hooks/exhaustive-deps
  const mudar = (parcial: Partial<typeof f>) => {
    setSalvo(false);
    setF({ ...f, ...parcial });
  };

  const pctComp = (a: number) => lerMoeda(f.comp[a] ?? "") ?? 0;
  const totalComp = origens.reduce((s, l) => s + pctComp(l.aliquota), 0);
  const mediaComp = origens.reduce((s, l) => s + (pctComp(l.aliquota) / 100) * l.aliquota, 0);
  const compMudou = JSON.stringify(f.comp) !== JSON.stringify(base.comp);
  const compFecha = Math.abs(totalComp - 100) < 0.005;
  const stMudou = f.estoqueSt !== base.estoqueSt;
  const umEstoque = !f.moedas.estoque_inicial !== !f.moedas.estoque_final;
  const folhaInformada = Boolean(f.rat || f.fap || f.terceiros);
  const encargos = 20 + (f.rat ? Number(f.rat) : 2) * (lerMoeda(f.fap) ?? 1) + (lerMoeda(f.terceiros) ?? 5.8);
  const comprasTotal = Object.values(coleta.compras).reduce((s, v) => s + Number(v), 0);
  const creditoSt = st?.taxa != null && lerMoeda(f.estoqueSt) != null ? lerMoeda(f.estoqueSt)! * st.taxa : null;

  // o RBT12 automático vem do extrato do PGDAS-D enviado em Documentos; o Tema 69, da decisão do STF; o resto, das notas
  const origemAuto = (k: string): "pgdas" | "lei" | "notas" => (k === "rbt12_informado" ? "pgdas" : k === "excluir_icms_base_pis_cofins" ? "lei" : "notas");
  const marca = (k: string, vazio: boolean): Marca => (auto[k] && !informado(k) ? origemAuto(k) : vazio ? "pendente" : null);
  const fonte = (k: string) =>
    auto[k] && !informado(k) ? (
      <span className="mt-1 block text-brand">
        {{ pgdas: "Do", lei: "Pela lei:", notas: "Das notas:" }[origemAuto(k)]} {auto[k].fonte}
      </span>
    ) : null;
  const LR = ["adicoes_lr", "exclusoes_lr", "prejuizo_fiscal_compensar"] as const;
  const lrVazios = LR.filter((k) => !f.moedas[k]);

  const salvar = useMutation({
    mutationFn: async () => {
      if (contador) {
        const corpo: Record<string, unknown> = { ...f.opcoes };
        (Object.keys(MOEDAS) as ChaveMoeda[]).forEach((k) => (corpo[k] = lerMoeda(f.moedas[k])));
        const pct = lerMoeda(f.pct);
        corpo.pct_compras_credito_ibs_cbs = pct == null ? null : pct / 100;
        corpo.rat = f.rat ? Number(f.rat) / 100 : null;
        corpo.fap = lerMoeda(f.fap);
        const terceiros = lerMoeda(f.terceiros);
        corpo.terceiros = terceiros == null ? null : terceiros / 100;
        // valor igual ao das notas, sem nada informado antes: continua seguindo as notas
        for (const k of Object.keys(corpo)) if (!informado(k) && auto[k] && mesmo(corpo[k], auto[k].valor)) corpo[k] = null;
        await api.put(`/planejamentos/${pid}/premissas`, corpo);
      }
      if (compMudou)
        await api.put(
          `/planejamentos/${pid}/composicao-compras`,
          origens
            .filter((l) => pctComp(l.aliquota) > 0)
            .map((l) => ({
              origem: l.origem,
              aliquota: l.aliquota,
              percentual: Number((pctComp(l.aliquota) / 100).toFixed(4)),
            })),
        );
      if (stMudou) await api.put(`/planejamentos/${pid}/estoque-st`, { valor: lerMoeda(f.estoqueSt) });
    },
    onSuccess: () => {
      setErro(null);
      setSalvo(true);
      for (const chave of [
        ["coleta", pid],
        ["estoque-st", pid],
        ["simulacoes", pid],
        ["planejamento", String(pid)],
      ])
        qc.invalidateQueries({ queryKey: chave });
    },
    onError: (e) => {
      setSalvo(false);
      setErro(mensagemErro(e));
    },
  });
  const usarNotas = useMutation({
    mutationFn: () => api.delete(`/planejamentos/${pid}/composicao-compras`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["coleta", pid] }),
    onError: (e) => setErro(mensagemErro(e)),
  });

  const bloqueio = umEstoque
    ? "Informe o estoque inicial e o final, ou deixe os dois vazios."
    : compMudou && !compFecha
      ? "A origem das compras precisa somar 100%."
      : null;

  const moeda = (k: ChaveMoeda) => (
    <Caixa
      key={k}
      rotulo={MOEDAS[k].rotulo}
      ajuda={
        <>
          {MOEDAS[k].ajuda}
          {fonte(k)}
        </>
      }
      marca={marca(k, !f.moedas[k])}
    >
      <input
        aria-label={MOEDAS[k].rotulo}
        inputMode="decimal"
        disabled={!contador}
        className={entrada}
        placeholder="não informado"
        value={f.moedas[k]}
        onChange={(e) => mudar({ moedas: { ...f.moedas, [k]: soNumero(e.target.value) } })}
      />
    </Caixa>
  );

  return (
    <Card titulo="Premissas do cálculo" adendo="O que dá para tirar das notas já vem preenchido. Clique no i para ver como cada premissa entra no cálculo.">
      <div className="space-y-4 text-sm">
        <div className="grid gap-x-6 gap-y-5 lg:grid-cols-2">
          <Bloco titulo="Simples Nacional">{moeda("rbt12_informado")}</Bloco>
          <Bloco titulo="Estoque do período" colunas={2}>
            {moeda("estoque_inicial")}
            {moeda("estoque_final")}
          </Bloco>
          <Bloco titulo="Compras e crédito de ICMS">
            <Caixa
              rotulo="Origem das compras"
              marca={compInformada ? null : compAuto ? "notas" : "pendente"}
              ajuda={
                <>
                  Define o crédito de ICMS no Lucro Presumido e no Lucro Real: o imposto destacado na nota de compra muda com a origem do fornecedor.
                  {compAuto && !compInformada && <span className="mt-1 block text-brand">Das notas: {compAuto.fonte}</span>}
                  {!compAuto && !compInformada && " Sem notas de compra, a simulação assume 100% internas, o que pode superestimar o crédito."}
                  {compInformada && compAuto && (
                    <button
                      type="button"
                      className="mt-1 block text-brand underline underline-offset-2"
                      disabled={usarNotas.isPending}
                      onClick={() => usarNotas.mutate()}
                    >
                      Usar a composição das notas
                    </button>
                  )}
                </>
              }
            >
              <div className="grid grid-cols-4 gap-1.5">
                {origens.map((l) => (
                  <label key={l.aliquota} className="text-xs text-text-muted">
                    {l.rotulo === "internas" ? `internas ${percentual(l.aliquota)}` : l.rotulo}
                    <input
                      aria-label={`Percentual: ${l.origem}`}
                      inputMode="decimal"
                      placeholder="0,00"
                      className={entrada}
                      value={f.comp[l.aliquota] ?? ""}
                      onChange={(e) => mudar({ comp: { ...f.comp, [l.aliquota]: soNumero(e.target.value) } })}
                    />
                  </label>
                ))}
              </div>
              <div className={`mt-1 text-xs ${compFecha ? "text-text-muted" : "text-alert-ink"}`}>
                {totalComp.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}% das compras, crédito médio de {percentual(mediaComp)}
                {compFecha && comprasTotal > 0 ? ` (${brl(comprasTotal * mediaComp)})` : ""}
              </div>
            </Caixa>
          </Bloco>
          <Bloco
            titulo="Lucro Real"
            colunas={3}
            acao={
              contador &&
              lrVazios.length > 0 && (
                <button
                  type="button"
                  className="text-xs text-brand underline underline-offset-2"
                  onClick={() => mudar({ moedas: { ...f.moedas, ...Object.fromEntries(lrVazios.map((k) => [k, "0,00"])) } })}
                >
                  Não há (0,00 nos vazios)
                </button>
              )
            }
          >
            {moeda("adicoes_lr")}
            {moeda("exclusoes_lr")}
            {moeda("prejuizo_fiscal_compensar")}
          </Bloco>
          <Bloco titulo="Encargos sobre a folha (LP e LR)">
            <Caixa
              rotulo="RAT, FAP e terceiros"
              marca={null}
              ajuda="CPP 20% + RAT × FAP + terceiros (Lei 8.212/1991, art. 22). Em branco vale a referência de 27,8% (RAT 2% e terceiros 5,8%). RAT e FAP estão no eSocial; terceiros dependem do FPAS. No Simples do comércio a CPP já está no DAS."
            >
              <div className="grid grid-cols-3 gap-1.5">
                <label className="text-xs text-text-muted">
                  RAT
                  <select disabled={!contador} className={entrada} value={f.rat} onChange={(e) => mudar({ rat: e.target.value })}>
                    <option value="">2% (ref.)</option>
                    <option value="1">1%</option>
                    <option value="2">2%</option>
                    <option value="3">3%</option>
                  </select>
                </label>
                <label className="text-xs text-text-muted">
                  FAP
                  <input
                    inputMode="decimal"
                    disabled={!contador}
                    className={entrada}
                    placeholder="1,0000"
                    value={f.fap}
                    onChange={(e) => mudar({ fap: soNumero(e.target.value) })}
                  />
                </label>
                <label className="text-xs text-text-muted">
                  Terceiros %
                  <input
                    inputMode="decimal"
                    disabled={!contador}
                    className={entrada}
                    placeholder="5,80"
                    value={f.terceiros}
                    onChange={(e) => mudar({ terceiros: soNumero(e.target.value) })}
                  />
                </label>
              </div>
              <div className="mt-1 text-xs text-text-muted">
                {encargos.toLocaleString("pt-BR", { maximumFractionDigits: 4 })}% sobre a folha{folhaInformada ? "" : " (referência)"}
              </div>
            </Caixa>
          </Bloco>
          <Bloco titulo="Reforma Tributária">
            <Caixa
              rotulo="Compras com crédito de IBS/CBS"
              marca={marca("pct_compras_credito_ibs_cbs", !f.pct)}
              ajuda={
                <>Parte das compras que dá crédito na Reforma. Compras de optantes do Simples creditam só o que foi pago no DAS.{fonte("pct_compras_credito_ibs_cbs")}</>
              }
            >
              <div className="flex items-center gap-1">
                <input
                  aria-label="Compras com crédito de IBS/CBS (%)"
                  inputMode="decimal"
                  disabled={!contador}
                  className={entrada}
                  value={f.pct}
                  onChange={(e) => mudar({ pct: soNumero(e.target.value) })}
                />
                <span className="text-text-muted">%</span>
              </div>
            </Caixa>
          </Bloco>
          {st && (
            <Bloco titulo="Estoque que saiu da ST">
              <Caixa
                rotulo={`Estoque em ${dataBr(st.corte)}`}
                marca={null}
                ajuda="Custo de aquisição, com o ICMS-ST pago, só das mercadorias que saíram da ST. O crédito vem da Portaria CAT 28/2020; em Detalhar estão os NCM e as notas usadas."
              >
                <input
                  aria-label={`Estoque em ${dataBr(st.corte)}`}
                  inputMode="decimal"
                  className={entrada}
                  placeholder="não informado"
                  value={f.estoqueSt}
                  onChange={(e) => mudar({ estoqueSt: soNumero(e.target.value) })}
                />
                <div className="mt-1 flex flex-wrap items-baseline justify-between gap-2 text-xs">
                  <span className={creditoSt != null ? "text-success-ink" : "text-text-muted"}>
                    {creditoSt != null
                      ? `Crédito estimado de ${brl(creditoSt)}, ${usoDoCredito(st)}`
                      : st.taxa == null
                        ? "Faltam notas de entrada com ST para estimar o crédito"
                        : "Informe o estoque para estimar o crédito"}
                  </span>
                  <button type="button" className="text-brand underline underline-offset-2" aria-expanded={detalheSt} onClick={() => setDetalheSt(!detalheSt)}>
                    {detalheSt ? "Fechar" : "Detalhar"}
                  </button>
                </div>
                {detalheSt && (
                  <div className="mt-2 border-t border-surface pt-2">
                    <DetalheEstoqueSt e={st} />
                  </div>
                )}
              </Caixa>
            </Bloco>
          )}
        </div>

        <section>
          <h3 className="mb-1.5 font-semibold">Opções tributárias</h3>
          <div className="grid gap-x-6 gap-y-2 rounded-md border border-border bg-white px-3 py-2.5 sm:grid-cols-2">
            {OPCOES.map((o) => (
              <Opcao
                key={o.chave}
                rotulo={o.rotulo}
                ajuda={
                  <>
                    {o.ajuda}
                    {fonte(o.chave)}
                    {o.chave === "aplicar_st_vendas_internas" && !informado(o.chave) && !auto[o.chave] && coleta.indicio_st && (
                      <span className="mt-1 block text-warning-ink">{coleta.indicio_st}</span>
                    )}
                  </>
                }
                marca={informado(o.chave) ? null : auto[o.chave] ? origemAuto(o.chave) : "pendente"}
                checked={f.opcoes[o.chave]}
                disabled={!contador}
                onChange={(v) => mudar({ opcoes: { ...f.opcoes, [o.chave]: v } })}
              />
            ))}
          </div>
        </section>

        <div className="flex flex-wrap items-center gap-3 border-t border-surface pt-3">
          <Botao disabled={!!bloqueio || salvar.isPending} onClick={() => salvar.mutate()}>
            Salvar premissas
          </Botao>
          {bloqueio && <span className="text-alert-ink">{bloqueio}</span>}
          {salvo && !bloqueio && <span className="text-success-ink">{AVISO_SIMULACAO}</span>}
          {!contador && <span className="text-text-muted">Só o contador altera as premissas; a origem das compras e o estoque você pode informar.</span>}
        </div>
        <Erro mensagem={erro} />
      </div>
    </Card>
  );
}

function Opcao({
  rotulo,
  ajuda,
  marca,
  checked,
  disabled,
  onChange,
}: {
  rotulo: string;
  ajuda: ReactNode;
  marca: Marca;
  checked: boolean;
  disabled: boolean;
  onChange: (v: boolean) => void;
}) {
  const [aberta, setAberta] = useState(false);
  return (
    <div className="max-w-xs">
      <div className="flex items-center gap-1.5">
        <label className="flex items-center gap-2">
          <input type="checkbox" disabled={disabled} checked={checked} onChange={(e) => onChange(e.target.checked)} />
          {rotulo}
        </label>
        <Info aberta={aberta} alternar={() => setAberta(!aberta)} rotulo={rotulo} />
        {marca && <span className={`text-xs ${MARCAS[marca].classe}`}>{MARCAS[marca].texto}</span>}
      </div>
      {aberta && <div className="mt-1 text-xs text-text-muted">{ajuda}</div>}
    </div>
  );
}
