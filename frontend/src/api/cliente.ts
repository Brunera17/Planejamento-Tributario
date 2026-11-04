import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

/**
 * Sessão: o access (JWT de 15 min) fica só em memória — nenhum script lê de localStorage.
 * O refresh mora num cookie HttpOnly que só vai para /api/auth; ao recarregar a página, /auth/refresh
 * recupera a sessão sem pedir a senha. No localStorage fica só o usuário (nome e perfil, para a tela).
 */
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "/api", // relativo: proxy do Vite no dev, rewrite da Vercel em produção
  withCredentials: true, // o cookie de refresh (só é enviado às rotas /auth)
  headers: { "X-Requested-With": "planejador" }, // proteção contra CSRF exigida pela API
});

const CHAVE = "planejador.sessao";

export type Usuario = { id: number; nome: string; usuario: string; perfil: "CONTADOR" | "ANALISTA" };
export type Sessao = { usuario: Usuario };
type RespostaSessao = { access: string; expira_em: string; sessao_expira_em: number; usuario: Usuario };

let access: string | null = null;

export function lerSessao(): Sessao | null {
  try {
    const s = localStorage.getItem(CHAVE);
    return s ? (JSON.parse(s) as Sessao) : null;
  } catch {
    return null;
  }
}

function gravarUsuario(u: Usuario | null) {
  try {
    if (u) localStorage.setItem(CHAVE, JSON.stringify({ usuario: u }));
    else localStorage.removeItem(CHAVE);
  } catch {
    /* armazenamento indisponível: o nome some ao recarregar, a sessão não */
  }
}

/** Grava a sessão recebida do login ou do refresh; null encerra localmente. */
export function gravarSessao(s: RespostaSessao | null) {
  access = s?.access ?? null;
  gravarUsuario(s?.usuario ?? null);
}

export function temAccess(): boolean {
  return access !== null;
}

// um único refresh em voo: as requisições que tomam 401 juntas esperam a mesma renovação
let renovando: Promise<boolean> | null = null;

export function renovarSessao(): Promise<boolean> {
  renovando ??= api
    .post<RespostaSessao>("/auth/refresh", null, { _semRenovar: true } as unknown as InternalAxiosRequestConfig)
    .then((r) => {
      gravarSessao(r.data);
      return true;
    })
    .catch(() => {
      gravarSessao(null);
      return false;
    })
    .finally(() => {
      renovando = null;
    });
  return renovando;
}

api.interceptors.request.use((cfg) => {
  if (access) cfg.headers.Authorization = `Bearer ${access}`;
  return cfg;
});

type ConfigComFlags = InternalAxiosRequestConfig & { _semRenovar?: boolean; _repetida?: boolean };

api.interceptors.response.use(
  (r) => r,
  async (e: AxiosError) => {
    const cfg = e.config as ConfigComFlags | undefined;
    const rotaDeLogin = cfg?.url?.includes("/auth/login");
    if (e.response?.status === 401 && cfg && !rotaDeLogin && !cfg._semRenovar && !cfg._repetida) {
      if (await renovarSessao()) {
        cfg._repetida = true;
        return api(cfg); // repete a original com o access novo
      }
      window.location.assign("/login");
    }
    return Promise.reject(e);
  },
);

/** Sai: a API derruba a sessão e apaga o cookie. */
export async function sair() {
  await api.post("/auth/logout").catch(() => undefined);
  gravarSessao(null);
}

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
