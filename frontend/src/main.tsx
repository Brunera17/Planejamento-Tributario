import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { lerSessao } from "./api/cliente";
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

function Protegida({ children }: { children: React.ReactNode }) {
  return lerSessao() ? <>{children}</> : <Navigate to="/login" replace />;
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
