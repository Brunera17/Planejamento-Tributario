import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/cliente";
import type { Planejamento } from "../api/tipos";
import { BarraProgresso, Cabecalho, Card, Ficha, Tabela } from "../components/ui";
import { brl } from "../lib/formato";

type Indicadores = {
  empresas_ativas: number;
  planejamentos_por_status: Record<string, number>;
  simulacoes_desatualizadas: number;
  economia_anual_estimada: number;
  recuperacoes_identificadas: number;
  empresas_proximas_sublimite: number;
};

/** O que o planejamento precisa agora, em linguagem de quem trabalha nele. */
function proximoPasso(p: Planejamento): { situacao: string; acao: string; aba: string } {
  if (p.status === "SIMULADO") return { situacao: "Simulado, aguardando aprovação", acao: "Revisar resultado", aba: "simulacoes" };
  if (p.status === "PRONTO_PARA_SIMULAR") return { situacao: "Dados conferidos", acao: "Simular", aba: "simulacoes" };
  if (p.status === "EM_CONFERENCIA") return { situacao: "Em conferência", acao: "Conferir dados", aba: "pendencias" };
  return { situacao: p.progresso === 0 ? "Sem dados ainda" : "Coleta em andamento", acao: "Ver pendências", aba: "pendencias" };
}

export function Dashboard() {
  const { data } = useQuery({ queryKey: ["dashboard"], queryFn: async () => (await api.get<Indicadores>("/dashboard")).data });
  const { data: planejamentos = [] } = useQuery({
    queryKey: ["planejamentos", "", ""],
    queryFn: async () => (await api.get<Planejamento[]>("/planejamentos")).data,
  });
  if (!data) return <p>Carregando…</p>;
  const abertos = planejamentos.filter((p) => p.status !== "APROVADO").sort((a, b) => a.progresso - b.progresso);

  return (
    <>
      <Cabecalho
        titulo="Visão geral"
        descricao={`${abertos.length} ${abertos.length === 1 ? "planejamento em andamento" : "planejamentos em andamento"} em ${data.empresas_ativas} ${data.empresas_ativas === 1 ? "empresa ativa" : "empresas ativas"}.`}
      />
      <Ficha
        campos={[
          { rotulo: "Economia anual estimada na carteira", valor: brl(data.economia_anual_estimada), largo: true },
          { rotulo: "Recuperações identificadas", valor: brl(data.recuperacoes_identificadas), largo: true },
          { rotulo: "Perto do sublimite do Simples", valor: data.empresas_proximas_sublimite },
          { rotulo: "Simulações desatualizadas", valor: data.simulacoes_desatualizadas },
        ]}
      />
      <Card titulo="O que precisa de atenção" semPadding>
        {abertos.length === 0 ? (
          <p className="p-4 text-text-muted">Nenhum planejamento em aberto. Crie um em Planejamentos para começar.</p>
        ) : (
          <Tabela cabecalho={["Empresa", "Situação", "Dados coletados", ""]}>
            {abertos.map((p) => {
              const passo = proximoPasso(p);
              return (
                <tr key={p.id}>
                  <td className="px-4 py-2 font-medium">{p.razao_social}</td>
                  <td className="px-2 py-2">{passo.situacao}</td>
                  <td className="px-2 py-2">
                    <BarraProgresso valor={p.progresso} />
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Link className="text-brand underline underline-offset-2" to={`/planejamentos/${p.id}?aba=${passo.aba}`}>
                      {passo.acao}
                    </Link>
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
