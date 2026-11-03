import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import { Botao, Card, Erro, LegendaObrigatorio, Modal, Obrigatorio, Tabela } from "../components/ui";
import { dataHora } from "../lib/formato";

export type Norma = {
  id: number;
  codigo: string;
  titulo: string;
  apelido: string | null;
  esfera: "FEDERAL" | "ESTADUAL" | "CONVENIO";
  uf: string | null;
  tributos: string[];
  resumo: string;
  uso_no_calculo: string | null;
  url: string;
  situacao: "VIGENTE" | "ALTERADA" | "REVOGADA";
  alterado_em: string | null;
  alterado_por_nome: string | null;
  regras_st: number;
  regras_st_encerradas: number;
};

const TRIBUTOS = ["ICMS", "PIS", "COFINS", "CBS", "IBS"] as const;
const FILTROS = [
  { id: "", rotulo: "Todas" },
  { id: "ICMS", rotulo: "ICMS" },
  { id: "PIS", rotulo: "PIS e COFINS" },
  { id: "CBS", rotulo: "CBS e IBS" },
];
const ESFERA: Record<Norma["esfera"], string> = { FEDERAL: "Federal", ESTADUAL: "Estadual", CONVENIO: "Convênio Confaz" };
const SITUACAO: Record<Norma["situacao"], { rotulo: string; classe: string }> = {
  VIGENTE: { rotulo: "Vigente", classe: "bg-success-soft text-success-ink" },
  ALTERADA: { rotulo: "Alterada", classe: "bg-warning-soft text-warning-ink" },
  REVOGADA: { rotulo: "Revogada", classe: "bg-surface text-text-muted" },
};
const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";
const semAcento = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export const useNormas = () => useQuery({ queryKey: ["normas"], queryFn: async () => (await api.get<Norma[]>("/tabelas/normas")).data });

