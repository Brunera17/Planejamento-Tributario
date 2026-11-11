import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/cliente";
import type { Planejamento } from "../api/tipos";
import { Badge, BarraProgresso, Botao, BotaoLink, Cabecalho, Card, Tabela } from "../components/ui";
import { brl } from "../lib/formato";

type Indicadores = {
  empresas_ativas: number;
  planejamentos_por_status: Record<string, number>;
  simulacoes_desatualizadas: number;
  economia_anual_estimada: number;
  recuperacoes_identificadas: number;
  empresas_proximas_sublimite: number;
};

/** Etapas do planejamento, na ordem em que acontecem. */
const ETAPAS = [
  { status: "EM_COLETA", nome: "Em coleta" },
  { status: "EM_CONFERENCIA", nome: "Em conferência" },
  { status: "PRONTO_PARA_SIMULAR", nome: "Pronto para simular" },
  { status: "SIMULADO", nome: "Aguardando aprovação" },
  { status: "APROVADO", nome: "Aprovado" },
];

/** O que o planejamento precisa agora, em linguagem de quem trabalha nele. */
function proximoPasso(p: Planejamento): { acao: string; aba: string } {
  if (p.status === "SIMULADO") return { acao: "Revisar resultado", aba: "simulacoes" };
  if (p.status === "PRONTO_PARA_SIMULAR") return { acao: "Simular", aba: "simulacoes" };
  if (p.status === "EM_CONFERENCIA") return { acao: "Conferir dados", aba: "pendencias" };
  return { acao: p.progresso === 0 ? "Começar coleta" : "Ver pendências", aba: "pendencias" };
}

function Indicador({ rotulo, valor, nota }: { rotulo: string; valor: string | number; nota?: string }) {
  return (
    <div className="flex min-h-24 flex-col justify-between gap-2 border-b border-r border-border px-4 py-3">
      <dt className="text-sm text-text-muted">{rotulo}</dt>
      <dd>
        <span className="block text-2xl font-semibold tracking-tight whitespace-nowrap">{valor}</span>
        {nota && <span className="text-xs text-text-muted">{nota}</span>}
      </dd>
    </div>
  );
}

export function Dashboard() {
  const navegar = useNavigate();
  const [etapa, setEtapa] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["dashboard"], queryFn: async () => (await api.get<Indicadores>("/dashboard")).data });
  // shortcut: só os 200 mais recentes da etapa (ou em aberto) entram na ordenação; ordenar no SQL se a carteira passar disso
  const { data: planejamentos = [] } = useQuery({
    queryKey: ["planejamentos", "painel", etapa],
    queryFn: async () => (await api.get<Planejamento[]>("/planejamentos", { params: etapa ? { status: etapa, limite: 200 } : { abertos: true, limite: 200 } })).data,
  });
  if (!data) return <p>Carregando…</p>;

  const contagem = (s: string) => data.planejamentos_por_status[s] ?? 0;
  const emAndamento = Object.entries(data.planejamentos_por_status).reduce((t, [s, n]) => (s === "APROVADO" ? t : t + n), 0);
  // quem está mais adiantado no fluxo vem primeiro: aprovar fecha o trabalho; coleta parada vem por menor progresso
  const ordem = (p: Planejamento) => ETAPAS.findIndex((e) => e.status === p.status);
  const lista = [...planejamentos].sort((a, b) => ordem(b) - ordem(a) || a.progresso - b.progresso);
  const nomeEtapa = ETAPAS.find((e) => e.status === etapa)?.nome;

  return (
    <>
      <Cabecalho
        titulo="Visão geral"
        descricao={`${emAndamento} ${emAndamento === 1 ? "planejamento em andamento" : "planejamentos em andamento"} em ${data.empresas_ativas} ${data.empresas_ativas === 1 ? "empresa ativa" : "empresas ativas"}.`}
      />

      <dl className="grid grid-cols-1 overflow-hidden rounded-md border-l border-t border-border bg-white sm:grid-cols-2 lg:grid-cols-4">
        <Indicador rotulo="Economia anual estimada" valor={brl(data.economia_anual_estimada)} nota="regime atual contra o melhor regime" />
        <Indicador rotulo="Recuperações identificadas" valor={brl(data.recuperacoes_identificadas)} nota="monofásico e ICMS-ST pagos a mais" />
        <Indicador rotulo="Perto do sublimite do Simples" valor={data.empresas_proximas_sublimite} nota={data.empresas_proximas_sublimite === 1 ? "empresa" : "empresas"} />
        <Indicador rotulo="Simulações desatualizadas" valor={data.simulacoes_desatualizadas} nota="dados mudaram depois do cálculo" />
      </dl>

      <Card titulo="Planejamentos por etapa" semPadding>
        <ol className="grid grid-cols-2 sm:grid-cols-5">
          {ETAPAS.map((e, i) => {
            const n = contagem(e.status);
            const ativa = etapa === e.status;
            return (
              <li key={e.status} className="border-b border-r border-surface last:border-r-0 sm:border-b-0">
                <button
                  type="button"
                  aria-pressed={ativa}
                  onClick={() => setEtapa(ativa ? null : e.status)}
                  className={`flex h-full w-full flex-col items-start gap-1 px-4 py-3 text-left ${ativa ? "bg-highlight shadow-[inset_0_-3px_0_var(--color-brand)]" : "hover:bg-bg"}`}
                >
                  <span className="text-xs text-text-muted">
                    {i + 1}. {e.nome}
                  </span>
                  <span className={`text-2xl font-semibold ${n ? "" : "text-text-muted"}`}>{n}</span>
                </button>
              </li>
            );
          })}
        </ol>
      </Card>

      <Card
        titulo={nomeEtapa ? `${nomeEtapa} (${contagem(etapa!)})` : "Próximas ações"}
        semPadding
        acoes={etapa && <Botao variante="linha" onClick={() => setEtapa(null)}>Mostrar todos em aberto</Botao>}
      >
        {lista.length === 0 ? (
          <p className="p-4 text-text-muted">{etapa ? "Nenhum planejamento nesta etapa." : "Nenhum planejamento em aberto. Crie um em Planejamentos para começar."}</p>
        ) : (
          <Tabela cabecalho={["Empresa", "Etapa", "Dados coletados", ""]}>
            {lista.map((p) => {
              const passo = proximoPasso(p);
              const destino = `/planejamentos/${p.id}?aba=${passo.aba}`;
              return (
                <tr key={p.id} className="cursor-pointer" onClick={() => navegar(destino)}>
                  <td className="px-4 py-2 font-medium">{p.razao_social}</td>
                  <td className="px-2 py-2">
                    <Badge status={p.status} />
                  </td>
                  <td className="px-2 py-2">
                    <BarraProgresso valor={p.progresso} />
                  </td>
                  <td className="px-4 py-2 text-right">
                    {p.status !== "APROVADO" && (
                      <BotaoLink variante="linha" to={destino} onClick={(e) => e.stopPropagation()}>
                        {passo.acao}
                      </BotaoLink>
                    )}
                  </td>
                </tr>
              );
            })}
          </Tabela>
        )}
      </Card>
    </>
  );
}
