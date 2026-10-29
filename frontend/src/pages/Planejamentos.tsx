import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import type { Empresa, Planejamento } from "../api/tipos";
import { Badge, BarraProgresso, Botao, Cabecalho, Card, Erro, Tabela } from "../components/ui";
import { competenciaExtenso, formatarCnpj, REGIMES, STATUS } from "../lib/formato";

export function Planejamentos() {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const [novo, setNovo] = useState(false);
  const [status, setStatus] = useState("");
  const [busca, setBusca] = useState("");
  const { data = [] } = useQuery({
    queryKey: ["planejamentos", status, busca],
    queryFn: async () => (await api.get<Planejamento[]>("/planejamentos", { params: { status: status || undefined, busca: busca || undefined } })).data,
  });

  return (
    <>
      <Cabecalho
        titulo="Planejamentos"
        descricao="Cada planejamento reúne os dados de uma empresa num período e compara os três regimes."
        acoes={contador && !novo && <Botao onClick={() => setNovo(true)}>Novo planejamento</Botao>}
      />
      {novo && <NovoPlanejamento fechar={() => setNovo(false)} />}
      <Card
        semPadding
        acoes={
          <div className="flex flex-wrap gap-2 text-sm">
            <input
              aria-label="Buscar por razão social ou CNPJ"
              placeholder="Razão social ou CNPJ"
              className="rounded border border-border px-2 py-1"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
            <select aria-label="Filtrar por status" className="rounded border border-border px-2 py-1" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Todos os status</option>
              {Object.entries(STATUS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </div>
        }
        titulo={`${data.length} ${data.length === 1 ? "planejamento" : "planejamentos"}`}
      >
        <Tabela cabecalho={["Empresa", "CNPJ", "Regime atual", "Período", "Progresso", "Status"]}>
          {data.map((p) => (
            <tr key={p.id}>
              <td className="px-4 py-2">
                <Link className="font-medium text-brand underline-offset-2 hover:underline" to={`/planejamentos/${p.id}`}>
                  {p.razao_social}
                </Link>
              </td>
              <td className="px-2 py-2">{formatarCnpj(p.cnpj)}</td>
              <td className="px-2 py-2">{REGIMES[p.regime_tributario]}</td>
              <td className="px-2 py-2">
                {competenciaExtenso(p.competencia_inicial)} a {competenciaExtenso(p.competencia_final)}
              </td>
              <td className="px-2 py-2">
                <Link to={`/planejamentos/${p.id}?aba=pendencias`} title="Ver o que falta">
                  <BarraProgresso valor={p.progresso} />
                </Link>
              </td>
              <td className="px-2 py-2">
                <Badge status={p.status} />
              </td>
            </tr>
          ))}
        </Tabela>
      </Card>
    </>
  );
}

function NovoPlanejamento({ fechar }: { fechar: () => void }) {
  const qc = useQueryClient();
  const { data: empresas = [] } = useQuery({ queryKey: ["empresas"], queryFn: async () => (await api.get<Empresa[]>("/empresas")).data });
  const [form, setForm] = useState({ empresa_id: "", competencia_inicial: "", competencia_final: "" });
  const [erro, setErro] = useState<string | null>(null);
  const criar = useMutation({
    mutationFn: () => api.post("/planejamentos", { ...form, empresa_id: Number(form.empresa_id) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["planejamentos"] });
      fechar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });
  const campo = "mt-1 block rounded border border-border bg-white px-2 py-1.5";
  return (
    <Card titulo="Novo planejamento">
      <div className="flex flex-wrap items-end gap-4 text-sm">
        <label>
          Empresa
          <select className={`${campo} min-w-64`} value={form.empresa_id} onChange={(e) => setForm({ ...form, empresa_id: e.target.value })}>
            <option value="">Selecione</option>
            {empresas.map((e) => (
              <option key={e.id} value={e.id}>
                {e.razao_social}
              </option>
            ))}
          </select>
        </label>
        <label>
          Primeiro mês
          <input type="month" className={campo} value={form.competencia_inicial} onChange={(e) => setForm({ ...form, competencia_inicial: e.target.value })} />
        </label>
        <label>
          Último mês
          <input type="month" className={campo} value={form.competencia_final} onChange={(e) => setForm({ ...form, competencia_final: e.target.value })} />
        </label>
        <div className="flex gap-2">
          <Botao onClick={() => criar.mutate()} disabled={!form.empresa_id || !form.competencia_inicial || !form.competencia_final}>
            Criar planejamento
          </Botao>
          <Botao variante="secundario" onClick={fechar}>
            Cancelar
          </Botao>
        </div>
      </div>
      {erro && (
        <div className="mt-3">
          <Erro mensagem={erro} />
        </div>
      )}
    </Card>
  );
}
