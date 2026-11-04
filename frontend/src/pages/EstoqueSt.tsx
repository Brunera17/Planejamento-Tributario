import { useQuery } from "@tanstack/react-query";

import { api } from "../api/cliente";
import { Tabela } from "../components/ui";
import { brl, competenciaExtenso } from "../lib/formato";

type EntradaSt = { numero: string; data: string; ncm: string; custo: number; bc_st: number; credito: number; formula: string };
export type EstoqueStDados = {
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

export const dataBr = (iso: string) => iso.split("-").reverse().join("/");
const diaSeguinte = (iso: string) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + 1);
  return d.toLocaleDateString("pt-BR");
};
const ncmFmt = (n: string) => `${n.slice(0, 4)}.${n.slice(4, 6)}.${n.slice(6)}`;
const juntar = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} e ${xs[xs.length - 1]}`);

export const useEstoqueSt = (pid: number) =>
  useQuery({ queryKey: ["estoque-st", pid], queryFn: async () => (await api.get<EstoqueStDados | null>(`/planejamentos/${pid}/estoque-st`)).data });

export function usoDoCredito(e: EstoqueStDados) {
  const ultima = e.parcelas[e.parcelas.length - 1];
  if (e.regime_rpa && ultima)
    return `12 × ${brl(e.parcelas[0].valor)} na apuração do ICMS, de ${competenciaExtenso(e.parcelas[0].competencia)} a ${competenciaExtenso(ultima.competencia)}`;
  return `abatido do ICMS do DAS a partir de ${competenciaExtenso(e.inicio_uso)}`;
}

/** Como o crédito do estoque que saiu da ST foi estimado (Portaria CAT 28/2020): regra, notas usadas e ressalvas. */
export function DetalheEstoqueSt({ e }: { e: EstoqueStDados }) {
  return (
    <div className="space-y-2 text-sm">
      <p className="max-w-[80ch]">
        {juntar(e.segmentos)} saíram da ST em {diaSeguinte(e.corte)}
        {e.norma ? `, pela ${e.norma}` : ""}. O ICMS-ST pago no estoque do fim de {dataBr(e.corte)} vira crédito ({e.fundamento}).
        {e.taxa != null && ` Pelas notas de entrada, cada R$ 100 de estoque dão ${brl(e.taxa * 100)} de crédito.`}
      </p>
      <p className="text-text-muted">
        Estoque pelo custo de aquisição, com o ICMS-ST pago, só destes NCM: {e.ncms.slice(0, 8).map(ncmFmt).join(", ")}
        {e.ncms.length > 8 ? ` e mais ${e.ncms.length - 8}` : ""}.
      </p>
      {e.taxa == null && (
        <p className="text-warning-ink">
          Sem notas de entrada com ST até {dataBr(e.corte)}. Importe os XML de compra dessas mercadorias; notas já importadas podem ir de novo, sem duplicar.
        </p>
      )}
      {e.sem_base > 0 && (
        <p className="text-text-muted">
          {e.sem_base} {e.sem_base === 1 ? "item saiu" : "itens saíram"} com CST de ST sem a base retida: crédito zero até a nota complementar (art. 4º).
        </p>
      )}
      {e.entradas.length > 0 && (
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
      )}
      <p className="text-xs text-text-muted">
        Estimativa. O valor a creditar é o do relatório da portaria, item a item do inventário; quem entrega a EFD escritura o inventário no Bloco H.
      </p>
    </div>
  );
}
