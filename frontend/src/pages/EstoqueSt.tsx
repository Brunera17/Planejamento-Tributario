import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, mensagemErro } from "../api/cliente";
import { Botao, CampoMoeda, Card, Erro, Ficha, Tabela } from "../components/ui";
import { brl, competenciaExtenso } from "../lib/formato";

type EntradaSt = { numero: string; data: string; ncm: string; custo: number; bc_st: number; credito: number; formula: string };
type EstoqueSt = {
  corte: string;
  norma: string | null;
  segmentos: string[];
  ncms: string[];
  regime_rpa: boolean;
  estoque: number | null;
  taxa: number | null;
  credito: number | null;
  inicio_uso: string;
  sem_base: number;
  parcelas: { competencia: string; valor: number }[];
  entradas: EntradaSt[];
  fundamento: string;
};

const dataBr = (iso: string) => iso.split("-").reverse().join("/");
const diaSeguinte = (iso: string) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + 1);
  return d.toLocaleDateString("pt-BR");
};
const ncmFmt = (n: string) => `${n.slice(0, 4)}.${n.slice(4, 6)}.${n.slice(6)}`;
const juntar = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} e ${xs[xs.length - 1]}`);

/** Crédito do ICMS-ST do estoque quando as mercadorias da empresa saem da substituição tributária (Portaria CAT 28/2020). */
export function EstoqueSt({ pid }: { pid: number }) {
  const qc = useQueryClient();
  const { data: e } = useQuery({
    queryKey: ["estoque-st", pid],
    queryFn: async () => (await api.get<EstoqueSt | null>(`/planejamentos/${pid}/estoque-st`)).data,
  });
  const [valor, setValor] = useState<number | null | undefined>(undefined);
  const [erro, setErro] = useState<string | null>(null);
  const salvar = useMutation({
    mutationFn: (v: number | null) => api.put(`/planejamentos/${pid}/estoque-st`, { valor: v }),
    onSuccess: () => {
      setErro(null);
      setValor(undefined);
      qc.invalidateQueries({ queryKey: ["estoque-st", pid] });
      qc.invalidateQueries({ queryKey: ["simulacoes", pid] });
      qc.invalidateQueries({ queryKey: ["planejamento", String(pid)] });
    },
    onError: (x) => setErro(mensagemErro(x)),
  });
  if (!e) return null;

  const digitado = valor === undefined ? e.estoque : valor;
  const mudou = valor !== undefined && valor !== e.estoque;
  const credito = e.taxa != null && digitado != null ? digitado * e.taxa : null;
  const ultima = e.parcelas[e.parcelas.length - 1];
  const uso = e.regime_rpa
    ? `em 12 parcelas mensais na apuração do ICMS, a partir de ${competenciaExtenso(e.inicio_uso)}`
    : `abatido do ICMS do DAS no PGDAS-D a partir de ${competenciaExtenso(e.inicio_uso)}; o que sobrar passa para os meses seguintes`;

  return (
    <Card titulo="Estoque que saiu da substituição tributária" adendo={e.fundamento}>
      <div className="space-y-3 text-sm">
        <p className="max-w-[80ch]">
          {juntar(e.segmentos)} saíram da ST em {diaSeguinte(e.corte)}
          {e.norma ? `, pela ${e.norma}` : ""}. O ICMS-ST já pago nas mercadorias que estavam em estoque no fim de {dataBr(e.corte)} vira crédito, {uso}.
        </p>

        <Ficha
          campos={[
            {
              rotulo: `Estoque em ${dataBr(e.corte)}`,
              largo: true,
              valor: (
                <span className="flex flex-wrap items-center gap-2">
                  <CampoMoeda key={e.estoque ?? "vazio"} rotulo={`Estoque em ${dataBr(e.corte)}`} valor={digitado} onChange={(v) => setValor(v)} />
                  {mudou && (
                    <Botao disabled={salvar.isPending} onClick={() => salvar.mutate(valor ?? null)}>
                      Salvar estoque
                    </Botao>
                  )}
                </span>
              ),
            },
            {
              rotulo: "Crédito por R$ 100 de estoque",
              valor: e.taxa == null ? "sem notas de entrada com ST" : brl(e.taxa * 100),
            },
            {
              rotulo: "Crédito estimado",
              valor: credito == null ? "–" : <strong className="text-success-ink">{brl(credito)}</strong>,
            },
            {
              rotulo: e.regime_rpa ? "Uso do crédito" : "Primeiro abatimento",
              largo: true,
              valor:
                e.regime_rpa && ultima
                  ? `12 × ${brl(e.parcelas[0].valor)}, de ${competenciaExtenso(e.parcelas[0].competencia)} a ${competenciaExtenso(ultima.competencia)}`
                  : competenciaExtenso(e.inicio_uso),
            },
          ]}
        />
        <p className="text-xs text-text-muted">
          Informe o estoque pelo custo de aquisição, com o ICMS-ST pago, só das mercadorias que saíram da ST ({e.ncms.length}{" "}
          {e.ncms.length === 1 ? "NCM vendido ou comprado" : "NCM vendidos ou comprados"} pela empresa: {e.ncms.slice(0, 6).map(ncmFmt).join(", ")}
          {e.ncms.length > 6 ? "…" : ""}).
        </p>
        <Erro mensagem={erro} />

        {e.taxa == null && (
          <p className="rounded bg-warning-soft px-3 py-2 text-warning-ink">
            Para estimar o crédito, importe na aba Faturamento os XML de compra dessas mercadorias até {dataBr(e.corte)}, com o ICMS-ST retido (CST 60, 10 ou
            CSOSN 500). Notas já importadas podem ser enviadas de novo: o sistema completa a base da ST sem duplicar.
          </p>
        )}
        {e.sem_base > 0 && (
          <p className="text-text-muted">
            {e.sem_base} {e.sem_base === 1 ? "item de entrada saiu" : "itens de entrada saíram"} com CST de ST sem a base retida na nota: pela portaria, o crédito
            desses itens é zero até o fornecedor emitir a nota complementar com a base (art. 4º).
          </p>
        )}

        {e.entradas.length > 0 && (
          <details>
            <summary className="cursor-pointer text-brand">
              {e.entradas.length} {e.entradas.length === 1 ? "nota de entrada usada" : "notas de entrada usadas"} na estimativa
            </summary>
            <div className="mt-2">
              <Tabela cabecalho={["NF", "Data", "NCM", "Custo", "Base da ST", "Crédito", "Fórmula"]} numericas={[3, 4, 5]}>
                {e.entradas.map((x, i) => (
                  <tr key={i}>
                    <td className="px-2 py-1.5">{x.numero}</td>
                    <td className="px-2 py-1.5">{dataBr(x.data)}</td>
                    <td className="num px-2 py-1.5">{ncmFmt(x.ncm)}</td>
                    <td className="num px-2 py-1.5">{brl(x.custo)}</td>
                    <td className="num px-2 py-1.5">{brl(x.bc_st)}</td>
                    <td className="num px-2 py-1.5">{brl(x.credito)}</td>
                    <td className="px-2 py-1.5 text-xs text-text-muted">{x.formula}</td>
                  </tr>
                ))}
              </Tabela>
            </div>
          </details>
        )}
        <p className="text-xs text-text-muted">
          Estimativa para o planejamento. O valor a creditar é o do relatório da portaria, item a item do inventário, com as notas de entrada mais recentes; quem
          entrega a EFD escritura o inventário no Bloco H.
        </p>
      </div>
    </Card>
  );
}
