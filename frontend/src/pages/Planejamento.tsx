import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import type { Bloco, Catalogo, Planejamento as TPlanejamento, SimulacaoResumo } from "../api/tipos";
import { Badge, BarraProgresso, Botao, Cabecalho, CampoMoeda, Card, Erro, Ficha, Tabela } from "../components/ui";
import { brl, competenciaExtenso, dataHora, formatarCnpj, REGIMES } from "../lib/formato";

const ABAS = [
  { id: "coleta", rotulo: "Faturamento, compras e folha" },
  { id: "despesas", rotulo: "Despesas" },
  { id: "pendencias", rotulo: "Pendências" },
  { id: "simulacoes", rotulo: "Simulações" },
];

export function Planejamento() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const aba = params.get("aba") ?? "coleta";
  const { data: p } = useQuery({
    queryKey: ["planejamento", id],
    queryFn: async () => (await api.get<TPlanejamento>(`/planejamentos/${id}`)).data,
  });
  if (!p) return <p>Carregando…</p>;

  return (
    <>
      <Cabecalho titulo={p.razao_social}>
        <Ficha
          campos={[
            { rotulo: "CNPJ", valor: formatarCnpj(p.cnpj) },
            { rotulo: "Regime atual", valor: REGIMES[p.regime_tributario] },
            { rotulo: "Período", valor: `${competenciaExtenso(p.competencia_inicial)} a ${competenciaExtenso(p.competencia_final)}`, largo: true },
            { rotulo: "Dados coletados", valor: <BarraProgresso valor={p.progresso} /> },
            { rotulo: "Situação", valor: <Badge status={p.status} /> },
          ]}
        />
      </Cabecalho>
      <nav className="flex gap-1 overflow-x-auto overflow-y-hidden border-b border-border" role="tablist">
        {ABAS.map((a) => (
          <button
            key={a.id}
            role="tab"
            aria-selected={aba === a.id}
            onClick={() => setParams({ aba: a.id })}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm ${aba === a.id ? "border-brand font-medium text-brand" : "border-transparent text-text-muted hover:text-text"}`}
          >
            {a.rotulo}
          </button>
        ))}
      </nav>
      {aba === "coleta" && <Coleta pid={p.id} />}
      {aba === "despesas" && <Despesas pid={p.id} />}
      {aba === "pendencias" && <Pendencias pid={p.id} />}
      {aba === "simulacoes" && <Simulacoes pid={p.id} />}
    </>
  );
}

type ColetaDados = {
  competencias: string[];
  compras: Record<string, number>;
  devolucoes: Record<string, number>;
  folha: Record<string, { folha: number | null; pro_labore: number | null }>;
  saidas: { competencia: string; notas: number; itens: number; valor: number }[];
};

function useAtualizar(pid: number) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["coleta", pid] });
    qc.invalidateQueries({ queryKey: ["planejamento", String(pid)] });
    qc.invalidateQueries({ queryKey: ["progresso", pid] });
  };
}

function Coleta({ pid }: { pid: number }) {
  const atualizar = useAtualizar(pid);
  const [erro, setErro] = useState<string | null>(null);
  const [log, setLog] = useState<string | null>(null);
  const [relatorios, setRelatorios] = useState<ResumoRelatorio[] | null>(null);
  const { data } = useQuery({
    queryKey: ["coleta", pid],
    queryFn: async () => (await api.get<ColetaDados>(`/planejamentos/${pid}/coleta`)).data,
  });

  const gravar = useMutation({
    mutationFn: ({ rota, corpo }: { rota: string; corpo: unknown }) => api.put(`/planejamentos/${pid}/${rota}`, corpo),
    onSuccess: () => {
      setErro(null);
      atualizar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  const importar = useMutation({
    mutationFn: (f: File) => {
      const fd = new FormData();
      fd.append("arquivo", f);
      return api.post(`/planejamentos/${pid}/nfe`, fd);
    },
    onSuccess: (r) => {
      setLog(`${r.data.lidos} notas lidas: ${r.data.importados} importadas e ${r.data.ignorados} ignoradas.`);
      atualizar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  const importarRelatorio = useMutation({
    mutationFn: async (arquivos: File[]) => {
      const resumos: ResumoRelatorio[] = [];
      for (const f of arquivos) {
        const fd = new FormData();
        fd.append("arquivo", f);
        resumos.push({ ...(await api.post<ResumoRelatorio>(`/planejamentos/${pid}/relatorio-contabil`, fd)).data, arquivo: f.name });
      }
      return resumos;
    },
    onSuccess: (resumos) => {
      setErro(null);
      setLog(null);
      setRelatorios(resumos);
      atualizar();
    },
    onError: (e) => {
      setErro(mensagemErro(e));
      atualizar();
    },
  });

  if (!data) return <p>Carregando…</p>;
  const mensal = (rota: string, c: string, v: number | null) => v != null && gravar.mutate({ rota, corpo: [{ competencia: c, valor: v }] });

  return (
    <div className="space-y-4">
      <Erro mensagem={erro} />
      <Card
        titulo="Notas fiscais de saída"
        acoes={
          <div className="flex flex-wrap gap-2">
            <label className="cursor-pointer rounded border border-border bg-white px-3 py-1.5 text-sm font-medium text-brand hover:border-brand hover:bg-highlight">
              {importarRelatorio.isPending ? "Importando relatório…" : "Importar relatório do Domínio"}
              <input
                type="file"
                multiple
                accept=".xls,.xlsx"
                className="hidden"
                disabled={importarRelatorio.isPending}
                onChange={(e) => {
                  const arquivos = Array.from(e.target.files ?? []);
                  e.target.value = "";
                  if (arquivos.length) importarRelatorio.mutate(arquivos);
                }}
              />
            </label>
            <label className="cursor-pointer rounded border border-border bg-white px-3 py-1.5 text-sm font-medium text-brand hover:border-brand hover:bg-highlight">
              Importar XML ou .zip
              <input type="file" accept=".xml,.zip" className="hidden" onChange={(e) => e.target.files?.[0] && importar.mutate(e.target.files[0])} />
            </label>
          </div>
        }
      >
        <p className="mb-3 max-w-[80ch] text-sm text-text-muted">
          O relatório é o "Movimentação de Produtos – ICMS – PIS – COFINS" do Domínio, em .xls. Pode enviar os de saídas e de entradas
          de vários meses de uma vez; o de entradas preenche as devoluções de venda.
        </p>
        {log && <p className="mb-2 text-sm">{log}</p>}
        {relatorios && <ResumoImportacao resumos={relatorios} fechar={() => setRelatorios(null)} />}
        <Tabela cabecalho={["Competência", "Notas", "Itens", "Valor total"]} numericas={[1, 2, 3]}>
          {data.competencias.map((c) => {
            const s = data.saidas.find((x) => x.competencia === c);
            return (
              <tr key={c}>
                <td className="px-2 py-1.5">{competenciaExtenso(c)}</td>
                <td className="num px-2 py-1.5">{s?.notas ?? <span className="text-alert">pendente</span>}</td>
                <td className="num px-2 py-1.5">{s?.itens ?? "—"}</td>
                <td className="num px-2 py-1.5">{brl(s?.valor)}</td>
              </tr>
            );
          })}
        </Tabela>
      </Card>
      <Card titulo="Compras, devoluções, folha e pró-labore">
        <Tabela cabecalho={["Competência", "Compras", "Devoluções", "Folha", "Pró-labore"]} numericas={[1, 2, 3, 4]}>
          {data.competencias.map((c) => (
            <tr key={c}>
              <td className="px-2 py-1.5">{competenciaExtenso(c)}</td>
              <td className="px-2 py-1 text-right">
                <CampoMoeda rotulo={`Compras ${c}`} valor={data.compras[c]} onChange={(v) => mensal("compras", c, v)} />
              </td>
              <td className="px-2 py-1 text-right">
                <CampoMoeda rotulo={`Devoluções ${c}`} valor={data.devolucoes[c]} onChange={(v) => mensal("devolucoes", c, v)} />
              </td>
              {(["folha", "pro_labore"] as const).map((campo) => (
                <td key={campo} className="px-2 py-1 text-right">
                  <CampoMoeda
                    rotulo={`${campo} ${c}`}
                    valor={data.folha[c]?.[campo]}
                    onChange={(v) =>
                      gravar.mutate({ rota: "folha", corpo: [{ competencia: c, ...data.folha[c], [campo]: v }] })
                    }
                  />
                </td>
              ))}
            </tr>
          ))}
        </Tabela>
      </Card>
    </div>
  );
}

type LevantamentoDados = { status: string | null; itens: Record<string, number> };

function Despesas({ pid }: { pid: number }) {
  const atualizar = useAtualizar(pid);
  const { data: coleta } = useQuery({
    queryKey: ["coleta", pid],
    queryFn: async () => (await api.get<ColetaDados>(`/planejamentos/${pid}/coleta`)).data,
  });
  const comps = coleta?.competencias ?? [];
  const [comp, setComp] = useState<string | null>(null);
  const atual = comp ?? comps[0];
  const { data: catalogo = [] } = useQuery({
    queryKey: ["catalogo"],
    queryFn: async () => (await api.get<Catalogo>("/tabelas/catalogo-despesas")).data,
  });
  const qc = useQueryClient();
  const { data: lev } = useQuery({
    queryKey: ["levantamento", pid, atual],
    enabled: !!atual,
    queryFn: async () => (await api.get<LevantamentoDados>(`/planejamentos/${pid}/levantamentos/${atual}`)).data,
  });
  const [erro, setErro] = useState<string | null>(null);
  const gravar = useMutation({
    mutationFn: (item: { item_despesa_id: number; valor: number | null }) =>
      api.put(`/planejamentos/${pid}/levantamentos/${atual}`, { itens: [item] }),
    onSuccess: () => {
      setErro(null);
      qc.invalidateQueries({ queryKey: ["levantamento", pid, atual] });
      atualizar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  if (!atual || !lev) return <p>Carregando…</p>;
  const valor = (id: number) => lev.itens[String(id)];
  const total = catalogo.reduce((s, g) => s + g.itens.filter((i) => i.ativo).reduce((t, i) => t + (valor(i.id) ?? 0), 0), 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        Competência:
        {comps.map((c) => (
          <button key={c} onClick={() => setComp(c)} className={`rounded px-2 py-1 ${c === atual ? "bg-brand-strong text-white" : "border border-surface"}`}>
            {competenciaExtenso(c)}
          </button>
        ))}
        <span className="ml-auto font-semibold">Total da competência: {brl(total)}</span>
      </div>
      <Erro mensagem={erro} />
      {catalogo.map((g) => {
        const subtotal = g.itens.filter((i) => i.ativo).reduce((t, i) => t + (valor(i.id) ?? 0), 0);
        return (
          <Card key={g.id} titulo={g.nome} acoes={<span className="num text-sm font-semibold">Subtotal {brl(subtotal)}</span>}>
            <div className="grid gap-x-6 gap-y-1 md:grid-cols-2">
              {g.itens.filter((i) => i.ativo).map((i) => (
                <label key={`${atual}-${i.id}`} className="flex items-center justify-between gap-2 border-b border-surface/50 py-1 text-sm">
                  <span>{i.nome}</span>
                  <CampoMoeda rotulo={i.nome} valor={valor(i.id)} onChange={(v) => gravar.mutate({ item_despesa_id: i.id, valor: v })} />
                </label>
              ))}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

function Pendencias({ pid }: { pid: number }) {
  const { data } = useQuery({
    queryKey: ["progresso", pid],
    queryFn: async () => (await api.get<{ progresso: number; blocos: Bloco[] }>(`/planejamentos/${pid}/progresso`)).data,
  });
  if (!data) return <p>Carregando…</p>;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {data.blocos.map((b) => (
        <Card key={b.codigo} titulo={`${b.nome} (peso ${b.peso}%)`} acoes={<span className="num text-sm">{b.preenchidos}/{b.esperados}</span>}>
          {b.pendencias.length === 0 ? (
            <p className="text-sm">✔ Completo</p>
          ) : (
            <ul className="max-h-48 space-y-0.5 overflow-auto text-sm">
              {b.pendencias.map((x, i) => (
                <li key={i}>
                  <span className="text-alert">●</span> {x.competencia ? `${competenciaExtenso(x.competencia)} — ` : ""}
                  {x.descricao}
                </li>
              ))}
            </ul>
          )}
        </Card>
      ))}
    </div>
  );
}

function Simulacoes({ pid }: { pid: number }) {
  const qc = useQueryClient();
  const [erro, setErro] = useState<string | null>(null);
  const { data = [] } = useQuery({
    queryKey: ["simulacoes", pid],
    queryFn: async () => (await api.get<SimulacaoResumo[]>(`/planejamentos/${pid}/simulacoes`)).data,
  });
  const executar = useMutation({
    mutationFn: () => api.post(`/planejamentos/${pid}/simulacoes`),
    onSuccess: () => {
      setErro(null);
      qc.invalidateQueries({ queryKey: ["simulacoes", pid] });
      qc.invalidateQueries({ queryKey: ["planejamento", String(pid)] });
    },
    onError: (e) => setErro(mensagemErro(e)),
  });
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";

  return (
    <Card titulo="Simulações" acoes={<Botao onClick={() => executar.mutate()} disabled={executar.isPending}>{executar.isPending ? "Calculando…" : "Nova simulação"}</Botao>}>
      <Erro mensagem={erro} />
      <Tabela cabecalho={["Versão", "Tipo", "Menor carga", "Calculada em", "Situação", ""]}>
        {data.map((s) => (
          <tr key={s.id}>
            <td className="px-2 py-1.5">v{s.versao}</td>
            <td className="px-2 py-1.5">
              <Badge status={s.tipo} />
            </td>
            <td className="px-2 py-1.5 font-medium">{REGIMES[s.regime_recomendado]}</td>
            <td className="px-2 py-1.5">{dataHora(s.executada_em)}</td>
            <td className="px-2 py-1.5">{s.desatualizada ? <span className="text-alert">⚠ desatualizada</span> : s.aprovada_em ? "✔ aprovada" : "atual"}</td>
            <td className="px-2 py-1.5">
              <Link className="text-brand underline underline-offset-2" to={`/simulacoes/${s.id}`}>
                Ver resultado
              </Link>
            </td>
          </tr>
        ))}
      </Tabela>
      {!contador && <p className="mt-2 text-xs">Aprovação, relatório e exportação ficam disponíveis para o contador.</p>}
    </Card>
  );
}

type ResumoRelatorio = {
  arquivo?: string;
  tipo: "SAIDA" | "ENTRADA";
  empresa_relatorio: string | null;
  linhas: number;
  notas_importadas: number;
  notas_ignoradas: number;
  valor_importado: number;
  avisos: string[];
};

function ResumoImportacao({ resumos, fechar }: { resumos: ResumoRelatorio[]; fechar: () => void }) {
  return (
    <div className="mb-4 rounded border border-border bg-bg p-3 text-sm" role="status">
      <div className="mb-2 flex items-center justify-between">
        <strong className="font-semibold">Importação concluída</strong>
        <button className="text-brand underline underline-offset-2" onClick={fechar}>
          Fechar
        </button>
      </div>
      <ul className="space-y-2">
        {resumos.map((r, i) => (
          <li key={i}>
            <div>
              {r.arquivo}: relatório de {r.tipo === "SAIDA" ? "saídas" : "entradas"}, {r.linhas} itens, {r.notas_importadas} notas importadas
              {r.notas_ignoradas > 0 && ` e ${r.notas_ignoradas} já existentes ignoradas`}, {brl(r.valor_importado)}.
            </div>
            {r.avisos.length > 0 && (
              <ul className="ml-5 mt-1 list-disc text-warning-ink">
                {r.avisos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
