import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, baixarArquivo, lerSessao, mensagemErro } from "../api/cliente";
import type { LinhaNcm, PassoMemoria, Planejamento, Resultado as TResultado, ResultadoRegime, SimulacaoResumo } from "../api/tipos";
import { Badge, Botao, BotaoLink, Card, Erro, Tabela } from "../components/ui";
import { brl, competenciaExtenso, dataHora, percentual, REGIMES } from "../lib/formato";

const CORES: Record<string, string> = {
  SIMPLES_NACIONAL: "var(--color-alert)",
  LUCRO_PRESUMIDO: "var(--color-brand)",
  LUCRO_REAL: "var(--color-text-muted)",
};

export function Resultado() {
  const { id } = useParams();
  const qc = useQueryClient();
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const [erro, setErro] = useState<string | null>(null);
  const [relatorio, setRelatorio] = useState(false);
  const { data } = useQuery({
    queryKey: ["simulacao", id],
    queryFn: async () => (await api.get<{ simulacao: SimulacaoResumo & { planejamento_id: number }; resultado: TResultado }>(`/simulacoes/${id}`)).data,
  });
  const { data: planejamento } = useQuery({
    queryKey: ["planejamento", String(data?.simulacao.planejamento_id)],
    enabled: !!data,
    queryFn: async () => (await api.get<Planejamento>(`/planejamentos/${data!.simulacao.planejamento_id}`)).data,
  });
  const aprovar = useMutation({
    mutationFn: () => api.post(`/simulacoes/${id}/aprovar`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["simulacao", id] }),
    onError: (e) => setErro(mensagemErro(e)),
  });

  const [gerando, setGerando] = useState(false);

  async function baixar(rota: "excel" | "apresentacao", padrao: string) {
    setGerando(true);
    try {
      const r = await api.get(`/simulacoes/${id}/${rota}`, { responseType: "blob" });
      const nome = /filename="(.+)"/.exec(r.headers["content-disposition"] ?? "")?.[1] ?? padrao;
      const url = URL.createObjectURL(r.data);
      Object.assign(document.createElement("a"), { href: url, download: nome }).click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErro(mensagemErro(e));
    } finally {
      setGerando(false);
    }
  }

  if (!data) return <p>Carregando…</p>;
  const { simulacao: s, resultado: r } = data;
  const receita = r.base.TOTAL.receita_liquida;
  const meses = Object.keys(r.base).length - 1;
  const atual = planejamento?.regime_tributario;
  const totais = Object.fromEntries(r.comparativo.map((c) => [c.regime, c.total]));
  const economiaAnual = atual && totais[atual] != null ? ((totais[atual] - totais[r.melhor_regime]) * 12) / meses : 0;

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <BotaoLink to={`/planejamentos/${s.planejamento_id}?aba=simulacoes`} variante="linha">
          Voltar ao planejamento
        </BotaoLink>
        <span className="text-text-muted">
          {planejamento?.razao_social}, simulação {s.versao}
        </span>
        <Badge status={s.tipo} />
        {contador && (
          <div className="ml-auto flex gap-2">
            <Botao variante="secundario" disabled={gerando} onClick={() => baixar("excel", "planejamento.xlsx")}>
              Exportar Excel
            </Botao>
            <Botao variante="secundario" disabled={gerando} onClick={() => baixar("apresentacao", "apresentacao.pptx")}>
              Apresentação para o cliente
            </Botao>
            <Botao variante="secundario" onClick={() => setRelatorio(!relatorio)} aria-expanded={relatorio}>
              Relatório PDF
            </Botao>
            <Botao onClick={() => aprovar.mutate()} disabled={!!s.aprovada_em || s.desatualizada || s.tipo !== "FINAL"}>
              {s.aprovada_em ? "Aprovada" : "Aprovar simulação"}
            </Botao>
          </div>
        )}
      </div>
      <Erro mensagem={erro} />
      {contador && relatorio && <PainelRelatorio sid={s.id} pid={s.planejamento_id} preliminar={s.tipo !== "FINAL" || s.desatualizada || !s.aprovada_em} />}
      {(s.pendencias || s.desatualizada) && (
        <div className="rounded border border-warning bg-warning-soft px-3 py-2 text-sm text-warning-ink">
          <strong>Simulação preliminar.</strong> Aprove só depois de resolver:
          <ul className="ml-5 list-disc">
            {s.desatualizada && <li>os dados mudaram depois desta simulação; gere uma nova</li>}
            {s.pendencias?.split("\n").map((x) => <li key={x}>{x}</li>)}
          </ul>
        </div>
      )}

      <section aria-labelledby="veredito" className="rounded-md border border-surface bg-white px-5 pb-5 pt-6 md:px-8">
        <h1 id="veredito" className="expandido max-w-[26ch] text-balance text-[1.9rem] md:text-[2.4rem] font-semibold leading-[1.1] tracking-tight">
          {atual === r.melhor_regime ? `${REGIMES[r.melhor_regime]} continua com a menor carga` : `${REGIMES[r.melhor_regime]} tem a menor carga`}
        </h1>
        <p className="mt-3 max-w-[64ch] text-[1.07rem] text-text-muted">
          {atual && atual !== r.melhor_regime ? (
            <>
              Economia estimada de <strong className="font-semibold text-success-ink">{brl(economiaAnual)} por ano</strong> em relação ao{" "}
              {REGIMES[atual]}, regime atual da empresa. Base: {brl(receita)} de receita líquida em {meses} meses.
            </>
          ) : (
            <>Mudar de regime não reduziria a carga neste período. Base: {brl(receita)} de receita líquida em {meses} meses.</>
          )}
        </p>
        <p className="mt-2 max-w-[64ch] text-sm text-text-muted">{enquadramentoSimples(r.simples, receita)}</p>
        <Composicao r={r} receita={receita} atual={atual} />
      </section>

      <Card titulo="Base da operação">
        <Tabela cabecalho={["Item", ...Object.keys(r.base).map((c) => (c === "TOTAL" ? "Período" : competenciaExtenso(c)))]} numericas={Object.keys(r.base).map((_, i) => i + 1)}>
          {[
            ["receita_bruta", "Faturamento bruto"],
            ["devolucoes", "(−) Devoluções"],
            ["receita_liquida", "(=) Receita líquida"],
            ["receita_monofasica", "Receita monofásica"],
            ["receita_interna", "Vendas internas"],
            ["receita_interestadual", "Vendas interestaduais"],
            ["compras", "Compras"],
            ["despesas", "Despesas"],
          ].map(([k, rot]) => (
            <tr key={k}>
              <td className="px-2 py-1">{rot}</td>
              {Object.keys(r.base).map((c) => (
                <td key={c} className="num px-2 py-1">
                  {brl(r.base[c][k])}
                </td>
              ))}
            </tr>
          ))}
        </Tabela>
      </Card>

      <div className="grid gap-3 lg:grid-cols-3">
        {[r.simples, r.presumido, r.real].map((reg) => (
          <DetalheRegime key={reg.regime} reg={reg} receita={receita} />
        ))}
      </div>

      <Card titulo="Reforma Tributária – carga por ano (mesma base do período)">
        <div className="h-72">
          <ResponsiveContainer>
            <LineChart data={r.reforma.map((a) => ({ ano: a.ano, ...a.cargas }))}>
              <CartesianGrid stroke="var(--color-surface)" />
              <XAxis dataKey="ano" />
              <YAxis tickFormatter={(v) => `${Math.round(v / 1000)} mil`} width={70} />
              <Tooltip formatter={(v: number, n: string) => [brl(v), REGIMES[n]]} />
              <Legend formatter={(n: string) => REGIMES[n]} />
              {Object.keys(CORES).map((k) => (
                <Line key={k} dataKey={k} stroke={CORES[k]} strokeWidth={2} dot />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <Tabela cabecalho={["Ano", "CBS", "IBS", "ICMS mantido", ...Object.values(REGIMES), "Menor carga"]} numericas={[1, 2, 3, 4, 5, 6]}>
          {r.reforma.map((a) => (
            <tr key={a.ano}>
              <td className="px-2 py-1">{a.ano}</td>
              <td className="num px-2 py-1">{percentual(a.cbs)}</td>
              <td className="num px-2 py-1">{percentual(a.ibs)}</td>
              <td className="num px-2 py-1">{percentual(a.fator_icms)}</td>
              {Object.keys(REGIMES).map((k) => (
                <td key={k} className={`num px-2 py-1 ${a.melhor === k ? "font-semibold" : ""}`}>
                  {brl(a.cargas[k])}
                </td>
              ))}
              <td className="px-2 py-1">{REGIMES[a.melhor]}</td>
            </tr>
          ))}
        </Tabela>
      </Card>

      <Oportunidades r={r} sid={Number(id)} contador={contador} />

      {r.verificacao_ncm && r.verificacao_ncm.length > 0 && <VerificacaoNcm linhas={r.verificacao_ncm} receita={receita} />}

      <div className="grid gap-3 lg:grid-cols-2">
        <Card titulo="Simulação de crescimento (RBT12)">
          <Tabela cabecalho={["Receita de 12 meses", "Simples", "Presumido", "Real", "Menor carga"]} numericas={[0, 1, 2, 3]}>
            {r.crescimento.map((l) => (
              <tr key={l.rbt12} title={l.observacao}>
                <td className="num px-2 py-1">{brl(l.rbt12)}</td>
                <td className="num px-2 py-1">{l.aliquota_simples == null ? "inelegível" : percentual(l.aliquota_simples)}</td>
                <td className="num px-2 py-1">{percentual(l.aliquota_lp)}</td>
                <td className="num px-2 py-1">{percentual(l.aliquota_lr)}</td>
                <td className="px-2 py-1">{REGIMES[l.melhor]}</td>
              </tr>
            ))}
          </Tabela>
          {r.margem_equilibrio_lr_lp != null && (
            <p className="mt-2 text-sm">
              Margem de equilíbrio LR × LP: <strong>{percentual(r.margem_equilibrio_lr_lp)}</strong> de LAIR sobre a receita (atual{" "}
              {percentual(r.real.detalhes.margem_lair)}). Abaixo dela o Lucro Real fica mais barato.
            </p>
          )}
        </Card>
        <Card titulo="Pontos críticos e premissas a validar">
          <ul className="space-y-1 text-sm">
            {r.pontos_criticos.map((p) => (
              <li key={p.codigo}>⚠ {p.texto}</li>
            ))}
          </ul>
        </Card>
      </div>

      <MemoriaCalculo sid={Number(id)} />
    </>
  );
}

const ANEXOS: Record<number, string> = { 1: "Anexo I (comércio)", 2: "Anexo II (indústria)" };
const anexoSimples = (s: ResultadoRegime) => ANEXOS[s.detalhes.anexo ?? 1] ?? `Anexo ${s.detalhes.anexo}`;

/** Onde a empresa se encaixa no Simples: anexo, faixa do RBT12 e alíquota efetiva do DAS. */
function enquadramentoSimples(s: ResultadoRegime, receita: number) {
  const d = s.detalhes;
  const faixa = `${d.faixa}ª faixa`;
  const rbt12 = `RBT12 de ${brl(d.rbt12)}${d.rbt12_estimado ? ", estimado pela média do período" : ""}`;
  if (!s.elegivel) return `No Simples: acima do teto de R$ 4,8 milhões (${rbt12}), a empresa não pode optar.`;
  const sublimite = d.acima_sublimite ? "; acima do sublimite, o ICMS é pago fora do DAS" : "";
  // o monofásico e a ST saem do DAS: a carga sobre a receita fica abaixo da alíquota da tabela
  const segregacao = !d.acima_sublimite && s.total < receita * d.aliquota_efetiva_das - 0.01 ? "; a carga fica menor porque o monofásico e a ST saem do DAS" : "";
  return `No Simples: ${anexoSimples(s)}, ${faixa} (${rbt12}), alíquota efetiva de ${percentual(d.aliquota_efetiva_das)} no DAS${sublimite}${segregacao}.`;
}

function DetalheRegime({ reg, receita }: { reg: ResultadoRegime; receita: number }) {
  const linhas = reg.tributos.filter((t) => t.competencia == null && t.valor !== 0);
  const d = reg.detalhes;
  return (
    <Card titulo={REGIMES[reg.regime]}>
      {reg.regime === "SIMPLES_NACIONAL" && (
        <div className="mb-3">
          <dl className="grid grid-cols-2 overflow-hidden rounded-md border-t border-l border-border text-sm">
            {[
              ["Anexo", anexoSimples(reg)],
              ["Faixa", `${d.faixa}ª`],
              [d.rbt12_estimado ? "RBT12 (estimado)" : "RBT12", brl(d.rbt12)],
              ["Alíquota nominal", percentual(d.aliquota_nominal)],
              ["Parcela a deduzir", brl(d.parcela_deduzir)],
              ["Alíquota efetiva", percentual(d.aliquota_efetiva_das)],
            ].map(([rotulo, valor]) => (
              <div key={rotulo} className="border-r border-b border-border px-2.5 py-1">
                <dt className="text-xs text-text-muted">{rotulo}</dt>
                <dd className="num font-medium">{valor}</dd>
              </div>
            ))}
          </dl>
          {(!reg.elegivel || d.acima_sublimite > 0) && (
            <p className="mt-1.5 text-xs text-warning-ink">
              {!reg.elegivel ? "RBT12 acima do teto de R$ 4,8 milhões: a empresa não pode optar pelo Simples." : "RBT12 acima do sublimite de R$ 3,6 milhões: o ICMS é pago fora do DAS."}
            </p>
          )}
        </div>
      )}
      <Tabela cabecalho={["Tributo", "Valor", "% da receita"]} numericas={[1, 2]}>
        {linhas.map((t) => (
          <tr key={t.tributo}>
            <td className="px-2 py-1">{t.tributo}</td>
            <td className="num px-2 py-1">{brl(t.valor)}</td>
            <td className="num px-2 py-1">{percentual(t.valor / receita)}</td>
          </tr>
        ))}
        <tr className="font-semibold">
          <td className="px-2 py-1">Total</td>
          <td className="num px-2 py-1">{brl(reg.total)}</td>
          <td className="num px-2 py-1">{percentual(reg.total / receita)}</td>
        </tr>
      </Tabela>
    </Card>
  );
}

function Oportunidades({ r, sid, contador }: { r: TResultado; sid: number; contador: boolean }) {
  const qc = useQueryClient();
  const mudar = useMutation({
    mutationFn: ({ id, situacao }: { id: number; situacao: string }) => api.patch(`/oportunidades/${id}`, { situacao }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["simulacao", String(sid)] }),
  });
  return (
    <Card titulo="Oportunidades identificadas">
      <Tabela cabecalho={["Oportunidade", "Impacto no período", "Prioridade", "O que fazer", "Situação"]} numericas={[1]}>
        {r.oportunidades.map((o) => (
          <tr key={o.id} className={o.situacao === "DESCARTADA" ? "opacity-50" : ""}>
            <td className="px-2 py-1.5 font-medium">{o.titulo}</td>
            <td className="num px-2 py-1.5">{o.impacto == null ? "qualitativo" : brl(o.impacto)}</td>
            <td className="px-2 py-1.5">{o.prioridade === "ALTA" ? "▲ Alta" : o.prioridade === "MEDIA" ? "■ Média" : "▼ Baixa"}</td>
            <td className="px-2 py-1.5 text-xs">{o.acao}</td>
            <td className="px-2 py-1.5">
              {contador ? (
                <select className="rounded border border-surface text-xs" value={o.situacao} onChange={(e) => mudar.mutate({ id: o.id, situacao: e.target.value })}>
                  <option value="ABERTA">Aberta</option>
                  <option value="CONFIRMADA">Confirmada</option>
                  <option value="DESCARTADA">Descartada</option>
                </select>
              ) : (
                o.situacao
              )}
            </td>
          </tr>
        ))}
      </Tabela>
    </Card>
  );
}

