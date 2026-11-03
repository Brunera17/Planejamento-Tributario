import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import { Botao, Card, Erro, LegendaObrigatorio, Modal, Obrigatorio, Tabela } from "../components/ui";
import { competenciaExtenso } from "../lib/formato";
import { useNormas } from "./Normas";

type RegraSt = {
  id: number;
  uf: string;
  ncm: string;
  excecoes: string[];
  cest: string | null;
  segmento: string;
  item: string | null;
  descricao: string;
  vigencia_inicio: string;
  vigencia_fim: string | null;
  norma_id: number | null;
  revogada_por_id: number | null;
  norma: string | null;
  revogada_por: string | null;
  vigente_hoje: boolean;
};
type Consulta = {
  ncm: string;
  competencia: string;
  sujeito_st: boolean;
  regra: { segmento: string; item: string | null; ncm: string; fim: string | null; revogada_por: string | null } | null;
};

const LIMITE = 200;
const INICIO_PADRAO = "2000-01-01";
const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";
const ncmFmt = (n: string) => [n.slice(0, 4), n.slice(4, 6), n.slice(6, 8)].filter(Boolean).join(".");
const dataBr = (iso: string) => iso.split("-").reverse().join("/");
const semAcento = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const mesAtual = () => new Date().toISOString().slice(0, 7);

function vigencia(r: Pick<RegraSt, "vigencia_inicio" | "vigencia_fim">) {
  const desde = r.vigencia_inicio > INICIO_PADRAO ? `de ${dataBr(r.vigencia_inicio)}` : "";
  if (!r.vigencia_fim) return desde ? `${desde} em diante` : "Em vigor";
  return desde ? `${desde} a ${dataBr(r.vigencia_fim)}` : `Até ${dataBr(r.vigencia_fim)}`;
}

