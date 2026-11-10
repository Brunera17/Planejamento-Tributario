import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, baixarArquivo, mensagemErro } from "../api/cliente";
import { Botao, Card, EnvioArquivo, Erro, Modal, Obrigatorio } from "../components/ui";
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
type Celula = { competencia: string; tipo: number; nome: string; editavel: boolean; doc?: Documento; modo?: "arquivo" | "nao-se-aplica" };
type Linha = { tipo: number; nome: string; competencias: string[] };

const FORMATOS = [".pdf", ".xml", ".txt", ".xlsx", ".xls", ".csv", ".zip", ".jpg", ".jpeg", ".png"];

/** Conferência de documentos: uma linha por documento, uma coluna por mês; cada célula abre o envio daquele documento. */
export function Documentos({ pid }: { pid: number }) {
  const [erro, setErro] = useState<string | null>(null);
  const [aberta, setAberta] = useState<Celula | null>(null);
  const [linha, setLinha] = useState<Linha | null>(null);
  const { data } = useQuery({
    queryKey: ["documentos", pid],
    queryFn: async () => (await api.get<Dados>(`/planejamentos/${pid}/documentos`)).data,
  });

  if (!data) return <p>Carregando…</p>;
  const esperados = data.tipos.length * data.competencias.length;
  const faltam = esperados - data.documentos.length;
  const achar = (c: string, t: number) => data.documentos.find((d) => d.competencia === c && d.tipo_documento_id === t);

  return (
    <div className="space-y-4">
      <Erro mensagem={erro} />
      {linha && <NaoSeAplicaLinha pid={pid} linha={linha} fechar={() => setLinha(null)} />}
      {aberta && <EnvioDocumento pid={pid} celula={aberta} fechar={() => setAberta(null)} falhou={(e) => setErro(mensagemErro(e))} />}
      <Card titulo={faltam === 0 ? `Todos os ${esperados} documentos resolvidos` : `Faltam ${faltam} de ${esperados} documentos`} semPadding>
        <div className="overflow-x-auto">
          <table className="condensado w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-2 text-left font-medium text-text-muted">Documento</th>
                {data.competencias.map((c) => (
                  <th key={c.competencia} className="min-w-40 border-l border-surface px-3 py-2 text-left font-medium text-text-muted">
                    {competenciaExtenso(c.competencia)}
                    {!c.editavel && <span className="block text-xs font-normal">enviado para conferência</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.tipos.map((t) => {
                // meses em que este documento ainda está pendente e dá para marcar
                const abertos = data.competencias.filter((c) => c.editavel && !achar(c.competencia, t.id)).map((c) => c.competencia);
                return (
                <tr key={t.id} className="border-b border-surface last:border-0">
                  <th scope="row" className="max-w-64 px-4 py-2 text-left align-middle font-medium">
                    {t.nome}
                    {abertos.length > 1 && (
                      <button
                        type="button"
                        className="block text-xs font-normal text-brand underline-offset-2 hover:underline"
                        onClick={() => setLinha({ tipo: t.id, nome: t.nome, competencias: abertos })}
                      >
                        Não se aplica nos {abertos.length} meses pendentes
                      </button>
                    )}
                  </th>
                  {data.competencias.map(({ competencia, editavel }) => {
                    const d = achar(competencia, t.id);
                    const celula = { competencia, tipo: t.id, nome: t.nome, editavel, doc: d };
                    return (
                      <td key={competencia} className={`border-l border-surface px-3 py-2 align-middle ${d ? "" : "bg-alert-soft"}`}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="min-w-0">
                            {d?.arquivo && (
                              <span className="block truncate text-success-ink" title={d.arquivo}>
                                Enviado
                                <span className="block truncate text-xs text-text-muted">{d.arquivo}</span>
                              </span>
                            )}
                            {d?.nao_se_aplica && (
                              <span className="block" title={d.justificativa ?? ""}>
                                Não se aplica
                                <span className="block truncate text-xs text-text-muted">{d.justificativa}</span>
                              </span>
                            )}
                            {!d && <span className="text-alert-ink">Pendente</span>}
                          </span>
                          <span className="flex shrink-0 gap-1">
                            <Botao
                              variante={!d && editavel ? "linha-destaque" : "linha"}
                              aria-label={`${d ? "Abrir" : "Enviar"} ${t.nome} de ${competenciaExtenso(competencia)}`}
                              onClick={() => setAberta(celula)}
                            >
                              {d ? "Abrir" : editavel ? "Enviar" : "Ver"}
                            </Botao>
                            {!d && editavel && (
                              <Botao
                                variante="linha"
                                title="Não se aplica"
                                aria-label={`Não se aplica: ${t.nome} de ${competenciaExtenso(competencia)}`}
                                onClick={() => setAberta({ ...celula, modo: "nao-se-aplica" })}
                              >
                                N/A
                              </Botao>
                            )}
                          </span>
                        </div>
                      </td>
                    );
                  })}
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function EnvioDocumento({ pid, celula, fechar, falhou }: { pid: number; celula: Celula; fechar: () => void; falhou: (e: unknown) => void }) {
  const qc = useQueryClient();
  const d = celula.doc;
  const [modo, setModo] = useState<"arquivo" | "nao-se-aplica">(celula.modo ?? (d?.nao_se_aplica ? "nao-se-aplica" : "arquivo"));
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [justificativa, setJustificativa] = useState(d?.justificativa ?? "");
  const [removendo, setRemovendo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  function concluido() {
    qc.invalidateQueries({ queryKey: ["documentos", pid] });
    qc.invalidateQueries({ queryKey: ["planejamento", String(pid)] });
    qc.invalidateQueries({ queryKey: ["progresso", pid] });
    fechar();
  }
  const opcoes = { onSuccess: concluido, onError: (e: unknown) => setErro(mensagemErro(e)) };
  const enviar = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("arquivo", arquivos[0]);
      return api.post(`/planejamentos/${pid}/documentos/${celula.competencia}/${celula.tipo}`, fd);
    },
    ...opcoes,
  });
  const naoSeAplica = useMutation({
    mutationFn: () => api.put(`/planejamentos/${pid}/documentos/${celula.competencia}/${celula.tipo}/nao-se-aplica`, { justificativa: justificativa.trim() }),
    ...opcoes,
  });
  const excluir = useMutation({ mutationFn: () => api.delete(`/planejamentos/${pid}/documentos/${d!.id}`), ...opcoes });

  const pronto = modo === "arquivo" ? arquivos.length === 1 : justificativa.trim().length >= 5;
  const titulo = `${celula.nome}`;

  return (
    <Modal aberto fechar={fechar} titulo={titulo} descricao={competenciaExtenso(celula.competencia)}>
      <div className="space-y-4 text-sm">
        {d && (
          <div className="flex items-center justify-between gap-3 rounded border border-surface bg-bg px-3 py-2">
            <span className="min-w-0">
              <span className="block font-medium">{d.arquivo ? "Arquivo enviado" : "Marcado como não se aplica"}</span>
              <span className="block truncate text-text-muted">{d.arquivo ?? d.justificativa}</span>
            </span>
            <span className="flex shrink-0 gap-1.5">
              {d.arquivo && (
                <Botao variante="linha" onClick={() => baixarArquivo(`/planejamentos/${pid}/documentos/${d.id}/download`, d.arquivo ?? "documento").catch(falhou)}>
                  Baixar
                </Botao>
              )}
              {celula.editavel && (
                <Botao variante="linha-perigo" onClick={() => setRemovendo(true)}>
                  Remover
                </Botao>
              )}
            </span>
          </div>
        )}
        {removendo && (
          <div className="flex items-center justify-between gap-3 rounded border border-alert/40 bg-alert-soft px-3 py-2 text-alert-ink">
            <span>O documento volta a ficar pendente. Remover?</span>
            <span className="flex gap-1.5">
              <Botao variante="linha" onClick={() => setRemovendo(false)}>
                Voltar
              </Botao>
              <Botao variante="linha-perigo" disabled={excluir.isPending} onClick={() => excluir.mutate()}>
                Remover documento
              </Botao>
            </span>
          </div>
        )}
        {celula.editavel ? (
          <>
            <fieldset className="flex flex-wrap gap-4">
              <legend className="sr-only">O que fazer</legend>
              <label className="flex items-center gap-1.5">
                <input type="radio" name="modo-documento" checked={modo === "arquivo"} onChange={() => setModo("arquivo")} />
                {d?.arquivo ? "Substituir o arquivo" : "Enviar arquivo"}
              </label>
              <label className="flex items-center gap-1.5">
                <input type="radio" name="modo-documento" checked={modo === "nao-se-aplica"} onChange={() => setModo("nao-se-aplica")} />
                Não se aplica a este mês
              </label>
            </fieldset>
            {modo === "arquivo" ? (
              <EnvioArquivo formatos={FORMATOS} arquivos={arquivos} aoEscolher={(fs) => setArquivos(fs.slice(0, 1))} />
            ) : (
              <label className="block">
                Por que este documento não se aplica?<Obrigatorio />
                <textarea
                  autoFocus
                  rows={3}
                  maxLength={500}
                  placeholder="Ex.: a empresa não teve funcionários neste mês"
                  className="mt-1 w-full rounded border border-border bg-white px-2 py-1.5"
                  value={justificativa}
                  onChange={(e) => setJustificativa(e.target.value)}
                />
              </label>
            )}
            <p className="text-xs text-text-muted">Até 10 MB por arquivo.</p>
            <Erro mensagem={erro} />
            <div className="flex justify-end gap-2 border-t border-surface pt-3">
              <Botao variante="secundario" onClick={fechar}>
                Cancelar
              </Botao>
              <Botao disabled={!pronto || enviar.isPending || naoSeAplica.isPending} onClick={() => (modo === "arquivo" ? enviar.mutate() : naoSeAplica.mutate())}>
                {modo === "arquivo" ? "Enviar documento" : "Marcar como não se aplica"}
              </Botao>
            </div>
          </>
        ) : (
          <p className="text-text-muted">Este mês foi enviado para conferência e está só para consulta.</p>
        )}
      </div>
    </Modal>
  );
}

/** Mesma justificativa para todos os meses pendentes de um documento (ex.: tarifas de marketplace numa lanchonete). */
function NaoSeAplicaLinha({ pid, linha, fechar }: { pid: number; linha: Linha; fechar: () => void }) {
  const qc = useQueryClient();
  const [justificativa, setJustificativa] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const marcar = useMutation({
    mutationFn: async () => {
      for (const c of linha.competencias)
        await api.put(`/planejamentos/${pid}/documentos/${c}/${linha.tipo}/nao-se-aplica`, { justificativa: justificativa.trim(), somente_pendente: true });
    },
    onError: (e) => setErro(mensagemErro(e)),
    onSettled: (_r, e) => {
      // mesmo com erro no meio, os meses já marcados aparecem
      qc.invalidateQueries({ queryKey: ["documentos", pid] });
      qc.invalidateQueries({ queryKey: ["planejamento", String(pid)] });
      qc.invalidateQueries({ queryKey: ["progresso", pid] });
      if (!e) fechar();
    },
  });
  return (
    <Modal aberto fechar={fechar} titulo={linha.nome} descricao={`Não se aplica em ${linha.competencias.map(competenciaExtenso).join(", ")}`}>
      <div className="space-y-4 text-sm">
        <label className="block">
          Por que este documento não se aplica?<Obrigatorio />
          <textarea
            autoFocus
            rows={3}
            maxLength={500}
            placeholder="Ex.: a empresa não vende por marketplace"
            className="mt-1 w-full rounded border border-border bg-white px-2 py-1.5"
            value={justificativa}
            onChange={(e) => setJustificativa(e.target.value)}
          />
        </label>
        <Erro mensagem={erro} />
        <div className="flex justify-end gap-2 border-t border-surface pt-3">
          <Botao variante="secundario" onClick={fechar}>
            Cancelar
          </Botao>
          <Botao disabled={justificativa.trim().length < 5 || marcar.isPending} onClick={() => marcar.mutate()}>
            Marcar {linha.competencias.length} meses
          </Botao>
        </div>
      </div>
    </Modal>
  );
}
