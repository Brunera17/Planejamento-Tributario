import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import type { Bloco, Catalogo, Planejamento as TPlanejamento, SimulacaoResumo } from "../api/tipos";
import { Badge, BarraProgresso, Botao, BotaoLink, Cabecalho, CampoMoeda, Card, EnvioArquivo, Erro, Ficha, Modal, Obrigatorio, Tabela, useConfirmacao } from "../components/ui";
import { brl, competenciaExtenso, dataHora, editarMoeda, formatarCnpj, lerMoeda, REGIMES } from "../lib/formato";
import { Bens } from "./Bens";
import { Documentos } from "./Documentos";
import { Premissas } from "./Premissas";
import { Revisao } from "./Revisao";

const ABAS = [
  { id: "coleta", rotulo: "Faturamento, compras e folha" },
  { id: "despesas", rotulo: "Despesas" },
  { id: "bens", rotulo: "Bens" },
  { id: "documentos", rotulo: "Documentos" },
  { id: "premissas", rotulo: "Premissas" },
  { id: "revisao", rotulo: "Revisão de produtos" },
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
      <AcoesStatus p={p} />
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
      {aba === "bens" && <Bens pid={p.id} />}
      {aba === "documentos" && <Documentos pid={p.id} />}
      {aba === "premissas" && <Premissas pid={p.id} />}
      {aba === "revisao" && <Revisao pid={p.id} />}
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
  const [importando, setImportando] = useState(false);
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
      setRelatorios(null);
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
      {log && <p className="text-sm">{log}</p>}
      {relatorios && <ResumoImportacao resumos={relatorios} fechar={() => setRelatorios(null)} />}
      <Card
        titulo="Movimento mensal"
        acoes={
          <Botao variante="secundario" onClick={() => setImportando(true)}>
            Importar documentos
          </Botao>
        }
        semPadding
      >
        <Tabela cabecalho={["Competência", "Faturamento (notas de saída)", "Compras", "Devoluções", "Folha", "Pró-labore"]} numericas={[1, 2, 3, 4, 5]}>
          {data.competencias.map((c) => {
            const s = data.saidas.find((x) => x.competencia === c);
            return (
              <tr key={c}>
                <td className="px-4 py-1.5">{competenciaExtenso(c)}</td>
                <td className="num px-2 py-1.5">
                  {s ? (
                    <>
                      {brl(s.valor)}
                      <span className="block text-xs text-text-muted">
                        {s.notas} {s.notas === 1 ? "nota" : "notas"}
                      </span>
                    </>
                  ) : (
                    <span className="text-alert">pendente</span>
                  )}
                </td>
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
                      onChange={(v) => gravar.mutate({ rota: "folha", corpo: [{ competencia: c, ...data.folha[c], [campo]: v }] })}
                    />
                  </td>
                ))}
              </tr>
            );
          })}
        </Tabela>
      </Card>
      <ImportarDocumentos
        aberto={importando}
        fechar={() => setImportando(false)}
        enviando={importar.isPending || importarRelatorio.isPending}
        enviar={(tipo, arquivos) => {
          setImportando(false);
          if (tipo === "relatorio") importarRelatorio.mutate(arquivos);
          else arquivos.forEach((f) => importar.mutate(f));
        }}
      />
    </div>
  );
}

const TIPOS_IMPORTACAO = {
  relatorio: {
    nome: "Relatório do Domínio",
    detalhe: "Movimentação de Produtos – ICMS – PIS – COFINS. O de saídas preenche o faturamento; o de entradas, as devoluções. Pode enviar vários meses de uma vez.",
    formatos: [".xls", ".xlsx"],
  },
  xml: {
    nome: "XML de NF-e",
    detalhe: "Notas de saída avulsas ou num arquivo .zip. Preenchem o faturamento e a lista de produtos para revisão.",
    formatos: [".xml", ".zip"],
  },
};