function MemoriaCalculo({ sid }: { sid: number }) {
  const [aberta, setAberta] = useState(false);
  const { data = [] } = useQuery({
    queryKey: ["memoria", sid],
    enabled: aberta,
    queryFn: async () => (await api.get<PassoMemoria[]>(`/simulacoes/${sid}/memoria`)).data,
  });
  return (
    <Card titulo="Memória de cálculo" acoes={<Botao variante="secundario" onClick={() => setAberta(!aberta)}>{aberta ? "Ocultar" : "Mostrar"}</Botao>}>
      {aberta && (
        <Tabela cabecalho={["Seção", "Competência", "Etapa", "Fórmula", "Resultado", "Fundamento"]}>
          {data.map((p, i) => (
            <tr key={i}>
              <td className="px-2 py-1">{p.secao}</td>
              <td className="px-2 py-1">{p.competencia ?? "período"}</td>
              <td className="px-2 py-1">{p.descricao}</td>
              <td className="px-2 py-1 text-xs">{p.formula}</td>
              <td className="num px-2 py-1">{Math.abs(p.valor) < 1 && p.valor !== 0 ? percentual(p.valor) : brl(p.valor)}</td>
              <td className="px-2 py-1 text-xs">{p.fundamento ?? ""}</td>
            </tr>
          ))}
        </Tabela>
      )}
    </Card>
  );
}

