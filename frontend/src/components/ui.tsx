import { type ReactNode, useState } from "react";

import { editarMoeda, lerMoeda, STATUS } from "../lib/formato";

/** Cabeçalho de página: título, uma linha de contexto e as ações da página. */
export function Cabecalho({ titulo, descricao, acoes, children }: { titulo: ReactNode; descricao?: ReactNode; acoes?: ReactNode; children?: ReactNode }) {
  return (
    <header className="space-y-3 pb-1">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1>{titulo}</h1>
          {descricao && <p className="mt-1 max-w-[70ch] text-text-muted">{descricao}</p>}
        </div>
        {acoes && <div className="flex flex-wrap gap-2">{acoes}</div>}
      </div>
      {children}
    </header>
  );
}

/** Painel de conteúdo: borda simples, sem sombra; o título separa o corpo com uma régua. */
export function Card({ titulo, acoes, children, semPadding }: { titulo?: string; acoes?: ReactNode; children: ReactNode; semPadding?: boolean }) {
  return (
    <section className="rounded-md border border-surface bg-white">
      {(titulo || acoes) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-surface px-4 py-2.5">
          {titulo && <h2>{titulo}</h2>}
          {acoes}
        </header>
      )}
      <div className={semPadding ? "" : "p-4"}>{children}</div>
    </section>
  );
}

/** Ficha no estilo dos campos de um DANFE: rótulo pequeno no canto, valor abaixo, caixas encostadas. */
export function Ficha({ campos }: { campos: { rotulo: string; valor: ReactNode; largo?: boolean }[] }) {
  return (
    <dl className="grid grid-cols-2 overflow-hidden rounded-md border-l border-t border-border bg-white sm:grid-cols-4 lg:grid-cols-6">
      {campos.map((c) => (
        <div key={c.rotulo} className={`border-b border-r border-border px-3 py-1.5 ${c.largo ? "col-span-2" : ""}`}>
          <dt className="text-xs text-text-muted">{c.rotulo}</dt>
          <dd className="truncate font-medium">{c.valor}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Botao({
  children,
  variante = "principal",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variante?: "principal" | "secundario" }) {
  const cls =
    variante === "principal"
      ? "border border-brand bg-brand text-white hover:bg-brand-hover"
      : "border border-border bg-white text-brand hover:border-brand hover:bg-highlight";
  return (
    <button {...props} className={`rounded px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${cls} ${props.className ?? ""}`}>
      {children}
    </button>
  );
}

/** Barra 0–100%: alerta até 49%, destaque de 50% a 99%, sucesso em 100% (texto sempre visível). */
export function BarraProgresso({ valor }: { valor: number }) {
  const cor = valor >= 100 ? "bg-success" : valor >= 50 ? "bg-warning" : "bg-alert";
  return (
    <div className="flex items-center gap-2" role="progressbar" aria-valuenow={valor} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface">
        <div className={`h-full ${cor}`} style={{ width: `${valor}%` }} />
      </div>
      <span className="num w-9 text-xs text-text-muted">{valor}%</span>
    </div>
  );
}

const ICONES: Record<string, string> = {
  EM_COLETA: "✎",
  EM_CONFERENCIA: "⧗",
  PRONTO_PARA_SIMULAR: "▶",
  SIMULADO: "∑",
  APROVADO: "✔",
  PRELIMINAR: "!",
  FINAL: "✔",
};

/** Status nunca só por cor: badge com ícone e texto. */
export function Badge({ status }: { status: string }) {
  const tom =
    status === "APROVADO" || status === "FINAL"
      ? "bg-success-soft text-success-ink"
      : status === "PRELIMINAR"
        ? "bg-warning-soft text-warning-ink"
        : "bg-surface text-text";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${tom}`}>
      <span aria-hidden>{ICONES[status] ?? "•"}</span>
      {STATUS[status] ?? status.charAt(0) + status.slice(1).toLowerCase()}
    </span>
  );
}

/** Campo monetário: vazio = não informado; 0,00 = informado. */
export function CampoMoeda({
  valor,
  onChange,
  rotulo,
}: {
  valor: number | null | undefined;
  onChange: (v: number | null) => void;
  rotulo: string;
}) {
  const [texto, setTexto] = useState(editarMoeda(valor));
  return (
    <input
      aria-label={rotulo}
      inputMode="decimal"
      className={`num w-32 rounded border px-2 py-1 text-sm ${valor == null ? "border-alert/60" : "border-border"}`}
      placeholder="não informado"
      value={texto}
      onChange={(e) => setTexto(e.target.value.replace(/[^\d.,]/g, ""))}
      onBlur={() => {
        const v = lerMoeda(texto);
        setTexto(editarMoeda(v));
        onChange(v);
      }}
    />
  );
}

export function Erro({ mensagem }: { mensagem: string | null }) {
  if (!mensagem) return null;
  return (
    <p role="alert" className="flex gap-2 rounded border border-alert/40 bg-alert-soft px-3 py-2 text-sm text-alert-ink">
      <span aria-hidden className="font-semibold">!</span>
      {mensagem}
    </p>
  );
}

/** Tabela de dados em largura condensada; `numericas` alinha os cabeçalhos das colunas de valor à direita. */
export function Tabela({ cabecalho, children, numericas = [] }: { cabecalho: ReactNode[]; children: ReactNode; numericas?: number[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="condensado w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            {cabecalho.map((c, i) => (
              <th key={i} className={`px-2 py-1.5 font-medium text-text-muted ${numericas.includes(i) ? "text-right" : "text-left"}`}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="[&>tr]:border-b [&>tr]:border-surface [&>tr:last-child]:border-0 [&>tr:hover]:bg-highlight">{children}</tbody>
      </table>
    </div>
  );
}
