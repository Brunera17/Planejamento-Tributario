import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { api, gravarSessao, lerSessao } from "../api/cliente";

const MENU = [
  { para: "/", rotulo: "Visão geral" },
  { para: "/planejamentos", rotulo: "Planejamentos" },
  { para: "/empresas", rotulo: "Empresas" },
  { para: "/regras", rotulo: "Base legal e CFOP" },
];

export function Layout() {
  const sessao = lerSessao();
  const navegar = useNavigate();

  async function sair() {
    await api.post("/auth/logout").catch(() => undefined);
    gravarSessao(null);
    navegar("/login");
  }

  return (
    <div className="min-h-screen md:grid md:grid-cols-[14rem_1fr]">
      <aside className="flex flex-col bg-brand text-white md:sticky md:top-0 md:h-screen">
        <div className="px-5 pb-4 pt-5">
          <div className="expandido text-lg font-semibold leading-tight">Planejador</div>
          <div className="text-sm text-white/70">tributário</div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 md:flex-col" aria-label="Principal">
          {[...MENU, ...(sessao?.usuario.perfil === "CONTADOR" ? [{ para: "/usuarios", rotulo: "Usuários" }] : [])].map((m) => (
            <NavLink
              key={m.para}
              to={m.para}
              end={m.para === "/"}
              className={({ isActive }) =>
                `whitespace-nowrap rounded px-3 py-2 text-sm ${isActive ? "bg-white font-medium text-brand" : "text-white/85 hover:bg-white/10"}`
              }
            >
              {m.rotulo}
            </NavLink>
          ))}
          <button onClick={sair} className="whitespace-nowrap rounded px-3 py-2 text-sm text-white/85 md:hidden">
            Sair
          </button>
        </nav>
        <div className="mt-auto hidden border-t border-white/15 px-5 py-4 text-sm md:block">
          <div className="font-medium">{sessao?.usuario.nome}</div>
          <div className="text-white/70">{sessao?.usuario.perfil === "CONTADOR" ? "Contador" : "Analista"}</div>
          <button onClick={sair} className="mt-2 text-white/85 underline underline-offset-2 hover:text-white">
            Sair
          </button>
        </div>
      </aside>
      <main className="mx-auto w-full max-w-6xl space-y-5 px-4 py-6 md:px-8 md:py-8">
        <Outlet />
      </main>
    </div>
  );
}
