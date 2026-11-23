import { type ReactNode, useId, useState } from "react";

import type { Empresa } from "../api/tipos";
import { formatarCnpj } from "../lib/formato";

const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";

/** Um campo só: digita para filtrar por razão social ou CNPJ e escolhe na lista que abre logo abaixo (teclado ou mouse). */
export function EscolhaEmpresa({
  busca,
  escolhida,
  opcoes,
  aoDigitar,
  aoEscolher,
  rotulo = "Empresa",
  placeholder = "Digite a razão social ou o CNPJ",
  vazio = "Nenhuma empresa encontrada",
  autoFocus,
}: {
  busca: string;
  escolhida: boolean;
  opcoes: Empresa[];
  aoDigitar: (t: string) => void;
  aoEscolher: (e: Empresa | null) => void;
  rotulo?: ReactNode;
  placeholder?: string;
  vazio?: string;
  autoFocus?: boolean;
}) {
  const id = useId();
  const [aberta, setAberta] = useState(false);
  const [ativa, setAtiva] = useState(0);
  const lista = opcoes.slice(0, 8);
  const mostrar = aberta && !escolhida;

  function escolher(e: Empresa) {
    aoEscolher(e);
    setAberta(false);
  }

  return (
    <div className="relative">
      <label htmlFor={`${id}-campo`}>{rotulo}</label>
      <div className="relative">
        <input
          id={`${id}-campo`}
          role="combobox"
          aria-expanded={mostrar}
          aria-controls={`${id}-lista`}
          aria-activedescendant={mostrar && lista[ativa] ? `${id}-${lista[ativa].id}` : undefined}
          autoComplete="off"
          autoFocus={autoFocus}
          placeholder={placeholder}
          className={`${campo} pr-8`}
          value={busca}
          onFocus={() => setAberta(true)}
          onBlur={() => setAberta(false)}
          onChange={(e) => {
            aoDigitar(e.target.value);
            setAtiva(0);
            setAberta(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              if (!mostrar) { // a primeira seta só abre a lista, já com a primeira empresa marcada
                setAtiva(0);
                return setAberta(true);
              }
              setAtiva((i) => Math.max(0, Math.min(i + 1, lista.length - 1)));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setAtiva((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter" && mostrar && lista[ativa]) {
              e.preventDefault();
              escolher(lista[ativa]);
            } else if (e.key === "Escape") {
              setAberta(false);
            }
          }}
        />
        {busca && (
          <button
            type="button"
            aria-label="Limpar empresa"
            className="absolute right-2 top-1/2 mt-0.5 -translate-y-1/2 px-1 text-text-muted hover:text-alert"
            onClick={() => aoEscolher(null)}
          >
            ×
          </button>
        )}
      </div>
      {mostrar && (
        <ul id={`${id}-lista`} role="listbox" className="absolute z-10 mt-1 max-h-64 w-full overflow-auto rounded border border-border bg-white text-sm">
          {lista.length === 0 ? (
            <li className="px-3 py-2 text-text-muted">{vazio}</li>
          ) : (
            lista.map((e, i) => (
              <li
                key={e.id}
                id={`${id}-${e.id}`}
                role="option"
                aria-selected={i === ativa}
                className={`cursor-pointer px-3 py-1.5 ${i === ativa ? "bg-highlight" : ""}`}
                onMouseDown={(ev) => ev.preventDefault()} // escolhe antes do blur fechar a lista
                onMouseEnter={() => setAtiva(i)}
                onClick={() => escolher(e)}
              >
                <span className="block">{e.razao_social}</span>
                <span className="num text-xs text-text-muted">{formatarCnpj(e.cnpj)}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
