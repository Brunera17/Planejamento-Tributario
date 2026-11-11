import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { Link, type LinkProps } from "react-router-dom";

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
export function Card({
  titulo,
  adendo,
  acoes,
  children,
  semPadding,
}: {
  titulo?: string;
  adendo?: ReactNode;
  acoes?: ReactNode;
  children: ReactNode;
  semPadding?: boolean;
}) {
  return (
    <section className="rounded-md border border-surface bg-white">
      {(titulo || acoes) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-surface px-4 py-2.5">
          {titulo && (
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
              <h2>{titulo}</h2>
              {adendo && <p className="text-sm text-text-muted">{adendo}</p>}
            </div>
          )}
          {acoes}
        </header>
      )}
      <div className={semPadding ? "" : "p-4"}>{children}</div>
    </section>
  );
}

/** Ficha no estilo dos campos de um DANFE: rótulo pequeno no canto, valor abaixo, caixas encostadas. */
export function Ficha({ campos }: { campos: { rotulo: string; valor: ReactNode; largo?: boolean }[] }) {
  // no desktop as caixas ocupam a largura toda, como os campos de um DANFE (nada de coluna vazia no fim)
  const colunas = Math.min(6, campos.reduce((n, c) => n + (c.largo ? 2 : 1), 0));
  return (
    <dl
      style={{ "--colunas": `repeat(${colunas}, minmax(0, 1fr))` } as React.CSSProperties}
      className="grid grid-cols-2 overflow-hidden rounded-md border-l border-t border-border bg-white sm:grid-cols-4 lg:grid-cols-(--colunas)"
    >
      {campos.map((c) => (
        <div key={c.rotulo} className={`border-b border-r border-border px-3 py-1.5 ${c.largo ? "col-span-2" : ""}`}>
          <dt className="text-xs text-text-muted">{c.rotulo}</dt>
          <dd className="truncate font-medium">{c.valor}</dd>
        </div>
      ))}
    </dl>
  );
}

const VARIANTES = {
  principal: "border-brand bg-brand text-white hover:bg-brand-hover",
  secundario: "border-border bg-white text-brand hover:border-brand hover:bg-highlight",
  perigo: "border-alert bg-alert text-white hover:bg-alert-ink",
  // ação de linha de tabela: discreta até o mouse passar
  linha: "border-border bg-white text-brand hover:border-brand hover:bg-highlight",
  "linha-perigo": "border-border bg-white text-alert hover:border-alert hover:bg-alert-soft",
  "linha-destaque": "border-brand bg-brand text-white hover:bg-brand-hover",
};

const classeBotao = (variante: keyof typeof VARIANTES) =>
  `inline-block rounded border font-medium whitespace-nowrap ${variante.startsWith("linha") ? "px-2 py-0.5 text-xs" : "px-3 py-1.5 text-sm"} ${VARIANTES[variante]}`;

/** Navegação com aparência de botão (ações de linha e atalhos). */
export function BotaoLink({ variante = "secundario", className, ...props }: LinkProps & { variante?: keyof typeof VARIANTES }) {
  return <Link {...props} className={`${classeBotao(variante)} ${className ?? ""}`} />;
}

export function Botao({
  children,
  variante = "principal",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variante?: keyof typeof VARIANTES }) {
  return (
    <button type="button" {...props} className={`${classeBotao(variante)} disabled:cursor-not-allowed disabled:opacity-50 ${props.className ?? ""}`}>
      {children}
    </button>
  );
}

/** Marca de campo obrigatório; o formulário explica o asterisco uma vez, na legenda. */
export function Obrigatorio() {
  return (
    <span className="text-alert" aria-hidden>
      {" "}*
    </span>
  );
}

export function LegendaObrigatorio() {
  return (
    <p className="text-xs text-text-muted">
      <span className="text-alert">*</span> Preenchimento obrigatório
    </p>
  );
}

/** Janela modal sobre a página (dialog nativo: Esc fecha, o foco fica preso dentro). */
export function Modal({
  titulo,
  descricao,
  aberto,
  fechar,
  children,
  largura = "max-w-2xl",
}: {
  titulo: string;
  descricao?: ReactNode;
  aberto: boolean;
  fechar: () => void;
  children: ReactNode;
  largura?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (aberto && !d.open) d.showModal();
    if (!aberto && d.open) d.close();
  }, [aberto]);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        fechar();
      }}
      onMouseDown={(e) => e.target === ref.current && fechar()}
      className={`modal m-auto w-[calc(100%-2rem)] ${largura} rounded-md border border-border bg-white p-0 text-text`}
    >
      {aberto && (
        <>
          <header className="flex items-start justify-between gap-4 border-b border-surface px-5 py-3">
            <div>
              <h2>{titulo}</h2>
              {descricao && <p className="mt-0.5 text-sm text-text-muted">{descricao}</p>}
            </div>
            <button type="button" aria-label="Fechar" onClick={fechar} className="-mr-1 rounded px-1.5 text-lg leading-none text-text-muted hover:bg-surface">
              ×
            </button>
          </header>
          <div className="max-h-[calc(100vh-10rem)] overflow-y-auto px-5 py-4">{children}</div>
        </>
      )}
    </dialog>
  );
}

type PedidoConfirmacao = { titulo: string; mensagem: ReactNode; confirmar: string; perigo?: boolean };