const GRUPOS = [
  { nome: "ICMS", tributos: ["ICMS", "IPI"], cor: "bg-t-icms" },  // IPI só no DAS da indústria (Anexo II)
  { nome: "PIS e COFINS", tributos: ["PIS", "COFINS", "PIS/COFINS"], cor: "bg-t-piscofins" },
  { nome: "IRPJ e CSLL", tributos: ["IRPJ", "CSLL"], cor: "bg-t-irpjcsll" },
  { nome: "CPP e INSS", tributos: ["CPP", "INSS patronal"], cor: "bg-t-cpp" },
];

/** Composição da carga de cada regime por grupo de tributo, na mesma escala, para mostrar de onde vem a diferença. */
function Composicao({ r, receita, atual }: { r: TResultado; receita: number; atual?: string }) {
  const regimes = r.comparativo.slice().sort((a, b) => a.posicao - b.posicao);
  const maior = Math.max(...regimes.map((c) => c.total));
  const detalhe: Record<string, ResultadoRegime> = { SIMPLES_NACIONAL: r.simples, LUCRO_PRESUMIDO: r.presumido, LUCRO_REAL: r.real };
  const valorGrupo = (reg: ResultadoRegime, tributos: string[]) =>
    reg.tributos.filter((t) => t.competencia == null && tributos.includes(t.tributo)).reduce((s, t) => s + t.valor, 0);

  const acimaDaReceita = regimes.filter((c) => c.aliquota_efetiva > 1);

  return (
    <div className="mt-7">
      {acimaDaReceita.length > 0 && (
        <p className="mb-4 rounded border border-warning bg-warning-soft px-3 py-2 text-sm text-warning-ink">
          A carga do {acimaDaReceita.map((c) => REGIMES[c.regime]).join(" e do ")} passa de 100% da receita líquida ({brl(receita)}). Isso costuma
          indicar faturamento incompleto ou folha, compras e despesas fora de escala: confira os dados antes de usar este resultado.
        </p>
      )}
      <div className="space-y-4">
        {regimes.map((c) => {
          const melhor = c.regime === r.melhor_regime;
          return (
            <div key={c.regime} className="grid gap-x-4 gap-y-1 md:grid-cols-[11rem_minmax(0,1fr)_auto] md:items-center">
              <div className="font-medium">
                {REGIMES[c.regime]}
                {c.regime === atual && <span className="ml-1.5 text-sm font-normal text-text-muted">(atual)</span>}
              </div>
              <div
                className="flex h-7 overflow-hidden rounded-sm"
                role="img"
                aria-label={`${REGIMES[c.regime]}: ${GRUPOS.map((g) => `${g.nome} ${brl(valorGrupo(detalhe[c.regime], g.tributos))}`).join(", ")}`}
              >
                {/* largura mínima: um regime muito mais barato não pode sumir da comparação */}
                <div className="barra-carga flex h-full min-w-1.5" style={{ width: `${maior > 0 ? (c.total / maior) * 100 : 0}%` }}>
                  {GRUPOS.map((g) => {
                    const v = valorGrupo(detalhe[c.regime], g.tributos);
                    // fatia estreita sem divisória: a borda branca de 1px apagaria a cor
                    const divisoria = maior > 0 && v / maior >= 0.03 ? "border-r border-white last:border-0" : "";
                    return v > 0 ? <div key={g.nome} className={`${g.cor} h-full ${divisoria}`} style={{ width: `${(v / c.total) * 100}%` }} title={`${g.nome}: ${brl(v)}`} /> : null;
                  })}
                </div>
              </div>
              <div className="grid grid-cols-[7.5rem_5.5rem_7.5rem] items-baseline gap-x-3 whitespace-nowrap md:pl-1">
                <span className={`num text-[1.07rem] font-semibold ${melhor ? "text-success-ink" : ""}`}>{brl(c.total)}</span>
                <span className="num text-sm text-text-muted">{percentual(c.aliquota_efetiva)}</span>
                <span className="num text-sm">{melhor ? <span className="font-medium text-success-ink">menor carga</span> : `+ ${brl(c.diferenca_melhor)}`}</span>
              </div>
            </div>
          );
        })}
      </div>
      <ul className="mt-5 flex flex-wrap gap-x-5 gap-y-1 text-sm text-text-muted">
        {GRUPOS.map((g) => (
          <li key={g.nome} className="flex items-center gap-1.5">
            <span aria-hidden className={`inline-block h-2.5 w-2.5 rounded-sm ${g.cor}`} />
            {g.nome === "ICMS" && r.simples.tributos.some((t) => t.tributo === "IPI") ? "ICMS e IPI" : g.nome}
          </li>
        ))}
        <li>Percentuais sobre a receita líquida de {brl(receita)}</li>
      </ul>
    </div>
  );
}