/** Mercadorias na substituição tributária do ICMS em SP, com a vigência de cada uma (Portaria CAT 68/2019 e revogações). */
export function SubstituicaoTributaria() {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const [editando, setEditando] = useState<RegraSt | null>(null);
  const [busca, setBusca] = useState("");
  const [segmento, setSegmento] = useState("");
  const [situacao, setSituacao] = useState<"vigentes" | "encerradas" | "todas">("vigentes");
  const { data: regras = [] } = useQuery({ queryKey: ["regras-st"], queryFn: async () => (await api.get<RegraSt[]>("/tabelas/st")).data });

  const segmentos = [...new Set(regras.map((r) => r.segmento))].sort((a, b) => a.localeCompare(b, "pt-BR"));
  const digitos = busca.replace(/\D/g, "");
  const termo = semAcento(busca.trim());
  const filtradas = regras.filter(
    (r) =>
      (!segmento || r.segmento === segmento) &&
      (situacao === "todas" || (situacao === "vigentes") === r.vigente_hoje) &&
      (!termo ||
        (digitos.length >= 2 && /^[\d.\s]+$/.test(busca.trim()) ? digitos.startsWith(r.ncm) || r.ncm.startsWith(digitos) : semAcento(r.descricao).includes(termo))),
  );

  return (
    <>
      {editando && <FormRegra inicial={editando} fechar={() => setEditando(null)} />}
      <ConsultaNcm />
      <Card
        titulo={`${filtradas.length} ${filtradas.length === 1 ? "mercadoria" : "mercadorias"} em SP`}
        adendo="Cada linha é uma posição, subposição ou NCM da Portaria CAT 68/2019: vale para todo código que começa assim."
        semPadding
        acoes={
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <select aria-label="Situação" className="rounded border border-border px-2 py-1" value={situacao} onChange={(e) => setSituacao(e.target.value as typeof situacao)}>
              <option value="vigentes">Na ST hoje</option>
              <option value="encerradas">Saíram da ST</option>
              <option value="todas">Todas</option>
            </select>
            <select aria-label="Segmento" className="max-w-56 rounded border border-border px-2 py-1" value={segmento} onChange={(e) => setSegmento(e.target.value)}>
              <option value="">Todos os segmentos</option>
              {segmentos.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <input
              aria-label="Buscar por NCM ou descrição"
              placeholder="NCM ou descrição"
              className="w-48 rounded border border-border px-2 py-1"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
          </div>
        }
      >
        {filtradas.length === 0 ? (
          <p className="p-4 text-sm text-text-muted">Nenhuma mercadoria com esse filtro. Troque a situação para “Todas” ou limpe a busca.</p>
        ) : (
          <Tabela cabecalho={["NCM", "CEST", "Segmento", "Descrição", "Vigência", ""]}>
            {filtradas.slice(0, LIMITE).map((r) => (
              <tr key={r.id} className="align-top">
                <td className="num px-4 py-2 font-medium whitespace-nowrap">
                  {ncmFmt(r.ncm)}
                  {r.excecoes.length > 0 && <span className="block text-xs font-normal text-text-muted">exceto {r.excecoes.map(ncmFmt).join(", ")}</span>}
                </td>
                <td className="num px-2 py-2 whitespace-nowrap">{r.cest ?? "–"}</td>
                <td className="px-2 py-2">
                  {r.segmento}
                  {r.item && <span className="block text-xs text-text-muted">item {r.item}</span>}
                </td>
                <td className="max-w-[60ch] px-2 py-2">{r.descricao}</td>
                <td className="px-2 py-2 whitespace-nowrap">
                  <span className={r.vigente_hoje ? "" : "text-text-muted"}>{vigencia(r)}</span>
                  {r.revogada_por && <span className="block text-xs text-text-muted">{r.revogada_por}</span>}
                </td>
                <td className="px-4 py-2 text-right">
                  {contador && (
                    <Botao variante="linha" onClick={() => setEditando(r)}>
                      Editar
                    </Botao>
                  )}
                </td>
              </tr>
            ))}
          </Tabela>
        )}
        {filtradas.length > LIMITE && (
          <p className="border-t border-surface px-4 py-2 text-sm text-text-muted">
            Mostrando {LIMITE} de {filtradas.length}. Escolha um segmento ou busque pelo NCM para ver o restante.
          </p>
        )}
      </Card>
    </>
  );
}

function ConsultaNcm() {
  const [ncm, setNcm] = useState("");
  const [competencia, setCompetencia] = useState(mesAtual());
  const digitos = ncm.replace(/\D/g, "");
  const { data: r } = useQuery({
    queryKey: ["st-consulta", digitos, competencia],
    enabled: digitos.length === 8 && /^\d{4}-\d{2}$/.test(competencia),
    queryFn: async () => (await api.get<Consulta>("/tabelas/st/consulta", { params: { ncm: digitos, competencia } })).data,
  });

  return (
    <Card titulo="Consultar um NCM">
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label>
          NCM
          <input inputMode="numeric" className={`${campo} num w-36`} placeholder="8708.99.90" value={ncm} onChange={(e) => setNcm(e.target.value)} />
        </label>
        <label>
          Competência
          <input type="month" className={`${campo} w-44`} value={competencia} onChange={(e) => setCompetencia(e.target.value)} />
        </label>
        {r && digitos.length === 8 && (
          <p className={`max-w-[70ch] rounded px-3 py-2 ${r.sujeito_st ? "bg-warning-soft text-warning-ink" : "bg-surface"}`} role="status">
            {r.sujeito_st ? (
              <>
                <strong>Na substituição tributária</strong> em {competenciaExtenso(r.competencia)}: {r.regra?.segmento}
                {r.regra?.item ? `, item ${r.regra.item}` : ""}.
              </>
            ) : r.regra ? (
              <>
                <strong>Fora da substituição tributária</strong> em {competenciaExtenso(r.competencia)}: a venda interna tem débito de ICMS normal. A ST de{" "}
                {r.regra.segmento.toLowerCase()} acabou em {dataBr(r.regra.fim!)}
                {r.regra.revogada_por ? `, pela ${r.regra.revogada_por}` : ""}.
              </>
            ) : (
              <>
                <strong>Fora da substituição tributária</strong>: o NCM não está na lista de SP.
              </>
            )}
          </p>
        )}
      </div>
    </Card>
  );
}

function FormRegra({ inicial, fechar }: { inicial: RegraSt; fechar: () => void }) {
  const qc = useQueryClient();
  const { data: normas = [] } = useNormas();
  const [f, setF] = useState({
    vigencia_inicio: inicial.vigencia_inicio,
    vigencia_fim: inicial.vigencia_fim ?? "",
    revogada_por_id: inicial.revogada_por_id ? String(inicial.revogada_por_id) : "",
    descricao: inicial.descricao,
    excecoes: inicial.excecoes.map(ncmFmt).join(", "),
  });
  const [erro, setErro] = useState<string | null>(null);
  const salvar = useMutation({
    mutationFn: () =>
      api.put(`/tabelas/st/${inicial.id}`, {
        uf: inicial.uf,
        ncm: inicial.ncm,
        cest: inicial.cest,
        segmento: inicial.segmento,
        item: inicial.item,
        norma_id: inicial.norma_id,
        descricao: f.descricao.trim(),
        excecoes: f.excecoes.split(",").map((x) => x.trim()).filter(Boolean),
        vigencia_inicio: f.vigencia_inicio,
        vigencia_fim: f.vigencia_fim || null,
        revogada_por_id: f.vigencia_fim && f.revogada_por_id ? Number(f.revogada_por_id) : null,
      }),
    onSuccess: () => {
      // a ST muda o ICMS das simulações: resultados e listas precisam recarregar
      qc.invalidateQueries();
      fechar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  function enviar(e: FormEvent) {
    e.preventDefault();
    if (!f.vigencia_inicio) return setErro("Informe o início da vigência");
    if (f.vigencia_fim && f.vigencia_fim < f.vigencia_inicio) return setErro("O fim da vigência não pode ser antes do início");
    if (f.descricao.trim().length < 3) return setErro("Informe a descrição da mercadoria");
    setErro(null);
    salvar.mutate();
  }

  return (
    <Modal
      aberto
      fechar={fechar}
      titulo={`NCM ${ncmFmt(inicial.ncm)}: ${inicial.segmento}`}
      descricao="A vigência decide em quais competências a venda interna sai com ST. Ao salvar, todas as simulações ficam desatualizadas."
      largura="max-w-2xl"
    >
      <form onSubmit={enviar} className="grid gap-3 text-sm sm:grid-cols-2">
        <label>
          Na ST desde
          <Obrigatorio />
          <input type="date" className={campo} value={f.vigencia_inicio} onChange={(e) => setF({ ...f, vigencia_inicio: e.target.value })} />
          <span className="mt-1 block text-xs text-text-muted">01/01/2000 quando a data de entrada não importa para o cálculo</span>
        </label>
        <label>
          Na ST até
          <input type="date" className={campo} value={f.vigencia_fim} onChange={(e) => setF({ ...f, vigencia_fim: e.target.value })} />
          <span className="mt-1 block text-xs text-text-muted">Último dia com ST; em branco enquanto continuar</span>
        </label>
        {f.vigencia_fim && (
          <label className="sm:col-span-2">
            Norma que tirou da ST
            <select className={campo} value={f.revogada_por_id} onChange={(e) => setF({ ...f, revogada_por_id: e.target.value })}>
              <option value="">Não informada</option>
              {normas
                .filter((n) => n.tributos.includes("ICMS"))
                .map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.titulo}
                  </option>
                ))}
            </select>
            <span className="mt-1 block text-xs text-text-muted">Falta a norma na lista? Inclua antes na aba Normas.</span>
          </label>
        )}
        <label className="sm:col-span-2">
          Descrição
          <Obrigatorio />
          <textarea className={campo} rows={2} value={f.descricao} onChange={(e) => setF({ ...f, descricao: e.target.value })} />
        </label>
        <label className="sm:col-span-2">
          Exceções
          <input className={`${campo} num`} placeholder="7325.91.00, 7325.99.10" value={f.excecoes} onChange={(e) => setF({ ...f, excecoes: e.target.value })} />
          <span className="mt-1 block text-xs text-text-muted">Códigos que começam com {ncmFmt(inicial.ncm)} mas ficam fora da ST, separados por vírgula</span>
        </label>
        <div className="space-y-2 sm:col-span-2">
          <Erro mensagem={erro} />
          <div className="flex items-center justify-between gap-2 border-t border-surface pt-3">
            <LegendaObrigatorio />
            <div className="flex gap-2">
              <Botao variante="secundario" onClick={fechar}>
                Cancelar
              </Botao>
              <Botao type="submit" disabled={salvar.isPending}>
                Salvar e desatualizar simulações
              </Botao>
            </div>
          </div>
        </div>
      </form>
    </Modal>
  );
}
