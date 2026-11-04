import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import { Botao, Card, Erro, LegendaObrigatorio, Modal, Obrigatorio, Tabela } from "../components/ui";

type Regra = {
  id: number;
  ncm: string;
  excecoes: string[];
  anexo: string;
  item: string | null;
  descricao: string;
  reducao: number;
  condicao: string | null;
  cst: string;
  cclass_trib: string | null;
  vigencia_fim: string | null;
};
type Consulta = { ncm: string; reducao: { anexo: string; item: string | null; descricao: string; reducao: number; condicao: string | null } | null };

const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";
const ncmFmt = (n: string) => [n.slice(0, 4), n.slice(4, 6), n.slice(6, 8)].filter(Boolean).join(".");
const efeito = (r: number) => (Number(r) >= 1 ? "Alíquota zero" : `Redução de ${Math.round(Number(r) * 100)}%`);
const semAcento = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** Reduções de CBS e IBS por NCM dos anexos da LC 214/2025, usadas na projeção da Reforma. */
export function ReducoesReforma() {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const [editando, setEditando] = useState<Regra | "nova" | null>(null);
  const [anexo, setAnexo] = useState("");
  const [busca, setBusca] = useState("");
  const { data: regras = [] } = useQuery({ queryKey: ["reforma-reducoes"], queryFn: async () => (await api.get<Regra[]>("/tabelas/reforma-reducoes")).data });

  const anexos = [...new Set(regras.map((r) => r.anexo))];
  const digitos = busca.replace(/\D/g, "");
  const termo = semAcento(busca.trim());
  const visiveis = regras.filter(
    (r) =>
      (!anexo || r.anexo === anexo) &&
      (!termo || (/^[\d.\s]+$/.test(busca.trim()) ? digitos.startsWith(r.ncm) || r.ncm.startsWith(digitos) : semAcento(r.descricao).includes(termo))),
  );

  return (
    <>
      {editando && <FormRegra inicial={editando === "nova" ? null : editando} fechar={() => setEditando(null)} />}
      <ConsultaNcm />
      <Card
        titulo={`${visiveis.length} ${visiveis.length === 1 ? "código" : "códigos"} com redução`}
        adendo="LC 214/2025: cada linha vale para todo NCM que começa assim. Quando o NCM está em dois anexos, vale o benefício maior."
        semPadding
        acoes={
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <select aria-label="Anexo" className="rounded border border-border px-2 py-1" value={anexo} onChange={(e) => setAnexo(e.target.value)}>
              <option value="">Todos os anexos</option>
              {anexos.map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
            <input
              aria-label="Buscar por NCM ou descrição"
              placeholder="NCM ou descrição"
              className="w-48 rounded border border-border px-2 py-1"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
            {contador && <Botao onClick={() => setEditando("nova")}>Nova redução</Botao>}
          </div>
        }
      >
        <p className="max-w-[90ch] px-4 pt-3 text-sm text-text-muted">
          Carregados os anexos de mercadorias do varejo: I (cesta básica) e XV (hortícolas, frutas e ovos), com alíquota zero; VII (alimentos) e VIII (higiene e
          limpeza), com redução de 60%. Dispositivos médicos, acessibilidade, nutrição especial, insumos agropecuários e medicamentos podem ser incluídos aqui.
        </p>
        <Tabela cabecalho={["NCM", "Anexo", "Produto", "Efeito", "Requisito", ""]}>
          {visiveis.map((r) => (
            <tr key={r.id} className="align-top">
              <td className="num px-4 py-2 font-medium whitespace-nowrap">
                {ncmFmt(r.ncm)}
                {r.excecoes.length > 0 && <span className="block text-xs font-normal text-text-muted">exceto {r.excecoes.map(ncmFmt).join(", ")}</span>}
              </td>
              <td className="px-2 py-2 whitespace-nowrap">
                {r.anexo}
                {r.item && <span className="block text-xs text-text-muted">item {r.item}</span>}
              </td>
              <td className="px-2 py-2">{r.descricao}</td>
              <td className="px-2 py-2 whitespace-nowrap">
                {efeito(r.reducao)}
                {r.cclass_trib && <span className="block text-xs text-text-muted">cClassTrib {r.cclass_trib}</span>}
              </td>
              <td className="max-w-sm px-2 py-2 text-xs text-text-muted">{r.condicao ?? "–"}</td>
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
      </Card>
    </>
  );
}

function ConsultaNcm() {
  const [ncm, setNcm] = useState("");
  const digitos = ncm.replace(/\D/g, "");
  const { data: r } = useQuery({
    queryKey: ["reforma-reducao-consulta", digitos],
    enabled: digitos.length === 8,
    queryFn: async () => (await api.get<Consulta>("/tabelas/reforma-reducoes/consulta", { params: { ncm: digitos } })).data,
  });
  return (
    <Card titulo="Consultar um NCM">
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label>
          NCM
          <input inputMode="numeric" className={`${campo} num w-36`} placeholder="1006.30.21" value={ncm} onChange={(e) => setNcm(e.target.value)} />
        </label>
        {r && digitos.length === 8 && (
          <p className={`max-w-[70ch] rounded px-3 py-2 ${r.reducao ? "bg-success-soft text-success-ink" : "bg-surface"}`} role="status">
            {r.reducao ? (
              <>
                <strong>{efeito(r.reducao.reducao)}</strong> de CBS e IBS: {r.reducao.descricao.toLowerCase()}, {r.reducao.anexo}
                {r.reducao.item ? `, item ${r.reducao.item}` : ""} da LC 214/2025.{r.reducao.condicao ? ` Requisito: ${r.reducao.condicao}.` : ""}
              </>
            ) : (
              <>
                <strong>Alíquota cheia</strong>: o NCM não está nos anexos cadastrados.
              </>
            )}
          </p>
        )}
      </div>
    </Card>
  );
}

function FormRegra({ inicial, fechar }: { inicial: Regra | null; fechar: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    ncm: inicial ? ncmFmt(inicial.ncm) : "",
    excecoes: inicial?.excecoes.map(ncmFmt).join(", ") ?? "",
    anexo: inicial?.anexo ?? "",
    item: inicial?.item ?? "",
    descricao: inicial?.descricao ?? "",
    reducao: inicial ? String(Math.round(Number(inicial.reducao) * 100)) : "60",
    condicao: inicial?.condicao ?? "",
    cclass_trib: inicial?.cclass_trib ?? "",
    vigencia_fim: inicial?.vigencia_fim ?? "",
  });
  const [erro, setErro] = useState<string | null>(null);
  const salvar = useMutation({
    mutationFn: () => {
      const corpo = {
        ncm: f.ncm,
        excecoes: f.excecoes.split(",").map((x) => x.trim()).filter(Boolean),
        anexo: f.anexo.trim(),
        item: f.item.trim() || null,
        descricao: f.descricao.trim(),
        reducao: Number(f.reducao) / 100,
        condicao: f.condicao.trim() || null,
        cclass_trib: f.cclass_trib.trim() || null,
        vigencia_fim: f.vigencia_fim || null,
      };
      return inicial ? api.put(`/tabelas/reforma-reducoes/${inicial.id}`, corpo) : api.post("/tabelas/reforma-reducoes", corpo);
    },
    onSuccess: () => {
      qc.invalidateQueries();
      fechar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  function enviar(e: FormEvent) {
    e.preventDefault();
    const n = f.ncm.replace(/\D/g, "");
    if (n.length < 2 || n.length > 8) return setErro("Informe o capítulo, a posição, a subposição ou o NCM completo");
    if (f.anexo.trim().length < 3) return setErro("Informe o anexo da LC 214, como em “Anexo VII”");
    if (f.descricao.trim().length < 3) return setErro("Informe o produto");
    if (f.cclass_trib && !/^\d{6}$/.test(f.cclass_trib.trim())) return setErro("O cClassTrib tem 6 dígitos");
    setErro(null);
    salvar.mutate();
  }

  return (
    <Modal
      aberto
      fechar={fechar}
      titulo={inicial ? `NCM ${ncmFmt(inicial.ncm)}` : "Nova redução de CBS e IBS"}
      descricao="Ao salvar, todas as simulações ficam desatualizadas."
      largura="max-w-2xl"
    >
      <form onSubmit={enviar} className="grid gap-3 text-sm sm:grid-cols-4">
        <label>
          NCM
          <Obrigatorio />
          <input autoFocus className={`${campo} num`} placeholder="9021.10" value={f.ncm} onChange={(e) => setF({ ...f, ncm: e.target.value })} />
        </label>
        <label>
          Anexo
          <Obrigatorio />
          <input className={campo} placeholder="Anexo IV" value={f.anexo} onChange={(e) => setF({ ...f, anexo: e.target.value })} />
        </label>
        <label>
          Item
          <input className={campo} value={f.item} onChange={(e) => setF({ ...f, item: e.target.value })} />
        </label>
        <label>
          Efeito
          <select className={campo} value={f.reducao} onChange={(e) => setF({ ...f, reducao: e.target.value })}>
            <option value="60">Redução de 60%</option>
            <option value="100">Alíquota zero</option>
            <option value="30">Redução de 30%</option>
            <option value="40">Redução de 40%</option>
          </select>
        </label>
        <label className="sm:col-span-4">
          Produto
          <Obrigatorio />
          <input className={campo} maxLength={200} value={f.descricao} onChange={(e) => setF({ ...f, descricao: e.target.value })} />
        </label>
        <label className="sm:col-span-2">
          Exceções
          <input className={`${campo} num`} placeholder="0207.43.00, 0207.53.00" value={f.excecoes} onChange={(e) => setF({ ...f, excecoes: e.target.value })} />
        </label>
        <label>
          cClassTrib
          <input className={`${campo} num`} maxLength={6} value={f.cclass_trib} onChange={(e) => setF({ ...f, cclass_trib: e.target.value })} />
        </label>
        <label>
          Vale até
          <input type="date" className={campo} value={f.vigencia_fim} onChange={(e) => setF({ ...f, vigencia_fim: e.target.value })} />
        </label>
        <label className="sm:col-span-4">
          Requisito
          <input
            className={campo}
            placeholder="O que o NCM sozinho não mostra, como “sem adição de açúcar”"
            value={f.condicao}
            onChange={(e) => setF({ ...f, condicao: e.target.value })}
          />
        </label>
        <div className="space-y-2 sm:col-span-4">
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