type Relatorio = { id: number; arquivo: string; preliminar: boolean; gerado_em: string; gerado_por_nome: string; simulacao_id: number };

/** Revisão do texto da recomendação, emissão do PDF e lista dos relatórios já arquivados. */
function PainelRelatorio({ sid, pid, preliminar }: { sid: number; pid: number; preliminar: boolean }) {
  const qc = useQueryClient();
  const [texto, setTexto] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const { data: base } = useQuery({
    queryKey: ["recomendacao", sid],
    queryFn: async () => (await api.get<string[]>(`/simulacoes/${sid}/recomendacao`)).data,
  });
  const { data: emitidos = [] } = useQuery({
    queryKey: ["relatorios", pid],
    queryFn: async () => (await api.get<Relatorio[]>(`/planejamentos/${pid}/relatorios`)).data,
  });
  const valor = texto ?? (base ?? []).join("\n\n");
  const gerar = useMutation({
    mutationFn: async () => {
      const itens = valor.split(/\n\s*\n/).map((x) => x.replace(/\s+/g, " ").trim()).filter(Boolean);
      return (await api.post<Relatorio>(`/simulacoes/${sid}/relatorio-pdf`, { recomendacao: itens })).data;
    },
    onSuccess: async (rel) => {
      setErro(null);
      qc.invalidateQueries({ queryKey: ["relatorios", pid] });
      await baixarArquivo(`/relatorios/${rel.id}/download`, rel.arquivo);
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  return (
    <Card titulo="Relatório para o cliente">
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-3">
          <label className="block text-sm font-medium" htmlFor="recomendacao">
            Recomendação e próximos passos
          </label>
          <p className="text-sm text-text-muted">Texto-base gerado a partir do resultado. Edite à vontade; cada parágrafo vira um item numerado.</p>
          <textarea
            id="recomendacao"
            rows={9}
            className="w-full rounded border border-border bg-white px-3 py-2 text-sm leading-relaxed"
            value={valor}
            onChange={(e) => setTexto(e.target.value)}
          />
          {preliminar && (
            <p className="text-sm text-warning-ink">Esta simulação ainda não foi aprovada: o PDF sai com a marca PRELIMINAR.</p>
          )}
          <Erro mensagem={erro} />
          <div className="flex gap-2">
            <Botao onClick={() => gerar.mutate()} disabled={gerar.isPending || !base}>
              {gerar.isPending ? "Gerando…" : "Gerar e baixar PDF"}
            </Botao>
            {texto !== null && (
              <Botao variante="secundario" onClick={() => setTexto(null)}>
                Voltar ao texto-base
              </Botao>
            )}
          </div>
        </div>
        <div>
          <h3 className="mb-2 text-sm font-medium">Relatórios emitidos</h3>
          {emitidos.length === 0 ? (
            <p className="text-sm text-text-muted">Nenhum relatório emitido para este planejamento.</p>
          ) : (
            <ul className="divide-y divide-surface text-sm">
              {emitidos.map((r) => (
                <li key={r.id} className="py-2">
                  <div className="flex items-center justify-between gap-3">
                    <span>
                      {dataHora(r.gerado_em)}
                      <span className="block text-text-muted">
                        {r.gerado_por_nome}, simulação {r.simulacao_id}
                        {r.preliminar ? ", preliminar" : ""}
                      </span>
                    </span>
                    <Botao variante="linha" onClick={() => baixarArquivo(`/relatorios/${r.id}/download`, r.arquivo).catch((e) => setErro(mensagemErro(e)))}>
                      Baixar PDF
                    </Botao>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Card>
  );
}

const ncmFmt = (n: string) => (n.length === 8 ? `${n.slice(0, 4)}.${n.slice(4, 6)}.${n.slice(6)}` : n);

/** Receita por NCM com a classificação tributária e a ação a tomar no cadastro de cada produto. */
function VerificacaoNcm({ linhas, receita }: { linhas: LinhaNcm[]; receita: number }) {
  const [soRevisar, setSoRevisar] = useState(false);
  const revisar = linhas.filter((l) => l.requer_revisao);
  const somaRevisar = revisar.reduce((s, l) => s + l.receita, 0);
  const indicio = linhas.filter((l) => l.indicio_ncm_incorreto).map((l) => ncmFmt(l.ncm));
  const ibs = new Set(linhas.map((l) => `${l.cst_ibs_cbs}/${l.cclass_trib}`));
  const beneficio = new Set(linhas.map((l) => l.beneficio_reforma));
  const visiveis = soRevisar ? revisar : linhas;

  return (
    <Card
      titulo="Verificação por NCM"
      semPadding
      acoes={
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={soRevisar} onChange={(e) => setSoRevisar(e.target.checked)} />
          Só os que precisam de revisão
        </label>
      }
    >
      <ul className="max-w-[90ch] list-disc space-y-1 px-8 py-3 text-sm">
        {revisar.length > 0 && (
          <li>
            <strong className="font-semibold">
              {revisar.length} de {linhas.length} NCMs precisam de revisão
            </strong>{" "}
            no cadastro dos produtos, somando {brl(somaRevisar)} ({percentual(somaRevisar / receita)} da receita).
          </li>
        )}
        {indicio.length > 0 && <li>Com indício de NCM incorreto que, se reclassificados, passam a monofásicos: {indicio.join(", ")}.</li>}
        {linhas.every((l) => l.sujeito_st) && <li>ICMS: todos estavam sujeitos à substituição tributária; validar o CEST no cadastro.</li>}
        {ibs.size === 1 && linhas[0].cst_ibs_cbs && (
          <li>
            IBS/CBS: CST {linhas[0].cst_ibs_cbs} e cClassTrib {linhas[0].cclass_trib} para todos os NCMs
            {beneficio.size === 1 && linhas[0].beneficio_reforma
              ? linhas[0].beneficio_reforma.startsWith("Não")
                ? ", sem benefício na Reforma (alíquota padrão)."
                : `, com benefício na Reforma: ${linhas[0].beneficio_reforma}.`
              : "."}
          </li>
        )}
      </ul>
      <Tabela cabecalho={["NCM", "Produto de exemplo", "Receita", "% receita", "PIS/COFINS", "Confiança", "Ação recomendada"]} numericas={[2, 3]}>
        {visiveis.map((l) => (
          <tr key={l.ncm} className={l.requer_revisao ? "bg-warning-soft/60" : ""}>
            <td className="whitespace-nowrap px-4 py-2 font-medium">{ncmFmt(l.ncm)}</td>
            <td className="px-2 py-2">{l.produto_exemplo ?? "–"}</td>
            <td className="num px-2 py-2">{brl(l.receita)}</td>
            <td className="num px-2 py-2">{percentual(l.participacao)}</td>
            <td className="px-2 py-2">{l.monofasico ? "Monofásico" : "Tributado"}</td>
            <td className="px-2 py-2">{l.confianca === "MEDIA" ? "Média" : l.confianca === "ALTA" ? "Alta" : "–"}</td>
            <td className="px-2 py-2">
              {l.requer_revisao && (
                <span className="mr-1.5 inline-flex rounded-full bg-warning-soft px-2 text-xs font-medium text-warning-ink ring-1 ring-warning/40">! Revisar</span>
              )}
              {l.acao_recomendada ?? "–"}
            </td>
          </tr>
        ))}
      </Tabela>
    </Card>
  );
}
