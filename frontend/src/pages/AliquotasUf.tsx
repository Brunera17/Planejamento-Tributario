import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import { Botao, Card, Erro, LegendaObrigatorio, Modal, Obrigatorio, Tabela } from "../components/ui";
import { dataHora, lerMoeda } from "../lib/formato";

type AliquotaUf = {
  id: number;
  uf: string;
  aliquota: number;
  fcp: number;
  base_dupla: boolean;
  fonte: string | null;
  vigencia_inicio: string;
  vigencia_fim: string | null;
  vigente_hoje: boolean;
  alterado_em: string | null;
  alterado_por_nome: string | null;
};

const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";
const pct = (v: number) => `${(Number(v) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
const dataBr = (iso: string) => iso.split("-").reverse().join("/");
const INICIO_PADRAO = "2000-01-01";

function vigencia(a: AliquotaUf) {
  if (a.vigencia_fim) return `${a.vigencia_inicio > INICIO_PADRAO ? `${dataBr(a.vigencia_inicio)} a ` : "até "}${dataBr(a.vigencia_fim)}`;
  return a.vigencia_inicio > INICIO_PADRAO ? `desde ${dataBr(a.vigencia_inicio)}` : "em vigor";
}

/** Alíquota interna de cada estado, usada no DIFAL das vendas a consumidor final não contribuinte de outro estado. */
export function AliquotasUf() {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const [mudando, setMudando] = useState<AliquotaUf | null>(null);
  const [historico, setHistorico] = useState(false);
  const { data = [] } = useQuery({ queryKey: ["aliquotas-uf"], queryFn: async () => (await api.get<AliquotaUf[]>("/tabelas/aliquotas-uf")).data });
  const linhas = data.filter((a) => historico || a.vigente_hoje);

  return (
    <>
      {mudando && <FormAliquota atual={mudando} fechar={() => setMudando(null)} />}
      <Card
        titulo="ICMS de cada estado (DIFAL)"
        adendo="EC 87/2015 e LC 190/2022"
        semPadding
        acoes={
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={historico} onChange={(e) => setHistorico(e.target.checked)} />
            Mostrar alíquotas anteriores
          </label>
        }
      >
        <p className="max-w-[90ch] px-4 pt-3 text-sm text-text-muted">
          Na venda a consumidor final não contribuinte de outro estado, o Lucro Presumido e o Lucro Real recolhem ao destino a diferença entre a alíquota de lá e a
          interestadual. O Simples não recolhe (STF, ADI 5464). Quando um estado mudar a alíquota, informe a nova com a data de início: a anterior vale até a véspera.
        </p>
        <Tabela cabecalho={["UF", "Alíquota interna", "FCP", "Base", "Vigência", "Fonte", ""]} numericas={[1, 2]}>
          {linhas.map((a) => (
            <tr key={a.id} className={a.vigente_hoje ? "" : "text-text-muted"}>
              <td className="px-4 py-2 font-medium">{a.uf}</td>
              <td className="num px-2 py-2 font-medium">{pct(a.aliquota)}</td>
              <td className="num px-2 py-2">{Number(a.fcp) ? pct(a.fcp) : "–"}</td>
              <td className="px-2 py-2">{a.base_dupla ? "Dupla" : "Única"}</td>
              <td className="px-2 py-2 whitespace-nowrap">{vigencia(a)}</td>
              <td className="max-w-md px-2 py-2 text-xs text-text-muted">
                {a.fonte ?? "–"}
                {a.alterado_por_nome && a.alterado_em && (
                  <span className="block">
                    Atualizado por {a.alterado_por_nome} em {dataHora(a.alterado_em)}
                  </span>
                )}
              </td>
              <td className="px-4 py-2 text-right">
                {contador && a.vigente_hoje && (
                  <Botao variante="linha" onClick={() => setMudando(a)}>
                    Nova alíquota
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

function FormAliquota({ atual, fechar }: { atual: AliquotaUf; fechar: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    aliquota: (Number(atual.aliquota) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 }),
    fcp: (Number(atual.fcp) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 }),
    base_dupla: atual.base_dupla,
    vigencia_inicio: "",
    fonte: "",
  });
  const [erro, setErro] = useState<string | null>(null);
  const salvar = useMutation({
    mutationFn: () =>
      api.post(`/tabelas/aliquotas-uf/${atual.uf}`, {
        aliquota: lerMoeda(f.aliquota)! / 100,
        fcp: (lerMoeda(f.fcp) ?? 0) / 100,
        base_dupla: f.base_dupla,
        vigencia_inicio: f.vigencia_inicio,
        fonte: f.fonte.trim(),
      }),
    onSuccess: () => {
      qc.invalidateQueries();
      fechar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  function enviar(e: FormEvent) {
    e.preventDefault();
    const a = lerMoeda(f.aliquota);
    if (a == null || a < 7 || a > 35) return setErro("Informe a alíquota interna em percentual, entre 7% e 35%");
    if ((lerMoeda(f.fcp) ?? 0) > 4) return setErro("O FCP vai de 0% a 4%");
    if (!f.vigencia_inicio || f.vigencia_inicio <= atual.vigencia_inicio) return setErro(`Informe uma data de início posterior a ${dataBr(atual.vigencia_inicio)}`);
    if (f.fonte.trim().length < 5) return setErro("Informe a lei ou o decreto que mudou a alíquota");
    setErro(null);
    salvar.mutate();
  }

  return (
    <Modal
      aberto
      fechar={fechar}
      titulo={`Nova alíquota de ${atual.uf}`}
      descricao={`Hoje: ${pct(atual.aliquota)}${Number(atual.fcp) ? ` + ${pct(atual.fcp)} de FCP` : ""}. A atual termina na véspera da data de início, e as simulações ficam desatualizadas.`}
      largura="max-w-xl"
    >
      <form onSubmit={enviar} className="grid gap-3 text-sm sm:grid-cols-3">
        <label>
          Alíquota interna
          <Obrigatorio />
          <input autoFocus inputMode="decimal" className={`${campo} num`} value={f.aliquota} onChange={(e) => setF({ ...f, aliquota: e.target.value })} />
        </label>
        <label>
          FCP
          <input inputMode="decimal" className={`${campo} num`} value={f.fcp} onChange={(e) => setF({ ...f, fcp: e.target.value })} />
        </label>
        <label>
          Vale a partir de
          <Obrigatorio />
          <input type="date" className={campo} value={f.vigencia_inicio} onChange={(e) => setF({ ...f, vigencia_inicio: e.target.value })} />
        </label>
        <label className="flex items-center gap-2 sm:col-span-3">
          <input type="checkbox" checked={f.base_dupla} onChange={(e) => setF({ ...f, base_dupla: e.target.checked })} />
          Base dupla (o ICMS do destino entra na própria base)
        </label>
        <label className="sm:col-span-3">
          Fonte
          <Obrigatorio />
          <input className={campo} maxLength={300} placeholder="Ex.: Lei 12.345/2026, art. 1º" value={f.fonte} onChange={(e) => setF({ ...f, fonte: e.target.value })} />
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
                Salvar e desatualizar simulações
              </Botao>
            </div>
          </div>
        </div>
      </form>
    </Modal>
  );
}