/** Biblioteca de normas: o que cada uma diz, onde entra no cálculo e o link do texto oficial. */
export function Normas() {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const [editando, setEditando] = useState<Norma | "nova" | null>(null);
  const [busca, setBusca] = useState("");
  const [tributo, setTributo] = useState("");
  const { data: normas = [] } = useNormas();

  const termo = semAcento(busca.trim());
  const visiveis = normas.filter(
    (n) =>
      (!tributo || n.tributos.includes(tributo) || (tributo === "PIS" && n.tributos.includes("COFINS")) || (tributo === "CBS" && n.tributos.includes("IBS"))) &&
      (!termo || semAcento([n.titulo, n.apelido, n.resumo, n.uso_no_calculo].join(" ")).includes(termo)),
  );

  return (
    <>
      {editando && <FormNorma inicial={editando === "nova" ? null : editando} fechar={() => setEditando(null)} />}
      <Card
        titulo={`${visiveis.length} ${visiveis.length === 1 ? "norma" : "normas"}`}
        adendo="O texto completo fica no site oficial; aqui ficam o resumo e o uso no cálculo."
        semPadding
        acoes={
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <div className="flex overflow-hidden rounded border border-border" role="group" aria-label="Filtrar por tributo">
              {FILTROS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  aria-pressed={tributo === f.id}
                  onClick={() => setTributo(f.id)}
                  className={`px-2.5 py-1 ${tributo === f.id ? "bg-brand text-white" : "bg-white hover:bg-highlight"}`}
                >
                  {f.rotulo}
                </button>
              ))}
            </div>
            <input
              aria-label="Buscar norma"
              placeholder="Buscar: Kandir, monofásico, 313-O…"
              className="w-60 rounded border border-border px-2 py-1"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
            {contador && <Botao onClick={() => setEditando("nova")}>Nova norma</Botao>}
          </div>
        }
      >
        {visiveis.length === 0 ? (
          <p className="p-4 text-sm text-text-muted">Nenhuma norma com esse filtro. Limpe a busca ou escolha outro tributo.</p>
        ) : (
          <Tabela cabecalho={["Norma", "Tributos", "O que diz", "Situação", ""]}>
            {visiveis.map((n) => (
              <tr key={n.id} className="align-top">
                <td className="w-64 px-4 py-2.5">
                  <a href={n.url} target="_blank" rel="noreferrer" className="font-medium text-brand underline-offset-2 hover:underline">
                    {n.titulo}
                  </a>
                  {n.apelido && <span className="block text-text-muted">{n.apelido}</span>}
                  <span className="block text-xs text-text-muted">
                    {ESFERA[n.esfera]}
                    {n.uf ? ` (${n.uf})` : ""}
                  </span>
                </td>
                <td className="px-2 py-2.5 whitespace-nowrap">{n.tributos.join(", ")}</td>
                <td className="max-w-[70ch] px-2 py-2.5">
                  <p>{n.resumo}</p>
                  {n.uso_no_calculo && (
                    <p className="mt-1 border-l-2 border-brand pl-2 text-text-muted">
                      <span className="font-medium text-text">No cálculo:</span> {n.uso_no_calculo}
                    </p>
                  )}
                  {n.alterado_por_nome && n.alterado_em && (
                    <p className="mt-1 text-xs text-text-muted">
                      Atualizada por {n.alterado_por_nome} em {dataHora(n.alterado_em)}
                    </p>
                  )}
                </td>
                <td className="px-2 py-2.5">
                  <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${SITUACAO[n.situacao].classe}`}>{SITUACAO[n.situacao].rotulo}</span>
                </td>
                <td className="px-4 py-2.5 text-right">
                  {contador && (
                    <Botao variante="linha" onClick={() => setEditando(n)}>
                      Editar
                    </Botao>
                  )}
                </td>
              </tr>
            ))}
          </Tabela>
        )}
      </Card>
    </>
  );
}

function FormNorma({ inicial, fechar }: { inicial: Norma | null; fechar: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    titulo: inicial?.titulo ?? "",
    apelido: inicial?.apelido ?? "",
    esfera: inicial?.esfera ?? "ESTADUAL",
    uf: inicial?.uf ?? "SP",
    tributos: inicial?.tributos ?? ["ICMS"],
    resumo: inicial?.resumo ?? "",
    uso_no_calculo: inicial?.uso_no_calculo ?? "",
    url: inicial?.url ?? "",
    situacao: inicial?.situacao ?? "VIGENTE",
  });
  const [erro, setErro] = useState<string | null>(null);
  const salvar = useMutation({
    mutationFn: () => {
      const corpo = { ...f, apelido: f.apelido.trim() || null, uso_no_calculo: f.uso_no_calculo.trim() || null, uf: f.esfera === "ESTADUAL" ? f.uf : null };
      return inicial ? api.put(`/tabelas/normas/${inicial.id}`, corpo) : api.post("/tabelas/normas", corpo);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["normas"] });
      fechar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  function enviar(e: FormEvent) {
    e.preventDefault();
    if (f.titulo.trim().length < 3) return setErro("Informe o tipo e o número da norma, como em “Decreto 45.490/2000”");
    if (!f.tributos.length) return setErro("Marque ao menos um tributo");
    if (f.resumo.trim().length < 10) return setErro("Escreva o resumo: o que a norma diz");
    if (!/^https?:\/\//.test(f.url.trim())) return setErro("Cole o link do texto oficial, começando com https://");
    setErro(null);
    salvar.mutate();
  }

  const marcar = (t: string) => setF({ ...f, tributos: f.tributos.includes(t) ? f.tributos.filter((x) => x !== t) : [...f.tributos, t] });

  return (
    <Modal aberto fechar={fechar} titulo={inicial ? `Editar ${inicial.titulo}` : "Nova norma"} largura="max-w-2xl">
      <form onSubmit={enviar} className="grid gap-3 text-sm sm:grid-cols-3">
        <label className="sm:col-span-2">
          Norma
          <Obrigatorio />
          <input autoFocus className={campo} maxLength={160} placeholder="Ex.: Portaria SRE 34/2026 (SP)" value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} />
        </label>
        <label>
          Apelido
          <input className={campo} maxLength={80} placeholder="Ex.: Lei Kandir" value={f.apelido} onChange={(e) => setF({ ...f, apelido: e.target.value })} />
        </label>
        <label>
          Esfera
          <select className={campo} value={f.esfera} onChange={(e) => setF({ ...f, esfera: e.target.value as Norma["esfera"] })}>
            {Object.entries(ESFERA).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        {f.esfera === "ESTADUAL" && (
          <label>
            UF
            <input className={`${campo} uppercase`} maxLength={2} value={f.uf} onChange={(e) => setF({ ...f, uf: e.target.value.toUpperCase() })} />
          </label>
        )}
        <label>
          Situação
          <select className={campo} value={f.situacao} onChange={(e) => setF({ ...f, situacao: e.target.value as Norma["situacao"] })}>
            {Object.entries(SITUACAO).map(([k, v]) => (
              <option key={k} value={k}>
                {v.rotulo}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="sm:col-span-3">
          <legend>
            Tributos
            <Obrigatorio />
          </legend>
          <div className="mt-1 flex flex-wrap gap-3">
            {TRIBUTOS.map((t) => (
              <label key={t} className="flex items-center gap-1.5">
                <input type="checkbox" checked={f.tributos.includes(t)} onChange={() => marcar(t)} />
                {t}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="sm:col-span-3">
          O que diz
          <Obrigatorio />
          <textarea className={campo} rows={3} value={f.resumo} onChange={(e) => setF({ ...f, resumo: e.target.value })} />
        </label>
        <label className="sm:col-span-3">
          Uso no cálculo
          <textarea
            className={campo}
            rows={2}
            placeholder="Deixe em branco se a norma é só de consulta"
            value={f.uso_no_calculo}
            onChange={(e) => setF({ ...f, uso_no_calculo: e.target.value })}
          />
        </label>
        <label className="sm:col-span-3">
          Link do texto oficial
          <Obrigatorio />
          <input className={campo} maxLength={300} placeholder="https://legislacao.fazenda.sp.gov.br/…" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} />
        </label>
        <div className="space-y-2 sm:col-span-3">
          <Erro mensagem={erro} />
          <div className="flex items-center justify-between gap-2 border-t border-surface pt-3">
            <LegendaObrigatorio />
            <div className="flex gap-2">
              <Botao variante="secundario" onClick={fechar}>
                Cancelar
              </Botao>
              <Botao type="submit" disabled={salvar.isPending}>
                {inicial ? "Salvar norma" : "Incluir norma"}
              </Botao>
            </div>
          </div>
        </div>
      </form>
    </Modal>
  );
}
