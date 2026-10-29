import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import type { Empresa } from "../api/tipos";
import { Botao, Cabecalho, Card, Erro, Tabela } from "../components/ui";
import { formatarCnpj, REGIMES } from "../lib/formato";

type LinhaPrevia = { linha: number; dados: Record<string, string>; situacao: string; erros: string[]; avisos: string[] };

export function Empresas() {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const { data = [] } = useQuery({ queryKey: ["empresas"], queryFn: async () => (await api.get<Empresa[]>("/empresas")).data });
  return (
    <>
      <Cabecalho titulo="Empresas" descricao="Cadastro das empresas atendidas. A importação aceita a planilha do escritório (.xlsx ou .csv)." />
      {contador && <Importacao />}
      <Card titulo={`${data.length} ${data.length === 1 ? "empresa ativa" : "empresas ativas"}`} semPadding>
        <Tabela cabecalho={["Razão social", "CNPJ", "Regime", "UF", "Representante", "Telefone"]}>
          {data.map((e) => (
            <tr key={e.id}>
              <td className="px-4 py-2 font-medium">{e.razao_social}</td>
              <td className="px-2 py-2">{formatarCnpj(e.cnpj)}</td>
              <td className="px-2 py-2">{REGIMES[e.regime_tributario]}</td>
              <td className="px-2 py-2">{e.uf}</td>
              <td className="px-2 py-2">{e.representante_legal ?? "—"}</td>
              <td className="px-2 py-2">{e.telefone ?? "—"}</td>
            </tr>
          ))}
        </Tabela>
      </Card>
    </>
  );
}

function Importacao() {
  const qc = useQueryClient();
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [previa, setPrevia] = useState<LinhaPrevia[] | null>(null);
  const [resumo, setResumo] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const enviar = (rota: string) => {
    const fd = new FormData();
    fd.append("arquivo", arquivo!);
    return api.post(`/empresas/importacao/${rota}`, fd);
  };
  const verPrevia = useMutation({ mutationFn: () => enviar("previa"), onSuccess: (r) => setPrevia(r.data), onError: (e) => setErro(mensagemErro(e)) });
  const confirmar = useMutation({
    mutationFn: () => enviar("confirmar"),
    onSuccess: (r) => {
      setResumo(`Importação concluída: ${r.data.incluidas} incluídas, ${r.data.atualizadas} atualizadas e ${r.data.rejeitadas} rejeitadas.`);
      setPrevia(null);
      qc.invalidateQueries({ queryKey: ["empresas"] });
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  return (
    <Card titulo="Importar empresas">
      <p className="mb-3 max-w-[70ch] text-sm text-text-muted">
        A planilha precisa das colunas Empresa, CNPJ, Regime tributário, Representante legal e Telefone; UF e CNAE são opcionais. Antes de gravar, você confere linha a linha o que entra.
      </p>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <input type="file" accept=".xlsx,.csv" onChange={(e) => setArquivo(e.target.files?.[0] ?? null)} />
        <Botao variante="secundario" disabled={!arquivo} onClick={() => verPrevia.mutate()}>
          Ver prévia
        </Botao>
        {previa && (
          <Botao onClick={() => confirmar.mutate()} disabled={!previa.some((l) => l.situacao !== "ERRO")}>
            Confirmar linhas válidas
          </Botao>
        )}
      </div>
      <Erro mensagem={erro} />
      {resumo && <p className="mt-2 text-sm font-medium">{resumo}</p>}
      {previa && (
        <div className="mt-3">
          <Tabela cabecalho={["Linha", "Empresa", "CNPJ", "Situação", "Motivo / aviso"]}>
            {previa.map((l) => (
              <tr key={l.linha}>
                <td className="px-2 py-1">{l.linha}</td>
                <td className="px-2 py-1">{l.dados.razao_social}</td>
                <td className="px-2 py-1">{l.dados.cnpj}</td>
                <td className={`px-2 py-1 font-medium ${l.situacao === "ERRO" ? "text-alert" : ""}`}>
                  {l.situacao === "ERRO" ? "✖ Não será importada" : l.situacao === "EXISTENTE" ? "↻ Atualiza cadastro" : "✔ Nova empresa"}
                </td>
                <td className="px-2 py-1">{[...l.erros, ...l.avisos].join("; ")}</td>
              </tr>
            ))}
          </Tabela>
        </div>
      )}
    </Card>
  );
}
