// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import type { Planejamento as TPlanejamento } from "../api/tipos";
import { Planejamento } from "./Planejamento";

const post = vi.fn((_url: string, _corpo?: unknown) => Promise.resolve({ data: {} }));

vi.mock("../api/cliente", () => ({
  api: {
    get: vi.fn(() => Promise.resolve({ data: [] })),
    post: (url: string, corpo?: unknown) => post(url, corpo),
  },
  lerSessao: () => ({ usuario: { id: 1, nome: "Contador", usuario: "contador", perfil: "CONTADOR" } }),
  mensagemErro: () => "erro",
  baixarArquivo: vi.fn(),
}));

function planejamento(id: number, razao_social: string): TPlanejamento {
  return {
    id,
    empresa_id: id,
    razao_social,
    cnpj: "00000000000191",
    regime_tributario: "SIMPLES_NACIONAL",
    competencia_inicial: "2026-01",
    competencia_final: "2026-06",
    status: "EM_CONFERENCIA",
    progresso: 100,
    sem_bens: false,
    criado_em: "2026-07-01T00:00:00",
    documentos_faltando: 0,
    documentos_recebidos_em: null,
  };
}

beforeAll(() => {
  // o jsdom não abre <dialog> como modal
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.open = false;
  };
});

afterEach(() => {
  cleanup();
  post.mockClear();
});

describe("troca de planejamento", () => {
  it("não leva o estado da tela de um planejamento para o outro", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    // os dois já em cache: é quando o React reaproveita a tela em vez de mostrar "Carregando…"
    qc.setQueryData(["planejamento", "1"], planejamento(1, "Empresa Um Ltda"));
    qc.setQueryData(["planejamento", "2"], planejamento(2, "Empresa Dois Ltda"));
    const router = createMemoryRouter([{ path: "/planejamentos/:id", element: <Planejamento /> }], {
      initialEntries: ["/planejamentos/1?aba=simulacoes"],
    });
    render(
      <QueryClientProvider client={qc}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    // no planejamento 1, o contador começa a devolver e escreve o motivo
    await screen.findByText("Empresa Um Ltda");
    fireEvent.click(screen.getByRole("button", { name: "Devolver para a coleta" }));
    const motivo = screen.getByPlaceholderText("Diga o que precisa ser ajustado") as HTMLTextAreaElement;
    fireEvent.change(motivo, { target: { value: "Faltou a folha de março" } });

    // troca para o planejamento 2 sem fechar a janela
    await act(() => router.navigate("/planejamentos/2?aba=simulacoes"));
    await screen.findByText("Empresa Dois Ltda");

    // o motivo escrito para o 1 não aparece no 2, nem ao abrir a devolução de novo
    expect(screen.queryByDisplayValue("Faltou a folha de março")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Devolver para a coleta" }));
    const novo = screen.getByPlaceholderText("Diga o que precisa ser ajustado") as HTMLTextAreaElement;
    expect(novo.value).toBe("");
    expect(post).not.toHaveBeenCalled();
  });
});
