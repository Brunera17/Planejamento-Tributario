import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, baixarArquivo, mensagemErro } from "../api/cliente";
import { Botao, Card, EnvioArquivo, Erro, Modal, Obrigatorio, Progresso, useProgresso } from "../components/ui";
import { brl, competenciaExtenso } from "../lib/formato";

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
      {data.competencias.some((c) => c.editavel) && <EnvioEmLote pid={pid} dados={data} />}
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
  const progresso = useProgresso();
  const enviar = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("arquivo", arquivos[0]);
      return progresso.enviar(0, 1, (cfg) => api.post(`/planejamentos/${pid}/documentos/${celula.competencia}/${celula.tipo}`, fd, cfg));
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
              <>
                <EnvioArquivo formatos={FORMATOS} arquivos={arquivos} aoEscolher={(fs) => setArquivos(fs.slice(0, 1))} />
                {enviar.isPending && <Progresso pct={progresso.pct} acao="Enviando o arquivo" />}
              </>
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
            <p className="text-xs text-text-muted">Até 30 MB por arquivo.</p>
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

type Sugestao = {
  arquivo: string;
  tipo_documento_id?: number | null;
  competencia?: string | null;
  motivo?: string;
  competencias_no_arquivo?: string[];
  cobre_tipos?: number[];
  despesas?: PreviaDespesas | null;
  erro?: string;
};
/** O que a importação da planilha de despesas gravaria na aba Despesas. */
type PreviaDespesas = {
  meses: string[];
  meses_fechados: string[];
  valores: number;
  outras: number;
  total: number;
  folha: number; // folha e pró-labore: vão para a aba Faturamento, compras e folha
  substitui_digitados: number;
  avisos: string[];
};
type ItemLote = {
  file: File;
  tipo: number | null;
  competencia: string | null;
  motivo: string;
  meses: string[];
  erro?: string;
  cobre: number[]; // planilha de despesas: documentos que o cliente responde nela
  marcarCobertos: boolean;
  despesas: PreviaDespesas | null;
  importarDespesas: boolean;
};

