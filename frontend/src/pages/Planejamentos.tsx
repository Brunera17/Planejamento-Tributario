import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import { useLista } from "../api/lista";
import type { Empresa, Planejamento } from "../api/tipos";
import { Badge, BarraProgresso, Botao, Cabecalho, CarregarMais, Card, Erro, LegendaObrigatorio, Modal, Obrigatorio, Tabela } from "../components/ui";
import { competenciaExtenso, dataHora, formatarCnpj, REGIMES, STATUS } from "../lib/formato";

export function Planejamentos() {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const navegar = useNavigate();
  const [novo, setNovo] = useState(false);
  const [status, setStatus] = useState("");
  const [busca, setBusca] = useState("");
  const lista = useLista<Planejamento>(["planejamentos", status, busca], "/planejamentos", { status: status || undefined, busca: busca || undefined });
  const data = lista.itens;

  return (
    <>
      <Cabecalho
        titulo="Planejamentos"
        descricao="Cada planejamento reúne os dados de uma empresa num período e compara os três regimes."
        acoes={contador && <Botao onClick={() => setNovo(true)}>Novo planejamento</Botao>}
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
        titulo={`${data.length}${lista.temMais ? "+" : ""} ${data.length === 1 ? "planejamento" : "planejamentos"}`}
      >
        <Tabela cabecalho={["Empresa", "CNPJ", "Regime atual", "Período", "Documentos recebidos", "Progresso", "Status"]}>
          {data.map((p) => (
            <tr key={p.id} className="cursor-pointer" onClick={() => navegar(`/planejamentos/${p.id}`)}>
              <td className="px-4 py-2">
                <Link className="font-medium text-brand underline-offset-2 hover:underline" to={`/planejamentos/${p.id}`} onClick={(e) => e.stopPropagation()}>
                  {p.razao_social}
                </Link>
              </td>
              <td className="px-2 py-2">{formatarCnpj(p.cnpj)}</td>
              <td className="px-2 py-2">{REGIMES[p.regime_tributario]}</td>
              <td className="px-2 py-2">
                {competenciaExtenso(p.competencia_inicial)} a {competenciaExtenso(p.competencia_final)}
              </td>
              <td className="whitespace-nowrap px-2 py-2">
                {p.documentos_recebidos_em ? (
                  <span title="Quando o último documento que faltava foi enviado">{dataHora(p.documentos_recebidos_em)}</span>
                ) : (
                  <Link className="text-text-muted underline-offset-2 hover:underline" to={`/planejamentos/${p.id}?aba=documentos`} onClick={(e) => e.stopPropagation()}>
                    {p.documentos_faltando === 1 ? "Falta 1" : `Faltam ${p.documentos_faltando}`}
                  </Link>
                )}
              </td>
              <td className="px-2 py-2">
                <Link to={`/planejamentos/${p.id}?aba=pendencias`} title="Ver o que falta" onClick={(e) => e.stopPropagation()}>
                  <BarraProgresso valor={p.progresso} />
                </Link>
              </td>
              <td className="px-2 py-2">
                <Badge status={p.status} />
              </td>
            </tr>
          ))}
        </Tabela>
        <CarregarMais lista={lista} />
      </Card>
    </>
  );
}

function NovoPlanejamento({ fechar }: { fechar: () => void }) {
  const qc = useQueryClient();
  const [buscaEmpresa, setBuscaEmpresa] = useState("");
  const { data: empresas = [] } = useQuery({
    queryKey: ["empresas", "escolha", buscaEmpresa],
    queryFn: async () => (await api.get<Empresa[]>("/empresas", { params: { busca: buscaEmpresa || undefined } })).data,
  });
  const [form, setForm] = useState({ empresa_id: "", competencia_inicial: "", competencia_final: "" });
  const [erro, setErro] = useState<string | null>(null);
  const criar = useMutation({
    mutationFn: () => api.post("/planejamentos", { ...form, empresa_id: Number(form.empresa_id) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["planejamentos"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] }); // as contagens da visão geral vêm do indicador
      fechar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });
  const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";
  const completo = form.empresa_id && form.competencia_inicial && form.competencia_final;
  return (
    <Modal aberto fechar={fechar} titulo="Novo planejamento" descricao="Escolha a empresa e os meses que entram na comparação." largura="max-w-xl">
      <form
        className="grid gap-3 text-sm sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (completo) criar.mutate();
        }}
      >
        <label className="sm:col-span-2">
          Empresa<Obrigatorio />
          <input
            autoFocus
            aria-label="Buscar empresa por razão social ou CNPJ"
            placeholder="Buscar por razão social ou CNPJ"
            className={campo}
            value={buscaEmpresa}
            onChange={(e) => {
              setBuscaEmpresa(e.target.value);
              setForm({ ...form, empresa_id: "" }); // a escolhida pode sumir do filtro
            }}
          />
          <select aria-label="Empresa" className={campo} value={form.empresa_id} onChange={(e) => setForm({ ...form, empresa_id: e.target.value })}>
            <option value="">Selecione</option>
            {empresas.map((e) => (
              <option key={e.id} value={e.id}>
                {e.razao_social}
              </option>
            ))}
          </select>
        </label>
        <label>
          Primeiro mês<Obrigatorio />
          <input type="month" className={campo} value={form.competencia_inicial} onChange={(e) => setForm({ ...form, competencia_inicial: e.target.value })} />
        </label>
        <label>
          Último mês<Obrigatorio />
          <input type="month" className={campo} value={form.competencia_final} onChange={(e) => setForm({ ...form, competencia_final: e.target.value })} />
        </label>
        <div className="space-y-2 sm:col-span-2">
          <Erro mensagem={erro} />
          <div className="flex items-center justify-between gap-2 border-t border-surface pt-3">
            <LegendaObrigatorio />
            <div className="flex gap-2">
              <Botao variante="secundario" onClick={fechar}>
                Cancelar
              </Botao>
              <Botao type="submit" disabled={!completo || criar.isPending}>
                Criar planejamento
              </Botao>
            </div>
          </div>
        </div>
      </form>
    </Modal>
  );
}
