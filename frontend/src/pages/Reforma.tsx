import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import { Botao, Card, Erro, LegendaObrigatorio, Modal, Obrigatorio, Tabela } from "../components/ui";
import { dataHora, lerMoeda } from "../lib/formato";

type AnoReforma = {
  ano: number;
  cbs: number;
  ibs: number;
  fator_icms: number;
  situacao: string | null;
  fonte: string | null;
  alterado_em: string | null;
  alterado_por_nome: string | null;
};
type Historico = { id: number; ano: number; cbs: number; ibs: number; fator_icms: number; fonte: string | null; substituido_por_fonte: string; alterado_em: string; alterado_por_nome: string | null };

const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";
// alíquotas com até 4 casas (11,3468% do TCU), sem arredondar o que a lei fixou
const pct = (v: number) => `${(Number(v) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 4 })}%`;
const editarPct = (v: number) => (Number(v) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 4, useGrouping: false });

/** Cronograma da Reforma mantido pelo contador: a lei muda e o cálculo acompanha, com a fonte e o histórico. */
export function Reforma() {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const [editando, setEditando] = useState<AnoReforma | null>(null);
  const { data: anos = [] } = useQuery({ queryKey: ["reforma"], queryFn: async () => (await api.get<AnoReforma[]>("/tabelas/reforma")).data });
  const { data: historico = [] } = useQuery({
    queryKey: ["reforma-historico"],
    queryFn: async () => (await api.get<Historico[]>("/tabelas/reforma/historico")).data,
  });

  return (
    <>
      {editando && <FormAno inicial={editando} fechar={() => setEditando(null)} />}
      <Card titulo="Cronograma da transição (2027 a 2033)" semPadding>
        <p className="max-w-[90ch] px-4 pt-3 text-sm text-text-muted">
          Alíquotas usadas na projeção da Reforma em todos os planejamentos. Quando sair uma resolução do Senado ou um novo cálculo do TCU, atualize o ano e
          informe a fonte: o valor anterior fica no histórico e as simulações ficam desatualizadas, para serem refeitas.
        </p>
        <Tabela cabecalho={["Ano", "CBS", "IBS", "ICMS que resta", "Situação", "Fonte", ""]} numericas={[1, 2, 3]}>
          {anos.map((a) => (
            <tr key={a.ano}>
              <td className="px-4 py-2 font-medium">{a.ano}</td>
              <td className="num px-2 py-2 font-medium">{pct(a.cbs)}</td>
              <td className="num px-2 py-2">{pct(a.ibs)}</td>
              <td className="num px-2 py-2">{Number(a.fator_icms) === 0 ? "extinto" : pct(a.fator_icms)}</td>
              <td className="px-2 py-2">{a.situacao ?? "–"}</td>
              <td className="max-w-md px-2 py-2 text-xs text-text-muted">
                {a.fonte ?? "–"}
                {a.alterado_por_nome && a.alterado_em && (
                  <span className="block">
                    Atualizado por {a.alterado_por_nome} em {dataHora(a.alterado_em)}
                  </span>
                )}
              </td>
              <td className="px-4 py-2 text-right">
                {contador && (
                  <Botao variante="linha" onClick={() => setEditando(a)}>
                    Atualizar
                  </Botao>
                )}
              </td>
            </tr>
          ))}
        </Tabela>
      </Card>

      <Card titulo="Histórico de alterações" semPadding>
        {historico.length === 0 ? (
          <p className="p-4 text-sm text-text-muted">Nenhuma alteração registrada.</p>
        ) : (
          <Tabela cabecalho={["Quando", "Ano", "CBS anterior", "IBS anterior", "ICMS anterior", "Motivo da troca", "Por"]} numericas={[2, 3, 4]}>
            {historico.map((h) => (
              <tr key={h.id}>
                <td className="whitespace-nowrap px-4 py-2">{dataHora(h.alterado_em)}</td>
                <td className="px-2 py-2 font-medium">{h.ano}</td>
                <td className="num px-2 py-2">{pct(h.cbs)}</td>
                <td className="num px-2 py-2">{pct(h.ibs)}</td>
                <td className="num px-2 py-2">{pct(h.fator_icms)}</td>
                <td className="max-w-md px-2 py-2 text-xs">{h.substituido_por_fonte}</td>
                <td className="px-2 py-2">{h.alterado_por_nome ?? "migração"}</td>
              </tr>
            ))}
          </Tabela>
        )}
      </Card>
    </>
  );
}