/** Vários arquivos de uma vez: o servidor sugere tipo e mês de cada um, a pessoa confere e envia pela rota de sempre. */
function EnvioEmLote({ pid, dados }: { pid: number; dados: Dados }) {
  const qc = useQueryClient();
  const [itens, setItens] = useState<ItemLote[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const abertos = dados.competencias.filter((c) => c.editavel).map((c) => c.competencia);

  const leitura = useProgresso();
  const envio = useProgresso();
  const classificar = useMutation({
    mutationFn: async (files: File[]) => {
      // um arquivo por requisição: o lote inteiro numa só passaria de centenas de MB
      const r: Sugestao[] = [];
      for (const [k, f] of files.entries()) {
        const fd = new FormData();
        fd.append("arquivos", f);
        r.push(...(await leitura.enviar(k, files.length, (cfg) => api.post<Sugestao[]>(`/planejamentos/${pid}/documentos/classificar`, fd, cfg))).data);
      }
      return files.map((file, i): ItemLote => {
        const s = r[i];
        const comp = s.competencia && abertos.includes(s.competencia) ? s.competencia : null;
        const cobre = s.cobre_tipos ?? [];
        const despesas = s.despesas ?? null;
        const temValores = !!despesas && despesas.valores + despesas.outras + despesas.folha > 0;
        return {
          file, tipo: s.tipo_documento_id ?? null, competencia: comp, motivo: s.motivo ?? "", meses: s.competencias_no_arquivo ?? [], erro: s.erro,
          cobre, marcarCobertos: cobre.length > 0, despesas: temValores ? despesas : null, importarDespesas: temValores,
        };
      });
    },
    onSuccess: (novos) => setItens((atuais) => [...atuais, ...novos]),
    onError: (e) => setErro(mensagemErro(e)),
  });

  const destino = (i: ItemLote) => `${i.competencia}|${i.tipo}`;
  const contagem = new Map<string, number>();
  itens.forEach((i) => i.tipo && i.competencia && contagem.set(destino(i), (contagem.get(destino(i)) ?? 0) + 1));
  const repetido = (i: ItemLote) => (contagem.get(destino(i)) ?? 0) > 1;
  const prontos = itens.filter((i) => i.motivo && i.tipo && i.competencia && !repetido(i));
  const vaoReceberArquivo = new Set(prontos.map(destino));
  /** Pendências que a planilha de despesas resolve: os documentos que ela cobre, nos meses abertos que ela traz,
   * fora a própria célula do arquivo, o que já foi resolvido e o que outro arquivo do lote vai preencher. */
  const cobertos = (i: ItemLote) => {
    const meses = i.meses.filter((m) => abertos.includes(m));
    return (meses.length ? meses : i.competencia ? [i.competencia] : []).flatMap((competencia) =>
      i.cobre
        .filter((tipo) => !(competencia === i.competencia && tipo === i.tipo))
        .filter((tipo) => !dados.documentos.some((d) => d.competencia === competencia && d.tipo_documento_id === tipo))
        .filter((tipo) => !vaoReceberArquivo.has(`${competencia}|${tipo}`))
        .map((tipo) => ({ competencia, tipo })),
    );
  };
  const nomeTipo = (id: number) => dados.tipos.find((t) => t.id === id)?.nome ?? "";
  const meses = (cs: { competencia: string }[]) => [...new Set(cs.map((c) => c.competencia))].map(competenciaExtenso).join(", ");
  const textoCobertos = (cob: { competencia: string; tipo: number }[], tipoDoArquivo: number | null) => {
    const outros = cob.filter((c) => c.tipo !== tipoDoArquivo);
    const propria = cob.filter((c) => c.tipo === tipoDoArquivo);
    const partes = [];
    if (outros.length) partes.push(`${[...new Set(outros.map((c) => c.tipo))].map(nomeTipo).join("; ")} em ${meses(outros)}`);
    if (propria.length) partes.push(`a própria planilha também em ${meses(propria)}`);
    return `Marcar como não se aplica, informado na planilha: ${partes.join("; e ")}`;
  };

  const enviar = useMutation({
    mutationFn: async () => {
      const falhas = new Map<File, string>();
      for (const [k, i] of prontos.entries()) {
        const fd = new FormData();
        fd.append("arquivo", i.file);
        try {
          await envio.enviar(k, prontos.length, (cfg) => api.post(`/planejamentos/${pid}/documentos/${i.competencia}/${i.tipo}`, fd, cfg));
          if (i.marcarCobertos)
            for (const c of cobertos(i))
              await api.put(`/planejamentos/${pid}/documentos/${c.competencia}/${c.tipo}/nao-se-aplica`, {
                justificativa: `Informado na planilha de despesas (${i.file.name})`.slice(0, 500),
                somente_pendente: true,
              });
          if (i.importarDespesas) {
            const pl = new FormData();
            pl.append("arquivo", i.file);
            await api.post(`/planejamentos/${pid}/despesas/planilha`, pl);
          }
        } catch (e) {
          falhas.set(i.file, mensagemErro(e));
        }
      }
      return falhas;
    },
    onSuccess: (falhas) => {
      const enviados = new Set(prontos.map((i) => i.file).filter((f) => !falhas.has(f)));
      setItens((atuais) => atuais.filter((i) => !enviados.has(i.file)).map((i) => (falhas.has(i.file) ? { ...i, erro: falhas.get(i.file) } : i)));
      qc.invalidateQueries({ queryKey: ["documentos", pid] });
      qc.invalidateQueries({ queryKey: ["planejamento", String(pid)] });
      qc.invalidateQueries({ queryKey: ["progresso", pid] });
      qc.invalidateQueries({ queryKey: ["levantamento", pid] });
      qc.invalidateQueries({ queryKey: ["coleta", pid] }); // folha e pró-labore da planilha de despesas
    },
  });

  const mudar = (idx: number, parte: Partial<ItemLote>) => setItens((atuais) => atuais.map((i, j) => (j === idx ? { ...i, ...parte } : i)));
  const campo = "w-full rounded border border-border bg-white px-1.5 py-1";

  return (
    <Card titulo="Enviar vários arquivos" adendo="O sistema sugere o documento e o mês de cada arquivo; confira antes de enviar. Até 30 MB por arquivo.">
      <div className="space-y-3 text-sm">
        <EnvioArquivo formatos={FORMATOS} multiplo arquivos={[]} aoEscolher={(fs) => { setErro(null); classificar.mutate(fs.slice(0, 30)); }} />
        {classificar.isPending && <Progresso pct={leitura.pct} />}
        {enviar.isPending && <Progresso pct={envio.pct} acao="Enviando os arquivos" />}
        <Erro mensagem={erro} />
        {itens.length > 0 && (
          <>
            <table className="condensado w-full border-collapse">
              <thead>
                <tr className="border-b border-border text-left text-text-muted">
                  <th className="py-1.5 pr-3 font-medium">Arquivo</th>
                  <th className="py-1.5 pr-3 font-medium">Documento</th>
                  <th className="py-1.5 pr-3 font-medium">Mês</th>
                  <th className="py-1.5 font-medium"><span className="sr-only">Remover</span></th>
                </tr>
              </thead>
              <tbody>
                {itens.map((i, idx) => {
                  const ja = i.tipo && i.competencia && dados.documentos.some((d) => d.competencia === i.competencia && d.tipo_documento_id === i.tipo);
                  const outros = i.cobre.length ? [] : i.meses.filter((m) => m !== i.competencia);
                  const cob = i.cobre.length ? cobertos(i) : [];
                  return (
                    <tr key={idx} className="border-b border-surface align-top last:border-0">
                      <td className="max-w-64 py-1.5 pr-3">
                        <span className="block truncate font-medium" title={i.file.name}>{i.file.name}</span>
                        {i.erro ? (
                          <span className="block text-xs text-alert-ink">{i.erro}</span>
                        ) : (
                          <span className="block text-xs text-text-muted">{i.motivo}</span>
                        )}
                        {repetido(i) && <span className="block text-xs text-alert-ink">Outro arquivo vai para o mesmo documento e mês</span>}
                        {!repetido(i) && ja && <span className="block text-xs text-alert-ink">Substitui o que já foi enviado</span>}
                        {outros.length > 0 && <span className="block text-xs text-alert-ink">Também tem {outros.map(competenciaExtenso).join(", ")}</span>}
                        {cob.length > 0 && (
                          <label className="mt-1 flex items-start gap-1.5 text-xs">
                            <input type="checkbox" className="mt-0.5" checked={i.marcarCobertos} onChange={(e) => mudar(idx, { marcarCobertos: e.target.checked })} />
                            <span>{textoCobertos(cob, i.tipo)}</span>
                          </label>
                        )}
                        {i.despesas && (
                          <label className="mt-1 flex items-start gap-1.5 text-xs">
                            <input type="checkbox" className="mt-0.5" checked={i.importarDespesas} onChange={(e) => mudar(idx, { importarDespesas: e.target.checked })} />
                            <span>
                              Importar os valores na aba Despesas: {i.despesas.valores + i.despesas.outras} valores em{" "}
                              {i.despesas.meses.map(competenciaExtenso).join(", ")}, total {brl(i.despesas.total)}
                              {i.despesas.folha > 0 && `; e ${i.despesas.folha} de folha/pró-labore na aba Faturamento, compras e folha`}
                              {i.despesas.substitui_digitados > 0 && (
                                <span className="block text-alert-ink">Substitui {i.despesas.substitui_digitados} valores já informados com outro valor</span>
                              )}
                              {i.despesas.meses_fechados.length > 0 && (
                                <span className="block text-alert-ink">
                                  Fora: {i.despesas.meses_fechados.map(competenciaExtenso).join(", ")} (enviado para conferência)
                                </span>
                              )}
                              {i.despesas.avisos.map((a) => (
                                <span key={a} className="block text-text-muted">{a}</span>
                              ))}
                            </span>
                          </label>
                        )}
                      </td>
                      <td className="min-w-56 py-1.5 pr-3">
                        <select aria-label={`Documento de ${i.file.name}`} className={campo} disabled={!i.motivo} value={i.tipo ?? ""}
                          onChange={(e) => mudar(idx, { tipo: e.target.value ? Number(e.target.value) : null })}>
                          <option value="">Escolha…</option>
                          {dados.tipos.map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}
                        </select>
                      </td>
                      <td className="min-w-36 py-1.5 pr-3">
                        <select aria-label={`Mês de ${i.file.name}`} className={campo} disabled={!i.motivo} value={i.competencia ?? ""}
                          onChange={(e) => mudar(idx, { competencia: e.target.value || null })}>
                          <option value="">Escolha…</option>
                          {abertos.map((c) => <option key={c} value={c}>{competenciaExtenso(c)}</option>)}
                        </select>
                      </td>
                      <td className="py-1.5">
                        <Botao variante="linha" aria-label={`Tirar ${i.file.name} da lista`} onClick={() => setItens((a) => a.filter((_, j) => j !== idx))}>
                          Tirar
                        </Botao>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="flex items-center justify-end gap-3 border-t border-surface pt-3">
              {prontos.length < itens.length && <span className="text-xs text-text-muted">Só vão os arquivos com documento e mês escolhidos.</span>}
              <Botao variante="secundario" onClick={() => setItens([])}>Limpar</Botao>
              <Botao disabled={!prontos.length || enviar.isPending} onClick={() => enviar.mutate()}>
                {enviar.isPending ? "Enviando…" : `Enviar ${prontos.length} ${prontos.length === 1 ? "arquivo" : "arquivos"}`}
              </Botao>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}
