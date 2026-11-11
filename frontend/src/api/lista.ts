import { useInfiniteQuery } from "@tanstack/react-query";

import { api } from "./cliente";

/** Listagem paginada da API: cada página vem como lista e a próxima é anunciada no cabeçalho X-Proximo. */
export function useLista<T>(chave: unknown[], rota: string, params: Record<string, unknown> = {}) {
  const q = useInfiniteQuery({
    queryKey: chave,
    initialPageParam: 0,
    queryFn: async ({ pageParam }) => {
      const r = await api.get<T[]>(rota, { params: { ...params, deslocamento: pageParam || undefined } });
      const proximo = r.headers["x-proximo"];
      return { itens: r.data, proximo: proximo ? Number(proximo) : undefined };
    },
    getNextPageParam: (ultima) => ultima.proximo,
  });
  return {
    // a paginação é por deslocamento: um cadastro novo entre páginas empurra uma linha para a página seguinte
    itens: [...new Map((q.data?.pages.flatMap((p) => p.itens) ?? []).map((x) => [(x as { id: number }).id, x])).values()],
    temMais: q.hasNextPage,
    carregarMais: () => q.fetchNextPage(),
    carregando: q.isFetchingNextPage,
    falhou: q.isFetchNextPageError,
  };
}