function FormAno({ inicial, fechar }: { inicial: AnoReforma; fechar: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    cbs: editarPct(inicial.cbs),
    ibs: editarPct(inicial.ibs),
    icms: editarPct(inicial.fator_icms),
    situacao: inicial.situacao ?? "",
    fonte: "",
  });
  const [erro, setErro] = useState<string | null>(null);
  const salvar = useMutation({
    mutationFn: () =>
      api.put(`/tabelas/reforma/${inicial.ano}`, {
        cbs: lerMoeda(f.cbs)! / 100,
        ibs: lerMoeda(f.ibs)! / 100,
        fator_icms: lerMoeda(f.icms)! / 100,
        situacao: f.situacao.trim() || null,
        fonte: f.fonte.trim(),
      }),
    onSuccess: () => {
      // a alíquota entra em todas as simulações: resultados e listas precisam recarregar
      qc.invalidateQueries();
      fechar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  function enviar(e: FormEvent) {
    e.preventDefault();
    const valores = [lerMoeda(f.cbs), lerMoeda(f.ibs), lerMoeda(f.icms)];
    if (valores.some((v) => v == null)) return setErro("Informe CBS, IBS e a parcela do ICMS em percentual");
    if (valores[0]! > 50 || valores[1]! > 50) return setErro("Alíquota acima de 50%: confira se não digitou o valor sem a vírgula");
    if (valores[2]! > 100) return setErro("A parcela do ICMS vai de 0% (extinto) a 100% (integral)");
    if (f.fonte.trim().length < 5) return setErro("Informe a fonte: a norma ou o ato que fixou os valores");
    setErro(null);
    salvar.mutate();
  }

  const percentualCampo = (k: "cbs" | "ibs" | "icms", rotulo: string, ajuda: string) => (
    <label>
      {rotulo}
      <Obrigatorio />
      <span className="relative block">
        <input inputMode="decimal" className={`${campo} num pr-7`} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value.replace(/[^\d.,]/g, "") })} />
        <span className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 pt-1 text-text-muted">%</span>
      </span>
      <span className="mt-1 block text-xs text-text-muted">{ajuda}</span>
    </label>
  );

  return (
    <Modal
      aberto
      fechar={fechar}
      titulo={`Atualizar ${inicial.ano}`}
      descricao="O valor atual vai para o histórico, e todas as simulações ficam desatualizadas."
      largura="max-w-2xl"
    >
      <form onSubmit={enviar} className="grid gap-3 text-sm sm:grid-cols-3">
        {percentualCampo("cbs", "CBS", inicial.ano <= 2028 ? "Em 2027 e 2028: referência menos 0,1 ponto (LC 214, art. 347)" : "Alíquota de referência do ano")}
        {percentualCampo("ibs", "IBS", inicial.ano <= 2028 ? "0,1% de teste (LC 214, art. 344)" : "Estadual + municipal")}
        {percentualCampo("icms", "ICMS que resta", "100% = integral; 0% = extinto")}
        <label className="sm:col-span-3">
          Situação
          <input className={campo} maxLength={200} value={f.situacao} onChange={(e) => setF({ ...f, situacao: e.target.value })} />
        </label>
        <label className="sm:col-span-3">
          Fonte da alteração
          <Obrigatorio />
          <input
            autoFocus
            className={campo}
            maxLength={300}
            placeholder="Ex.: Resolução do Senado Federal nº 00/2026"
            value={f.fonte}
            onChange={(e) => setF({ ...f, fonte: e.target.value })}
          />
          <span className="mt-1 block text-xs text-text-muted">Atual: {inicial.fonte ?? "não informada"}</span>
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