/** Substitui window.confirm: `const [confirmar, janela] = useConfirmacao()`; `if (await confirmar({...}))`. */
export function useConfirmacao(): [(p: PedidoConfirmacao) => Promise<boolean>, ReactNode] {
  const [pedido, setPedido] = useState<(PedidoConfirmacao & { responder: (ok: boolean) => void }) | null>(null);
  const confirmar = useCallback((p: PedidoConfirmacao) => new Promise<boolean>((responder) => setPedido({ ...p, responder })), []);
  const responder = (ok: boolean) => {
    pedido?.responder(ok);
    setPedido(null);
  };
  const janela = (
    <Modal titulo={pedido?.titulo ?? ""} aberto={!!pedido} fechar={() => responder(false)} largura="max-w-md">
      <div className="space-y-4 text-sm">
        <div>{pedido?.mensagem}</div>
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={() => responder(false)}>
            Voltar
          </Botao>
          <Botao autoFocus variante={pedido?.perigo ? "perigo" : "principal"} onClick={() => responder(true)}>
            {pedido?.confirmar}
          </Botao>
        </div>
      </div>
    </Modal>
  );
  return [confirmar, janela];
}

/** Área para soltar ou escolher arquivos, com os formatos aceitos à vista. */
export function EnvioArquivo({
  formatos,
  aoEscolher,
  multiplo,
  arquivos,
}: {
  formatos: string[];
  aoEscolher: (f: File[]) => void;
  multiplo?: boolean;
  arquivos: File[];
}) {
  const [sobre, setSobre] = useState(false);
  const aceitos = (fs: File[]) => fs.filter((f) => formatos.some((x) => f.name.toLowerCase().endsWith(x)));
  return (
    <div className="space-y-2">
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setSobre(true);
        }}
        onDragLeave={() => setSobre(false)}
        onDrop={(e) => {
          e.preventDefault();
          setSobre(false);
          const fs = aceitos([...e.dataTransfer.files]);
          if (fs.length) aoEscolher(multiplo ? fs : fs.slice(0, 1));
        }}
        className={`flex cursor-pointer flex-col items-center gap-1 rounded-md border-2 border-dashed px-4 py-7 text-center text-sm ${sobre ? "border-brand bg-highlight" : "border-border bg-bg hover:border-brand"}`}
      >
        <span className="font-medium text-brand">Arraste o arquivo para cá ou clique para escolher</span>
        <span className="text-xs text-text-muted">Formatos aceitos: {formatos.map((f) => f.slice(1).toUpperCase()).join(", ")}</span>
        <input
          type="file"
          className="sr-only"
          multiple={multiplo}
          accept={formatos.join(",")}
          onChange={(e) => {
            aoEscolher(aceitos([...(e.target.files ?? [])]));
            e.target.value = "";
          }}
        />
      </label>
      {arquivos.length > 0 && (
        <ul className="divide-y divide-surface rounded border border-surface text-sm">
          {arquivos.map((f) => (
            <li key={f.name + f.size} className="flex items-center justify-between gap-3 px-3 py-1.5">
              <span className="truncate">
                <span className="mr-2 rounded bg-surface px-1.5 py-0.5 text-xs font-medium">{f.name.split(".").pop()?.toUpperCase()}</span>
                {f.name}
              </span>
              <span className="flex shrink-0 items-center gap-3 text-xs text-text-muted">
                {f.size < 1024 * 1024 ? `${Math.ceil(f.size / 1024)} KB` : `${(f.size / 1024 / 1024).toFixed(1)} MB`}
                <button type="button" aria-label={`Retirar ${f.name}`} className="text-alert hover:underline" onClick={() => aoEscolher(arquivos.filter((x) => x !== f))}>
                  Retirar
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
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

// traços de 16px no estilo da interface: o ícone diz a etapa, o texto confirma
const ICONES: Record<string, ReactNode> = {
  EM_COLETA: <path d="M5 2.5h6M4 4h8v9.5H4zM6 7h4M6 9.5h4" />,
  EM_CONFERENCIA: <path d="M7 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8zm2.8 6.8L13 13" />,
  PRONTO_PARA_SIMULAR: <path d="M5.5 3.5v9l7-4.5z" />,
  SIMULADO: <path d="M3 13h10M4.5 11V8M8 11V4.5M11.5 11V6.5" />,
  APROVADO: <path d="M3.5 8.5l3 3 6-7" />,
  PRELIMINAR: <path d="M8 3.5v5.5M8 11.5v1" />,
  FINAL: <path d="M3.5 8.5l3 3 6-7" />,
};

function IconeStatus({ status }: { status: string }) {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {ICONES[status] ?? <circle cx="8" cy="8" r="2" />}
    </svg>
  );
}

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
      <IconeStatus status={status} />
      {STATUS[status] ?? status.charAt(0) + status.slice(1).toLowerCase()}
    </span>
  );
}

/** Campo monetário: vazio = não informado; 0,00 = informado. */
export function CampoMoeda({
  valor,
  onChange,
  rotulo,
  desabilitado,
}: {
  valor: number | null | undefined;
  onChange: (v: number | null) => void;
  rotulo: string;
  desabilitado?: boolean;
}) {
  const [texto, setTexto] = useState(editarMoeda(valor));
  const campo = useRef<HTMLInputElement>(null);
  // o valor pode mudar por fora (gravação recusada, dado recarregado): acompanha, mas não enquanto se digita
  useEffect(() => {
    if (document.activeElement !== campo.current) setTexto(editarMoeda(valor));
  }, [valor]);
  return (
    <input
      ref={campo}
      aria-label={rotulo}
      disabled={desabilitado}
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

/** Rodapé das listas paginadas: some quando a API não anuncia próxima página. */
export function CarregarMais({ lista }: { lista: { temMais: boolean; carregarMais: () => void; carregando: boolean } }) {
  if (!lista.temMais) return null;
  return (
    <div className="border-t border-border p-3 text-center">
      <Botao variante="secundario" disabled={lista.carregando} onClick={lista.carregarMais}>
        {lista.carregando ? "Carregando…" : "Carregar mais"}
      </Botao>
    </div>
  );
}
