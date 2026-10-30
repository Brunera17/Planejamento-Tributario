import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, baixarArquivo, mensagemErro } from "../api/cliente";
import { Botao, Card, Erro } from "../components/ui";
import { competenciaExtenso } from "../lib/formato";

type Documento = {
  id: number;
  competencia: string;
  tipo_documento_id: number;
  arquivo: string | null;
  nao_se_aplica: boolean;
  justificativa: string | null;
};
type Dados = {
  competencias: { competencia: string; editavel: boolean }[];
  tipos: { id: number; nome: string }[];
  documentos: Documento[];
};
type Celula = { competencia: string; tipo: number; nome: string };

const FORMATOS = ".pdf,.xlsx,.csv,.jpg,.jpeg,.png";

/** Conferência de documentos: uma linha por documento, uma coluna por mês, com a ação na própria célula. */
export function Documentos({ pid }: { pid: number }) {
  const qc = useQueryClient();
  const [erro, setErro] = useState<string | null>(null);
  const [justificando, setJustificando] = useState<Celula | null>(null);
  const [justificativa, setJustificativa] = useState("");
  const { data } = useQuery({
    queryKey: ["documentos", pid],
    queryFn: async () => (await api.get<Dados>(`/planejamentos/${pid}/documentos`)).data,
  });

  function concluido() {
    setErro(null);
    qc.invalidateQueries({ queryKey: ["documentos", pid] });
    qc.invalidateQueries({ queryKey: ["planejamento", String(pid)] });
    qc.invalidateQueries({ queryKey: ["progresso", pid] });
  }
  const falhou = (e: unknown) => setErro(mensagemErro(e));

  const enviar = useMutation({
    mutationFn: ({ competencia, tipo, arquivo }: { competencia: string; tipo: number; arquivo: File }) => {
      const fd = new FormData();
      fd.append("arquivo", arquivo);
      return api.post(`/planejamentos/${pid}/documentos/${competencia}/${tipo}`, fd);
    },
    onSuccess: concluido,
    onError: falhou,
  });
  const naoSeAplica = useMutation({
    mutationFn: (c: Celula) => api.put(`/planejamentos/${pid}/documentos/${c.competencia}/${c.tipo}/nao-se-aplica`, { justificativa: justificativa.trim() }),
    onSuccess: () => {
      setJustificando(null);
      setJustificativa("");
      concluido();
    },
    onError: falhou,
  });
  const excluir = useMutation({
    mutationFn: (id: number) => api.delete(`/planejamentos/${pid}/documentos/${id}`),
    onSuccess: concluido,
    onError: falhou,
  });

  if (!data) return <p>Carregando…</p>;
  const esperados = data.tipos.length * data.competencias.length;
  const faltam = esperados - data.documentos.length;
  const achar = (c: string, t: number) => data.documentos.find((d) => d.competencia === c && d.tipo_documento_id === t);
  const baixar = (d: Documento) => baixarArquivo(`/planejamentos/${pid}/documentos/${d.id}/download`, d.arquivo ?? "documento").catch(falhou);
  const acao = "text-left text-brand underline underline-offset-2";

  return (
    <div className="space-y-4">
      <Erro mensagem={erro} />
      {justificando && (
        <Card titulo="Marcar como não se aplica">
          <p className="mb-2 text-sm text-text-muted">
            {justificando.nome}, {competenciaExtenso(justificando.competencia)}
          </p>
          <label className="block text-sm">
            Por que este documento não se aplica?
            <textarea
              autoFocus
              rows={2}
              maxLength={500}
              className="mt-1 w-full rounded border border-border bg-white px-2 py-1.5"
              value={justificativa}
              onChange={(e) => setJustificativa(e.target.value)}
            />
          </label>
          <div className="mt-2 flex gap-2">
            <Botao disabled={justificativa.trim().length < 5 || naoSeAplica.isPending} onClick={() => naoSeAplica.mutate(justificando)}>
              Marcar como não se aplica
            </Botao>
            <Botao variante="secundario" onClick={() => setJustificando(null)}>
              Cancelar
            </Botao>
          </div>
        </Card>
      )}
      <Card titulo={faltam === 0 ? `Todos os ${esperados} documentos resolvidos` : `Faltam ${faltam} de ${esperados} documentos`} semPadding>
        <div className="overflow-x-auto">
          <table className="condensado w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-2 text-left font-medium text-text-muted">Documento</th>
                {data.competencias.map((c) => (
                  <th key={c.competencia} className="min-w-44 border-l border-surface px-3 py-2 text-left font-medium text-text-muted">
                    {competenciaExtenso(c.competencia)}
                    {!c.editavel && <span className="block text-xs font-normal">enviado para conferência</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.tipos.map((t) => (
                <tr key={t.id} className="border-b border-surface last:border-0">
                  <th scope="row" className="max-w-64 px-4 py-2 text-left align-top font-medium">
                    {t.nome}
                  </th>
                  {data.competencias.map(({ competencia, editavel }) => {
                    const d = achar(competencia, t.id);
                    return (
                      <td key={competencia} className={`border-l border-surface px-3 py-2 align-top ${d ? "" : "bg-alert-soft"}`}>
                        {d?.arquivo && (
                          <button className={`${acao} block max-w-44 truncate`} title={d.arquivo} onClick={() => baixar(d)}>
                            ✔ {d.arquivo}
                          </button>
                        )}
                        {d?.nao_se_aplica && (
                          <span className="block" title={d.justificativa ?? ""}>
                            – Não se aplica
                            <span className="block text-xs text-text-muted">{d.justificativa}</span>
                          </span>
                        )}
                        {!d && <span className="block text-alert-ink">! Pendente</span>}
                        {editavel && (
                          <span className="mt-1 flex flex-wrap gap-x-3 text-xs">
                            <label className="cursor-pointer text-brand underline underline-offset-2 focus-within:outline-2">
                              {d?.arquivo ? "Substituir" : "Enviar arquivo"}
                              <input
                                type="file"
                                accept={FORMATOS}
                                className="sr-only"
                                aria-label={`Enviar ${t.nome} de ${competenciaExtenso(competencia)}`}
                                onChange={(e) => {
                                  const arquivo = e.target.files?.[0];
                                  e.target.value = "";
                                  if (arquivo) enviar.mutate({ competencia, tipo: t.id, arquivo });
                                }}
                              />
                            </label>
                            {!d?.nao_se_aplica && (
                              <button
                                className={acao}
                                onClick={() => {
                                  setJustificativa("");
                                  setJustificando({ competencia, tipo: t.id, nome: t.nome });
                                }}
                              >
                                Não se aplica
                              </button>
                            )}
                            {d && (
                              <button className="text-alert underline underline-offset-2" onClick={() => window.confirm("Remover este documento?") && excluir.mutate(d.id)}>
                                Remover
                              </button>
                            )}
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <p className="text-sm text-text-muted">Aceita PDF, XLSX, CSV, JPG e PNG de até 10 MB.</p>
    </div>
  );
}
