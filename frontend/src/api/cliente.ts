import axios, { AxiosError } from "axios";

export const api = axios.create({ baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000/api" });

const CHAVE = "planejador.sessao";

export type Usuario = { id: number; nome: string; usuario: string; perfil: "CONTADOR" | "ANALISTA" };
export type Sessao = { token: string; usuario: Usuario };

export function lerSessao(): Sessao | null {
  try {
    const s = localStorage.getItem(CHAVE);
    return s ? (JSON.parse(s) as Sessao) : null;
  } catch {
    return null;
  }
}

export function gravarSessao(s: Sessao | null) {
  try {
    if (s) localStorage.setItem(CHAVE, JSON.stringify(s));
    else localStorage.removeItem(CHAVE);
  } catch {
    /* armazenamento indisponível: a sessão vale só nesta aba */
  }
}

api.interceptors.request.use((cfg) => {
  const s = lerSessao();
  if (s) cfg.headers.Authorization = `Bearer ${s.token}`;
  return cfg;
});

api.interceptors.response.use(
  (r) => r,
  (e: AxiosError) => {
    if (e.response?.status === 401 && !e.config?.url?.includes("/auth/login")) {
      gravarSessao(null);
      window.location.assign("/login");
    }
    return Promise.reject(e);
  },
);

export type ErroApi = { erro: string; campos: Record<string, string> };

export function mensagemErro(e: unknown): string {
  const dados = (e as AxiosError<ErroApi>)?.response?.data;
  if (!dados) return "Falha de comunicação com o servidor";
  const campos = Object.entries(dados.campos ?? {}).map(([k, v]) => `${k}: ${v}`);
  return [dados.erro, ...campos].join(" — ");
}

/** Baixa um arquivo protegido pela sessão. */
export async function baixarArquivo(url: string, nome: string) {
  const r = await api.get(url, { responseType: "blob" }).catch(async (e: AxiosError<Blob>) => {
    // com responseType blob, o erro da API também chega como blob
    if (e.response?.data instanceof Blob) (e.response as { data: unknown }).data = JSON.parse(await e.response.data.text());
    throw e;
  });
  const link = URL.createObjectURL(r.data);
  Object.assign(document.createElement("a"), { href: link, download: nome }).click();
  URL.revokeObjectURL(link);
}
