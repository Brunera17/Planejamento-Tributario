const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const pct = new Intl.NumberFormat("pt-BR", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const brl = (v: number | null | undefined) => (v == null ? "—" : moeda.format(v));
export const percentual = (v: number | null | undefined) => (v == null ? "—" : pct.format(v));

export const REGIMES: Record<string, string> = {
  SIMPLES_NACIONAL: "Simples Nacional",
  LUCRO_PRESUMIDO: "Lucro Presumido",
  LUCRO_REAL: "Lucro Real",
};

export const STATUS: Record<string, string> = {
  EM_COLETA: "Em coleta",
  EM_CONFERENCIA: "Em conferência",
  PRONTO_PARA_SIMULAR: "Pronto para simular",
  SIMULADO: "Simulado",
  APROVADO: "Aprovado",
};

export function competenciaExtenso(c: string) {
  const [a, m] = c.split("-").map(Number);
  return new Date(a, m - 1, 1).toLocaleDateString("pt-BR", { month: "short", year: "numeric" });
}

/** Máscara de moeda: aceita "1.234,56" e devolve número ou null (vazio = não informado). */
export function lerMoeda(texto: string): number | null {
  const limpo = texto.replace(/[^\d,]/g, "").replace(",", ".");
  if (!limpo) return null;
  const n = Number(limpo);
  return Number.isFinite(n) ? Math.round(n * 100) / 100 : null;
}

export const editarMoeda = (v: number | null | undefined) =>
  v == null ? "" : v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function formatarCnpj(c: string) {
  return c.length === 14 ? `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}` : c;
}

/** Data e hora locais. O SQLite devolve datas sem fuso (gravadas em UTC); o PostgreSQL devolve com fuso. */
export function dataHora(iso: string) {
  const comFuso = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  return new Date(comFuso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