function ImportarDocumentos({
  aberto,
  fechar,
  enviar,
  enviando,
}: {
  aberto: boolean;
  fechar: () => void;
  enviar: (tipo: keyof typeof TIPOS_IMPORTACAO, arquivos: File[]) => void;
  enviando: boolean;
}) {
  const [tipo, setTipo] = useState<keyof typeof TIPOS_IMPORTACAO>("relatorio");
  const [arquivos, setArquivos] = useState<File[]>([]);
  const t = TIPOS_IMPORTACAO[tipo];
  return (
    <Modal aberto={aberto} fechar={fechar} titulo="Importar documentos" descricao="Os valores lidos entram no movimento mensal; notas já importadas não são duplicadas.">
      <div className="space-y-4 text-sm">
        <fieldset className="grid gap-2 sm:grid-cols-2">
          <legend className="mb-1 font-medium">Tipo de documento</legend>
          {(Object.keys(TIPOS_IMPORTACAO) as (keyof typeof TIPOS_IMPORTACAO)[]).map((k) => (
            <label key={k} className={`flex cursor-pointer gap-2 rounded border px-3 py-2 ${tipo === k ? "border-brand bg-highlight" : "border-border"}`}>
              <input
                type="radio"
                name="tipo-documento"
                checked={tipo === k}
                onChange={() => {
                  setTipo(k);
                  setArquivos([]);
                }}
              />
              <span>
                <span className="block font-medium">{TIPOS_IMPORTACAO[k].nome}</span>
                <span className="text-xs text-text-muted">{TIPOS_IMPORTACAO[k].formatos.join(", ")}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <p className="text-text-muted">{t.detalhe}</p>
        <EnvioArquivo formatos={t.formatos} multiplo arquivos={arquivos} aoEscolher={setArquivos} />
        <div className="flex justify-end gap-2 border-t border-surface pt-3">
          <Botao variante="secundario" onClick={fechar}>
            Cancelar
          </Botao>
          <Botao
            disabled={!arquivos.length || enviando}
            onClick={() => {
              enviar(tipo, arquivos);
              setArquivos([]);
            }}
          >
            Importar {arquivos.length > 1 ? `${arquivos.length} arquivos` : "arquivo"}
          </Botao>
        </div>
      </div>
    </Modal>
  );
}

type OutraDespesa = { grupo_id: number; descricao: string; valor: number };
type LevantamentoDados = { status: string | null; itens: Record<string, number>; grupos_sem_outras: number[]; outras: OutraDespesa[] };

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

  const gravarOutras = useMutation({
    mutationFn: (corpo: { outras: OutraDespesa[]; grupos_sem_outras: number[] }) => api.put(`/planejamentos/${pid}/levantamentos/${atual}`, corpo),
    onSuccess: () => {
      setErro(null);
      qc.invalidateQueries({ queryKey: ["levantamento", pid, atual] });
      atualizar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  if (!atual || !lev) return <p>Carregando…</p>;
  const valor = (id: number) => lev.itens[String(id)];
  const editavel = !lev.status || lev.status === "EM_PREENCHIMENTO";
  const outrasDo = (id: number) => lev.outras.filter((o) => o.grupo_id === id).reduce((t, o) => t + Number(o.valor), 0);
  const total = catalogo.reduce((s, g) => s + outrasDo(g.id) + g.itens.filter((i) => i.ativo).reduce((t, i) => t + (valor(i.id) ?? 0), 0), 0);

  return (
    <div className="space-y-4">
      <Observacoes pid={pid} />
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
      {!editavel && <p className="text-sm text-text-muted">Este mês foi enviado para conferência e está só para consulta. Para alterar, o contador devolve o planejamento para a coleta.</p>}
      {catalogo.map((g) => {
        const subtotal = outrasDo(g.id) + g.itens.filter((i) => i.ativo).reduce((t, i) => t + (valor(i.id) ?? 0), 0);
        return (
          <Card key={g.id} titulo={g.nome} acoes={<span className="num text-sm font-semibold">Subtotal {brl(subtotal)}</span>}>
            <div className="grid gap-x-6 gap-y-1 md:grid-cols-2">
              {g.itens.filter((i) => i.ativo).map((i) => (
                <label key={`${atual}-${i.id}`} className="flex items-center justify-between gap-2 border-b border-surface/50 py-1 text-sm">
                  <span>{i.nome}</span>
                  <CampoMoeda rotulo={i.nome} valor={valor(i.id)} desabilitado={!editavel} onChange={(v) => gravar.mutate({ item_despesa_id: i.id, valor: v })} />
                </label>
              ))}
            </div>
            <OutrasDespesas key={`${atual}-${g.id}`} grupoId={g.id} lev={lev} editavel={editavel} salvar={(corpo) => gravarOutras.mutate(corpo)} />
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
        <Card
          key={b.codigo}
          titulo={`${b.nome} (peso ${b.peso}%)`}
          acoes={
            <span className="flex items-center gap-3">
              {b.codigo === "NCM" && b.pendencias.length > 0 && (
                <BotaoLink variante="linha" to={`/planejamentos/${pid}?aba=revisao`}>
                  Revisar produtos
                </BotaoLink>
              )}
              {b.codigo === "PREMISSAS" && b.pendencias.length > 0 && (
                <BotaoLink variante="linha" to={`/planejamentos/${pid}?aba=premissas`}>
                  Preencher premissas
                </BotaoLink>
              )}
              <span className="num text-sm">
                {b.preenchidos}/{b.esperados}
              </span>
            </span>
          }
        >
          {b.pendencias.length === 0 ? (
            <p className="text-sm">✔ Completo</p>
          ) : (
            <ul className="max-h-48 space-y-0.5 overflow-auto text-sm">
              {b.pendencias.map((x, i) => (
                <li key={i}>
                  <span className="text-alert">●</span> {x.competencia ? `${competenciaExtenso(x.competencia)}: ` : ""}
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
            <td className="px-2 py-1.5 text-right">
              <BotaoLink variante="linha" to={`/simulacoes/${s.id}`}>
                Ver resultado
              </BotaoLink>
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
        <Botao variante="linha" onClick={fechar}>
          Fechar
        </Botao>
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

type DadosObservacoes = { textos: string[]; aceitas_em: string | null; aceitas_por: string | null };

/** Orientações da planilha do escritório: precisam ser confirmadas antes de enviar para conferência. */
function Observacoes({ pid }: { pid: number }) {
  const atualizar = useAtualizar(pid);
  const qc = useQueryClient();
  const [erro, setErro] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: ["observacoes", pid],
    queryFn: async () => (await api.get<DadosObservacoes>(`/planejamentos/${pid}/observacoes`)).data,
  });
  const aceitar = useMutation({
    mutationFn: () => api.post(`/planejamentos/${pid}/observacoes/aceite`),
    onSuccess: () => {
      setErro(null);
      qc.invalidateQueries({ queryKey: ["observacoes", pid] });
      atualizar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });
  if (!data) return null;

  return (
    <Card titulo="Observações">
      <ul className="max-w-[80ch] list-disc space-y-1 pl-5 text-sm">
        {data.textos.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
      <div className="mt-3">
        <Erro mensagem={erro} />
        {data.aceitas_em ? (
          <p className="text-sm text-success-ink">
            ✔ Leitura confirmada por {data.aceitas_por} em {dataHora(data.aceitas_em)}.
          </p>
        ) : (
          <Botao onClick={() => aceitar.mutate()} disabled={aceitar.isPending}>
            Confirmar leitura
          </Botao>
        )}
      </div>
    </Card>
  );
}

/** "Possui outras despesas?" do grupo. Só conta como respondido com "não" ou com ao menos uma linha salva. */
function OutrasDespesas({
  grupoId,
  lev,
  editavel,
  salvar,
}: {
  grupoId: number;
  lev: LevantamentoDados;
  editavel: boolean;
  salvar: (corpo: { outras: OutraDespesa[]; grupos_sem_outras: number[] }) => void;
}) {
  const salvas = lev.outras.filter((o) => o.grupo_id === grupoId);
  const respondeuNao = lev.grupos_sem_outras.includes(grupoId);
  const [resposta, setResposta] = useState<"SIM" | "NAO" | null>(salvas.length ? "SIM" : respondeuNao ? "NAO" : null);
  const [linhas, setLinhas] = useState(salvas.length ? salvas.map((o) => ({ descricao: o.descricao, valor: editarMoeda(Number(o.valor)) })) : [{ descricao: "", valor: "" }]);
  const [erro, setErro] = useState<string | null>(null);

  function gravar(semOutras: boolean, novas: OutraDespesa[]) {
    const demaisSem = lev.grupos_sem_outras.filter((g) => g !== grupoId);
    salvar({
      outras: [...lev.outras.filter((o) => o.grupo_id !== grupoId), ...novas],
      grupos_sem_outras: semOutras ? [...demaisSem, grupoId] : demaisSem,
    });
  }

  function responder(r: "SIM" | "NAO") {
    setErro(null);
    setResposta(r);
    if (r === "NAO") gravar(true, []);
  }

  function salvarLinhas() {
    const novas = linhas.map((l) => ({ grupo_id: grupoId, descricao: l.descricao.trim(), valor: lerMoeda(l.valor) }));
    if (novas.some((l) => l.descricao.length < 2 || l.valor == null)) return setErro("Cada linha precisa de descrição e valor");
    setErro(null);
    gravar(false, novas as OutraDespesa[]);
  }

  const alterada = JSON.stringify(linhas.map((l) => [l.descricao.trim(), lerMoeda(l.valor)])) !== JSON.stringify(salvas.map((o) => [o.descricao, Number(o.valor)]));

  return (
    <div className="mt-3 border-t border-surface pt-3 text-sm">
      <fieldset className="flex flex-wrap items-center gap-4" disabled={!editavel}>
        <legend className="float-left mr-2 font-medium">Possui outras despesas?</legend>
        <label className="flex items-center gap-1.5">
          <input type="radio" name={`outras-${grupoId}`} checked={resposta === "NAO"} onChange={() => responder("NAO")} />
          Não
        </label>
        <label className="flex items-center gap-1.5">
          <input type="radio" name={`outras-${grupoId}`} checked={resposta === "SIM"} onChange={() => responder("SIM")} />
          Sim
        </label>
        {resposta === null && <span className="text-alert-ink">! Sem resposta</span>}
      </fieldset>
      {resposta === "SIM" && (
        <div className="mt-2 space-y-2">
          {linhas.map((l, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <input
                aria-label="Descrição da despesa"
                placeholder="Descreva a despesa"
                maxLength={200}
                disabled={!editavel}
                className="min-w-56 flex-1 rounded border border-border bg-white px-2 py-1"
                value={l.descricao}
                onChange={(e) => setLinhas(linhas.map((x, j) => (j === i ? { ...x, descricao: e.target.value } : x)))}
              />
              <input
                aria-label="Valor da despesa"
                inputMode="decimal"
                placeholder="0,00"
                disabled={!editavel}
                className="num w-32 rounded border border-border bg-white px-2 py-1"
                value={l.valor}
                onChange={(e) => setLinhas(linhas.map((x, j) => (j === i ? { ...x, valor: e.target.value.replace(/[^\d.,]/g, "") } : x)))}
              />
              {editavel && linhas.length > 1 && (
                <Botao variante="linha-perigo" onClick={() => setLinhas(linhas.filter((_, j) => j !== i))}>
                  Remover
                </Botao>
              )}
            </div>
          ))}
          <Erro mensagem={erro} />
          {editavel && (
            <div className="flex flex-wrap items-center gap-3">
              <Botao variante="secundario" onClick={() => setLinhas([...linhas, { descricao: "", valor: "" }])}>
                Adicionar linha
              </Botao>
              <Botao onClick={salvarLinhas}>
                Salvar outras despesas
              </Botao>
              {alterada && <span className="text-warning-ink">Alterações ainda não salvas</span>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const ESTADOS: Record<string, string> = {
  EM_COLETA: "Quando os dados estiverem prontos, envie para o contador conferir.",
  EM_CONFERENCIA: "Aguardando a conferência do contador. Os meses estão só para consulta.",
  PRONTO_PARA_SIMULAR: "Conferência concluída. Gere uma nova simulação na aba Simulações.",
  SIMULADO: "Simulação gerada. O contador revisa o resultado e aprova.",
  APROVADO: "Planejamento aprovado.",
};

/** Barra do fluxo: mostra a etapa atual e só oferece as ações que o perfil pode fazer. */
function AcoesStatus({ p }: { p: TPlanejamento }) {
  const qc = useQueryClient();
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const [confirmar, janelaConfirmacao] = useConfirmacao();
  const [devolvendo, setDevolvendo] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const { data: historico = [] } = useQuery({
    queryKey: ["historico", p.id, p.status],
    queryFn: async () => (await api.get<{ para: string; motivo: string | null; usuario: string | null }[]>(`/planejamentos/${p.id}/historico`)).data,
  });
  const mudar = useMutation({
    mutationFn: (corpo: { status: string; motivo?: string }) => api.post(`/planejamentos/${p.id}/status`, corpo),
    onSuccess: () => {
      setErro(null);
      setDevolvendo(false);
      setMotivo("");
      qc.invalidateQueries();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  async function enviar() {
    const ok =
      p.progresso >= 100 ||
      (await confirmar({
        titulo: "Enviar para conferência",
        mensagem: `Os dados estão em ${p.progresso}%. O contador vai receber o planejamento com pendências (veja a aba Pendências). Enviar mesmo assim?`,
        confirmar: "Enviar com pendências",
      }));
    if (ok) mudar.mutate({ status: "EM_CONFERENCIA" });
  }

  const ultimo = historico[historico.length - 1];
  const devolvido = p.status === "EM_COLETA" && ultimo?.para === "EM_COLETA" && ultimo.motivo && ultimo.motivo !== "Criação";
  const podeDevolver = contador && p.status !== "EM_COLETA";

  return (
    <div className="space-y-2">
      {devolvido && (
        <p className="rounded border border-warning bg-warning-soft px-3 py-2 text-sm text-warning-ink">
          <strong>Devolvido por {ultimo.usuario}:</strong> {ultimo.motivo}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-text-muted">{ESTADOS[p.status]}</span>
        <div className="ml-auto flex flex-wrap gap-2">
          {podeDevolver && (
            <Botao variante="secundario" onClick={() => setDevolvendo(true)}>
              {p.status === "EM_CONFERENCIA" ? "Devolver para a coleta" : "Reabrir a coleta"}
            </Botao>
          )}
          {p.status === "EM_COLETA" && (
            <Botao onClick={enviar} disabled={mudar.isPending}>
              Enviar para conferência
            </Botao>
          )}
          {p.status === "EM_CONFERENCIA" && contador && (
            <Botao onClick={() => mudar.mutate({ status: "PRONTO_PARA_SIMULAR" })} disabled={mudar.isPending}>
              Confirmar conferência
            </Botao>
          )}
        </div>
      </div>
      <Erro mensagem={erro} />
      {janelaConfirmacao}
      <Modal aberto={devolvendo} fechar={() => setDevolvendo(false)} titulo="Devolver para a coleta" descricao="O motivo aparece para quem está coletando os dados." largura="max-w-lg">
        <label className="block text-sm">
          Motivo<Obrigatorio />
          <textarea
            autoFocus
            rows={3}
            maxLength={500}
            placeholder="Diga o que precisa ser ajustado"
            className="mt-1 w-full rounded border border-border bg-white px-2 py-1.5"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
          />
        </label>
        <div className="mt-3 flex justify-end gap-2 border-t border-surface pt-3">
          <Botao variante="secundario" onClick={() => setDevolvendo(false)}>
            Cancelar
          </Botao>
          <Botao disabled={motivo.trim().length < 3 || mudar.isPending} onClick={() => mudar.mutate({ status: "EM_COLETA", motivo: motivo.trim() })}>
            Devolver para a coleta
          </Botao>
        </div>
      </Modal>
    </div>
  );
}
