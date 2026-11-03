import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import { Botao, Card, Erro, Obrigatorio } from "../components/ui";
import { brl, editarMoeda, lerMoeda, percentual } from "../lib/formato";
import { EstoqueSt } from "./EstoqueSt";

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

const MOEDAS = {
  rbt12_informado: "Receita bruta dos últimos 12 meses (RBT12 do PGDAS-D)",
  estoque_inicial: "Estoque inicial do período",
  estoque_final: "Estoque final do período",
  adicoes_lr: "Adições ao lucro (despesas indedutíveis)",
  exclusoes_lr: "Exclusões do lucro",
  prejuizo_fiscal_compensar: "Prejuízo fiscal a compensar",
} as const;
type ChaveMoeda = keyof typeof MOEDAS;
const OPCOES = [
  { chave: "aplicar_st_vendas_internas", padrao: false, rotulo: "Vendas internas com ICMS-ST", ajuda: "Marque para períodos em que os produtos estavam na substituição tributária. O ICMS sai do DAS e do débito nas vendas internas." },
  { chave: "excluir_icms_base_pis_cofins", padrao: false, rotulo: "Excluir o ICMS da base do PIS/COFINS", ajuda: "Tema 69 do STF. Vale para Lucro Presumido e Lucro Real." },
  { chave: "credito_frete_integral", padrao: false, rotulo: "Crédito integral de PIS/COFINS sobre fretes", ajuda: "Desmarcado, o crédito é proporcional às vendas não monofásicas (posição conservadora)." },
  { chave: "vendas_b2c", padrao: true, rotulo: "Vendas para consumidor final", ajuda: "Usado na análise da opção pelo IBS/CBS fora do DAS." },
] as const;

const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5 disabled:bg-bg";

/** De onde vem o valor: informado pelo contador (sem marca), das notas (com a explicação) ou pendente. */
function Procedencia({ auto, informado, vazio }: { auto?: Automatica; informado: boolean; vazio?: boolean }) {
  if (informado && !vazio) return null;
  if (auto && !informado)
    return (
      <span className="mt-1 block text-xs text-brand">
        <span className="mr-1 rounded bg-highlight px-1.5 py-0.5 font-medium">Das notas</span>
        {auto.fonte}
      </span>
    );
  return <span className="mt-1 block text-xs font-medium text-alert-ink">Pendente: informe para concluir as premissas</span>;
}

const mesmo = (a: unknown, b: unknown) => (typeof a === "boolean" || typeof b === "boolean" ? a === b : Number(a) === Number(b));

export function Premissas({ pid }: { pid: number }) {
  const { data } = useQuery({
    queryKey: ["coleta", pid],
    queryFn: async () => (await api.get<Coleta>(`/planejamentos/${pid}/coleta`)).data,
  });
  const { data: parametros } = useQuery({
    queryKey: ["parametros"],
    queryFn: async () => (await api.get<Parametro[]>("/tabelas/parametros")).data,
  });
  if (!data || !parametros) return <p>Carregando…</p>;
  const interna = Number(parametros.find((p) => p.chave === "aliq_icms_interna")?.valor ?? 0.18);
  return (
    <div className="space-y-4">
      <OrigemCompras pid={pid} coleta={data} interna={interna} />
      <EstoqueSt pid={pid} />
      <FormPremissas pid={pid} coleta={data} />
    </div>
  );
}

function useConcluir(pid: number) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["coleta", pid] });
    qc.invalidateQueries({ queryKey: ["simulacoes", pid] });
    qc.invalidateQueries({ queryKey: ["planejamento", String(pid)] });
  };
}

const AVISO_SIMULACAO = "Salvo. As simulações deste planejamento ficam desatualizadas: gere uma nova na aba Simulações.";

