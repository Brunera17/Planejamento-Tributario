import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { renovarSessao, temAccess } from "./api/cliente";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { Empresas } from "./pages/Empresas";
import { Login } from "./pages/Login";
import { Planejamento } from "./pages/Planejamento";
import { Planejamentos } from "./pages/Planejamentos";
import { Regras } from "./pages/Regras";
import { Resultado } from "./pages/Resultado";
import { Usuarios } from "./pages/Usuarios";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

/** O access vive só em memória: ao abrir ou recarregar, recupera a sessão pelo cookie de refresh. */
function Protegida({ children }: { children: React.ReactNode }) {
  const [estado, setEstado] = useState<"carregando" | "ok" | "anonimo">(temAccess() ? "ok" : "carregando");
  useEffect(() => {
    if (estado === "carregando") renovarSessao().then((ok) => setEstado(ok ? "ok" : "anonimo"));
  }, [estado]);
  if (estado === "carregando") return <div className="p-8 text-sm text-black/60">Carregando…</div>;
  return estado === "ok" ? <>{children}</> : <Navigate to="/login" replace />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <Protegida>
                <Layout />
              </Protegida>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="planejamentos" element={<Planejamentos />} />
            <Route path="planejamentos/:id" element={<Planejamento />} />
            <Route path="simulacoes/:id" element={<Resultado />} />
            <Route path="empresas" element={<Empresas />} />
            <Route path="regras" element={<Regras />} />
            <Route path="usuarios" element={<Usuarios />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
