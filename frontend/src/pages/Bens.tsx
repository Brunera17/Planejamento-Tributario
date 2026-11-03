import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { api, mensagemErro } from "../api/cliente";
import { Botao, Card, Erro, LegendaObrigatorio, Obrigatorio, Tabela, useConfirmacao } from "../components/ui";
import { brl, editarMoeda, lerMoeda } from "../lib/formato";

type Bem = { id: number; tipo: string; descricao: string; data_aquisicao: string; valor: number };

const TIPOS: Record<string, string> = {
  VEICULOS: "Veículos",
  MOVEIS_UTENSILIOS: "Móveis e utensílios",
  MAQUINAS_EQUIPAMENTOS: "Máquinas e equipamentos",
  IMOVEL: "Imóvel",
};
const VAZIO = { tipo: "VEICULOS", descricao: "", data_aquisicao: "", valor: "" };
const VALOR_MINIMO = 1200;

const dataBr = (iso: string) => iso.split("-").reverse().join("/");

export function Bens({ pid }: { pid: number }) {
  const qc = useQueryClient();
  const [confirmar, janelaConfirmacao] = useConfirmacao();
  const [form, setForm] = useState(VAZIO);
  const [editando, setEditando] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: ["bens", pid],
    queryFn: async () => (await api.get<{ sem_bens: boolean; bens: Bem[] }>(`/planejamentos/${pid}/bens`)).data,
  });

  function concluido() {
    setErro(null);
    qc.invalidateQueries({ queryKey: ["bens", pid] });
    qc.invalidateQueries({ queryKey: ["planejamento", String(pid)] });
    qc.invalidateQueries({ queryKey: ["progresso", pid] });
  }
  function limpar() {
    setForm(VAZIO);
    setEditando(null);
  }
  const falhou = (e: unknown) => setErro(mensagemErro(e));

  const salvar = useMutation({
    mutationFn: (corpo: object) =>
      editando ? api.put(`/planejamentos/${pid}/bens/${editando}`, corpo) : api.post(`/planejamentos/${pid}/bens`, corpo),
    onSuccess: () => {
      limpar();
      concluido();
    },
    onError: falhou,
  });
  const excluir = useMutation({
    mutationFn: (id: number) => api.delete(`/planejamentos/${pid}/bens/${id}`),
    onSuccess: () => {
      limpar();
      concluido();
    },
    onError: falhou,
  });
  const semBens = useMutation({
    mutationFn: (valor: boolean) => api.put(`/planejamentos/${pid}/sem-bens`, null, { params: { sem_bens: valor } }),
    onSuccess: concluido,
    onError: falhou,
  });

  function enviar(e: FormEvent) {
    e.preventDefault();
    const valor = lerMoeda(form.valor);
    if (form.descricao.trim().length < 2) return setErro("Descreva o bem");
    if (!form.data_aquisicao) return setErro("Informe a data de aquisição");
    if (form.data_aquisicao > new Date().toISOString().slice(0, 10)) return setErro("A data de aquisição não pode ser futura");
    if (valor == null || valor <= VALOR_MINIMO) return setErro("Só entram aqui bens acima de R$ 1.200,00");
    salvar.mutate({ ...form, descricao: form.descricao.trim(), valor });
  }

  if (!data) return <p>Carregando…</p>;
  const total = data.bens.reduce((s, b) => s + Number(b.valor), 0);
  const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";

  return (
    <div className="space-y-4">
      <Erro mensagem={erro} />
      {janelaConfirmacao}
      <Card titulo={editando ? "Editar bem" : "Cadastrar bem"} adendo="Só bens acima de R$ 1.200,00. Valem para a empresa, em todos os planejamentos dela.">
        <form onSubmit={enviar} className="grid gap-3 text-sm md:grid-cols-[12rem_1fr_9.5rem_9rem]">
          <label>
            Tipo<Obrigatorio />
            <select className={campo} value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })}>
              {Object.entries(TIPOS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label>
            Descrição<Obrigatorio />
            <input className={campo} maxLength={200} placeholder="Utilitário de entregas" value={form.descricao} onChange={(e) => setForm({ ...form, descricao: e.target.value })} />
          </label>
          <label>
            Data de aquisição<Obrigatorio />
            <input type="date" className={campo} value={form.data_aquisicao} onChange={(e) => setForm({ ...form, data_aquisicao: e.target.value })} />
          </label>
          <label>
            Valor (R$)<Obrigatorio />
            <input inputMode="decimal" className={`${campo} num`} placeholder="1.200,01" value={form.valor} onChange={(e) => setForm({ ...form, valor: e.target.value.replace(/[^\d.,]/g, "") })} />
          </label>
          <div className="flex items-center justify-between gap-2 md:col-span-4">
            <LegendaObrigatorio />
            <div className="flex gap-2">
              {editando && (
                <Botao variante="secundario" onClick={limpar}>
                  Cancelar
                </Botao>
              )}
              <Botao type="submit" disabled={salvar.isPending}>
                {editando ? "Salvar alterações" : "Cadastrar bem"}
              </Botao>
            </div>
          </div>
        </form>
      </Card>

      <Card titulo={data.bens.length === 1 ? "1 bem cadastrado" : `${data.bens.length} bens cadastrados`} semPadding>
        {data.bens.length === 0 ? (
          <div className="p-4">
            <p className="mb-3 text-text-muted">Nenhum bem cadastrado. Cadastre o primeiro acima ou declare que a empresa não tem bens acima de R$ 1.200,00.</p>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={data.sem_bens} disabled={semBens.isPending} onChange={(e) => semBens.mutate(e.target.checked)} />A empresa não possui bens acima de R$ 1.200,00
            </label>
          </div>
        ) : (
          <Tabela cabecalho={["Tipo", "Descrição", "Data de aquisição", "Valor", ""]} numericas={[3]}>
            {data.bens.map((b) => (
              <tr key={b.id} className={editando === b.id ? "bg-highlight" : ""}>
                <td className="px-4 py-2">{TIPOS[b.tipo] ?? b.tipo}</td>
                <td className="px-2 py-2 font-medium">{b.descricao}</td>
                <td className="px-2 py-2">{dataBr(b.data_aquisicao)}</td>
                <td className="num px-2 py-2">{brl(Number(b.valor))}</td>
                <td className="px-4 py-2">
                  <div className="flex justify-end gap-1.5">
                  <Botao
                    variante="linha"
                    onClick={() => {
                      setEditando(b.id);
                      setErro(null);
                      setForm({ tipo: b.tipo, descricao: b.descricao, data_aquisicao: b.data_aquisicao, valor: editarMoeda(Number(b.valor)) });
                      window.scrollTo({ top: 0 });
                    }}
                  >
                    Editar
                  </Botao>
                  <Botao
                    variante="linha-perigo"
                    onClick={async () =>
                      (await confirmar({ titulo: "Excluir bem", mensagem: `Excluir "${b.descricao}"? Ele sai de todos os planejamentos da empresa.`, confirmar: "Excluir bem", perigo: true })) &&
                      excluir.mutate(b.id)
                    }
                  >
                    Excluir
                  </Botao>
                  </div>
                </td>
              </tr>
            ))}
            <tr className="font-semibold">
              <td className="px-4 py-2" colSpan={3}>
                Total
              </td>
              <td className="num px-2 py-2">{brl(total)}</td>
              <td />
            </tr>
          </Tabela>
        )}
      </Card>
    </div>
  );
}