function OrigemCompras({ pid, coleta, interna }: { pid: number; coleta: Coleta; interna: number }) {
  const linhas = [
    { origem: "Compras internas (fornecedor da mesma UF)", aliquota: interna },
    { origem: "Interestaduais a 12% (regra geral)", aliquota: 0.12 },
    { origem: "Interestaduais a 7% (de Sul e Sudeste para Norte, Nordeste, Centro-Oeste e ES)", aliquota: 0.07 },
    { origem: "Importados (4%, Resolução do Senado 13/2012)", aliquota: 0.04 },
  ];
  const informada = coleta.composicao_compras.length > 0;
  const auto = coleta.composicao_auto;
  const base: { aliquota: number; percentual: number }[] = informada ? coleta.composicao_compras : (auto?.linhas ?? []);
  const inicial = () =>
    Object.fromEntries(linhas.map((l) => {
      const o = base.find((x) => Math.abs(Number(x.aliquota) - l.aliquota) < 0.0001);
      return [l.aliquota, o ? editarMoeda(Number(o.percentual) * 100) : ""];
    }));
  const [valores, setValores] = useState<Record<string, string>>(inicial);
  useEffect(() => setValores(inicial()), [coleta]); // eslint-disable-line react-hooks/exhaustive-deps
  const [erro, setErro] = useState<string | null>(null);
  const [salvo, setSalvo] = useState(false);
  const concluir = useConcluir(pid);

  const pct = (a: number) => lerMoeda(valores[a] ?? "") ?? 0;
  const total = linhas.reduce((s, l) => s + pct(l.aliquota), 0);
  const media = linhas.reduce((s, l) => s + (pct(l.aliquota) / 100) * l.aliquota, 0);
  const fecha = Math.abs(total - 100) < 0.005;
  const compras = Object.values(coleta.compras).reduce((s, v) => s + Number(v), 0);

  const salvar = useMutation({
    mutationFn: () =>
      api.put(`/planejamentos/${pid}/composicao-compras`, linhas.filter((l) => pct(l.aliquota) > 0).map((l) => ({
        origem: l.origem, aliquota: l.aliquota, percentual: Number((pct(l.aliquota) / 100).toFixed(4)),
      }))),
    onSuccess: () => {
      setErro(null);
      setSalvo(true);
      concluir();
    },
    onError: (e) => {
      setSalvo(false);
      setErro(mensagemErro(e));
    },
  });
  const usarNotas = useMutation({
    mutationFn: () => api.delete(`/planejamentos/${pid}/composicao-compras`),
    onSuccess: () => {
      setErro(null);
      setSalvo(false);
      concluir();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  return (
    <Card titulo="Origem das compras">
      <p className="mb-3 max-w-[75ch] text-sm text-text-muted">
        Define o crédito de ICMS no Lucro Presumido e no Lucro Real. O crédito é o imposto destacado na nota de compra, que muda conforme a origem do fornecedor.
      </p>
      {!informada && auto && (
        <p className="mb-3 rounded border border-brand/30 bg-highlight px-3 py-2 text-sm">
          <span className="mr-1 rounded bg-white px-1.5 py-0.5 text-xs font-medium text-brand">Das notas</span>
          Calculada pelas notas de compra importadas: {auto.fonte}. Ao alterar e salvar, vale o que você informar.
        </p>
      )}
      {informada && auto && (
        <p className="mb-3 flex flex-wrap items-center gap-2 text-sm text-text-muted">
          Informada pelo contador. As notas de compra indicam outra composição.
          <Botao variante="linha" disabled={usarNotas.isPending} onClick={() => usarNotas.mutate()}>
            Usar a das notas
          </Botao>
        </p>
      )}
      {!informada && !auto && (
        <p className="mb-3 rounded border border-warning bg-warning-soft px-3 py-2 text-sm text-warning-ink">
          Pendente. Importe o XML das notas de compra para o sistema calcular, ou informe abaixo. Enquanto isso, a simulação assume 100% de compras
          internas, o que pode superestimar o crédito.
        </p>
      )}
      <table className="condensado w-full max-w-2xl text-sm">
        <thead>
          <tr className="border-b border-border text-text-muted">
            <th className="py-1.5 text-left font-medium">Origem</th>
            <th className="px-2 py-1.5 text-right font-medium">Alíquota</th>
            <th className="py-1.5 text-right font-medium">% das compras</th>
          </tr>
        </thead>
        <tbody>
          {linhas.map((l) => (
            <tr key={l.aliquota} className="border-b border-surface">
              <td className="py-1.5">{l.origem}</td>
              <td className="num px-2 py-1.5">{percentual(l.aliquota)}</td>
              <td className="py-1.5 text-right">
                <input
                  aria-label={`Percentual: ${l.origem}`}
                  inputMode="decimal"
                  placeholder="0,00"
                  className="num w-24 rounded border border-border bg-white px-2 py-1"
                  value={valores[l.aliquota] ?? ""}
                  onChange={(e) => {
                    setSalvo(false);
                    setValores({ ...valores, [l.aliquota]: e.target.value.replace(/[^\d.,]/g, "") });
                  }}
                />
              </td>
            </tr>
          ))}
          <tr className="font-semibold">
            <td className="py-1.5">Total</td>
            <td className="num px-2 py-1.5">{percentual(media)} média</td>
            <td className={`num py-1.5 ${fecha ? "" : "text-alert"}`}>{total.toFixed(2).replace(".", ",")}%</td>
          </tr>
        </tbody>
      </table>
      {compras > 0 && fecha && <p className="mt-2 text-sm text-text-muted">Com {brl(compras)} em compras, o crédito de ICMS estimado é de {brl(compras * media)}.</p>}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Botao disabled={!fecha || salvar.isPending} onClick={() => salvar.mutate()}>
          Salvar origem das compras
        </Botao>
        {!fecha && <span className="text-sm text-alert-ink">A soma precisa dar 100%.</span>}
        {salvo && <span className="text-sm text-success-ink">✔ {AVISO_SIMULACAO}</span>}
      </div>
      <div className="mt-2">
        <Erro mensagem={erro} />
      </div>
    </Card>
  );
}

function FormPremissas({ pid, coleta }: { pid: number; coleta: Coleta }) {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const informado = (k: string) => coleta.premissas[k] != null;
  const auto = coleta.premissas_auto;
  // informado pelo contador > tirado das notas > padrão
  const valor = (k: string) => (informado(k) ? coleta.premissas[k] : auto[k]?.valor);
  const inicial = () => ({
    moedas: Object.fromEntries((Object.keys(MOEDAS) as ChaveMoeda[]).map((k) => [k, valor(k) != null ? editarMoeda(Number(valor(k))) : ""])) as Record<ChaveMoeda, string>,
    opcoes: Object.fromEntries(OPCOES.map((o) => [o.chave, (valor(o.chave) as boolean | undefined) ?? o.padrao])) as Record<string, boolean>,
    pct: valor("pct_compras_credito_ibs_cbs") != null ? editarMoeda(Number(valor("pct_compras_credito_ibs_cbs")) * 100) : "",
  });
  const [f, setF] = useState(inicial);
  const [erro, setErro] = useState<string | null>(null);
  const [salvo, setSalvo] = useState(false);
  const concluir = useConcluir(pid);
  useEffect(() => setF(inicial()), [coleta]); // eslint-disable-line react-hooks/exhaustive-deps

  const salvar = useMutation({
    mutationFn: () => {
      const corpo: Record<string, unknown> = { ...f.opcoes };
      (Object.keys(MOEDAS) as ChaveMoeda[]).forEach((k) => (corpo[k] = lerMoeda(f.moedas[k])));
      const pct = lerMoeda(f.pct);
      corpo.pct_compras_credito_ibs_cbs = pct == null ? null : pct / 100;
      // valor igual ao das notas, sem nada informado antes: continua seguindo as notas
      for (const k of Object.keys(corpo)) if (!informado(k) && auto[k] && mesmo(corpo[k], auto[k].valor)) corpo[k] = null;
      return api.put(`/planejamentos/${pid}/premissas`, corpo);
    },
    onSuccess: () => {
      setErro(null);
      setSalvo(true);
      concluir();
    },
    onError: (e) => {
      setSalvo(false);
      setErro(mensagemErro(e));
    },
  });

  const moeda = (k: ChaveMoeda) => (
    <label key={k}>
      {MOEDAS[k]}
      <Obrigatorio />
      <input
        inputMode="decimal"
        disabled={!contador}
        className={`${campo} num`}
        placeholder="não informado"
        value={f.moedas[k]}
        onChange={(e) => {
          setSalvo(false);
          setF({ ...f, moedas: { ...f.moedas, [k]: e.target.value.replace(/[^\d.,]/g, "") } });
        }}
      />
      <Procedencia auto={auto[k]} informado={informado(k)} vazio={!f.moedas[k]} />
    </label>
  );
  const semRbt12 = !lerMoeda(f.moedas.rbt12_informado);
  const umEstoque = !f.moedas.estoque_inicial !== !f.moedas.estoque_final;

  return (
    <Card titulo="Premissas do cálculo">
      {!contador && <p className="mb-3 text-sm text-text-muted">Só o contador altera estas premissas.</p>}
      <p className="mb-4 max-w-[80ch] text-sm text-text-muted">
        O que dá para tirar das notas importadas já vem preenchido. O que ficar pendente aparece na aba Pendências até ser informado; salvar
        confirma as opções marcadas.
      </p>
      <div className="grid gap-6 text-sm lg:grid-cols-2">
        <section className="space-y-3">
          <h3 className="font-semibold">Simples Nacional</h3>
          {moeda("rbt12_informado")}
          {semRbt12 && <p className="text-text-muted">Enquanto estiver vazio, o sistema estima pela média do período × 12.</p>}
          <h3 className="pt-2 font-semibold">Estoque</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {moeda("estoque_inicial")}
            {moeda("estoque_final")}
          </div>
          <p className={umEstoque ? "text-alert-ink" : "text-text-muted"}>
            {umEstoque ? "Informe os dois valores, ou deixe os dois vazios." : "Sem estoque, informe 0,00 nos dois: o custo das mercadorias no Lucro Real fica igual às compras do período."}
          </p>
          <h3 className="pt-2 font-semibold">Lucro Real</h3>
          {moeda("adicoes_lr")}
          {moeda("exclusoes_lr")}
          {moeda("prejuizo_fiscal_compensar")}
        </section>
        <section className="space-y-3">
          <h3 className="font-semibold">Opções tributárias</h3>
          {OPCOES.map((o) => (
            <label key={o.chave} className="flex items-start gap-2">
              <input
                type="checkbox"
                className="mt-1"
                disabled={!contador}
                checked={f.opcoes[o.chave]}
                onChange={(e) => {
                  setSalvo(false);
                  setF({ ...f, opcoes: { ...f.opcoes, [o.chave]: e.target.checked } });
                }}
              />
              <span>
                {o.rotulo}
                <Obrigatorio />
                <span className="block text-text-muted">{o.ajuda}</span>
                <Procedencia auto={auto[o.chave]} informado={informado(o.chave)} />
                {o.chave === "aplicar_st_vendas_internas" && !informado(o.chave) && !auto[o.chave] && coleta.indicio_st && (
                  <span className="mt-1 block text-xs text-warning-ink">{coleta.indicio_st}</span>
                )}
              </span>
            </label>
          ))}
          <h3 className="pt-2 font-semibold">Reforma Tributária</h3>
          <label>
            Compras com crédito de IBS/CBS (%)
            <Obrigatorio />
            <input
              inputMode="decimal"
              disabled={!contador}
              className={`${campo} num max-w-32`}
              value={f.pct}
              onChange={(e) => {
                setSalvo(false);
                setF({ ...f, pct: e.target.value.replace(/[^\d.,]/g, "") });
              }}
            />
            <Procedencia auto={auto.pct_compras_credito_ibs_cbs} informado={informado("pct_compras_credito_ibs_cbs")} vazio={!f.pct} />
          </label>
          <p className="text-text-muted">Compras de optantes do Simples geram crédito limitado ao valor pago no DAS.</p>
        </section>
      </div>
      {contador && (
        <div className="mt-4 space-y-2">
          <Erro mensagem={erro} />
          <div className="flex flex-wrap items-center gap-3">
            <Botao disabled={umEstoque || salvar.isPending} onClick={() => salvar.mutate()}>
              Salvar premissas
            </Botao>
            {salvo && <span className="text-sm text-success-ink">✔ {AVISO_SIMULACAO}</span>}
          </div>
        </div>
      )}
    </Card>
  );
}
