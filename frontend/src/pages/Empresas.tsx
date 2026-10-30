import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import type { Empresa } from "../api/tipos";
import { FormEmpresa } from "../components/FormEmpresa";
import { Botao, Cabecalho, Card, Erro, Tabela } from "../components/ui";
import { formatarCnpj, formatarTelefone, REGIMES } from "../lib/formato";

type LinhaPrevia = { linha: number; dados: Record<string, string>; situacao: string; erros: string[]; avisos: string[] };

export function Empresas() {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const qc = useQueryClient();
  const [inativas, setInativas] = useState(false);
  const [importando, setImportando] = useState(false);
  const [editando, setEditando] = useState<Empresa | "nova" | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const { data = [] } = useQuery({
    queryKey: ["empresas", inativas],
    queryFn: async () => (await api.get<Empresa[]>("/empresas", { params: { ativas: !inativas } })).data,
  });
  const atualizar = {
    onSuccess: () => {
      setErro(null);
      qc.invalidateQueries({ queryKey: ["empresas"] });
    },
    onError: (e: unknown) => setErro(mensagemErro(e)),
  };
  const remover = useMutation({ mutationFn: (id: number) => api.delete(`/empresas/${id}`), ...atualizar });
  const reativar = useMutation({ mutationFn: (id: number) => api.post(`/empresas/${id}/reativar`), ...atualizar });
  const ativas = data.filter((e) => e.ativo).length;

  return (
    <>
      <Cabecalho
        titulo="Empresas"
        descricao="Empresas atendidas pelo escritório. Importe a planilha para cadastrar várias de uma vez."
        acoes={
          contador && (
            <>
              <Botao variante="secundario" onClick={() => setImportando(!importando)} aria-expanded={importando}>
                Importar planilha
              </Botao>
              <Botao onClick={() => setEditando("nova")}>Nova empresa</Botao>
            </>
          )
        }
      />
      <Erro mensagem={erro} />
      {editando && <FormEmpresa key={editando === "nova" ? 0 : editando.id} empresa={editando === "nova" ? null : editando} fechar={() => setEditando(null)} />}
      {importando && <Importacao />}
      <Card
        titulo={`${ativas} ${ativas === 1 ? "empresa ativa" : "empresas ativas"}`}
        semPadding
        acoes={
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={inativas} onChange={(e) => setInativas(e.target.checked)} />
            Mostrar inativas
          </label>
        }
      >
        <Tabela cabecalho={["Razão social", "CNPJ", "Regime", "UF", "Representante", "Telefone", ""]}>
          {data.map((e) => (
            <tr key={e.id} className={e.ativo ? "" : "text-text-muted"}>
              <td className="px-4 py-2 font-medium">
                {e.razao_social}
                {!e.ativo && <span className="ml-1.5 font-normal">(inativa)</span>}
              </td>
              <td className="px-2 py-2">{formatarCnpj(e.cnpj)}</td>
              <td className="px-2 py-2">{REGIMES[e.regime_tributario]}</td>
              <td className="px-2 py-2">{e.uf}</td>
              <td className="px-2 py-2">{e.representante_legal ?? "—"}</td>
              <td className="whitespace-nowrap px-2 py-2">{formatarTelefone(e.telefone)}</td>
              <td className="whitespace-nowrap px-4 py-2 text-right">
                {contador && e.ativo && (
                  <>
                    <button
                      className="text-brand underline underline-offset-2"
                      onClick={() => {
                        setEditando(e);
                        window.scrollTo({ top: 0 });
                      }}
                    >
                      Editar
                    </button>
                    <button
                      className="ml-3 text-alert underline underline-offset-2"
                      onClick={() => window.confirm(`Remover ${e.razao_social}? Com planejamentos, ela fica inativa; sem planejamentos, é excluída com seus bens.`) && remover.mutate(e.id)}
                    >
                      Remover
                    </button>
                  </>
                )}
                {contador && !e.ativo && (
                  <button className="text-brand underline underline-offset-2" onClick={() => reativar.mutate(e.id)}>
                    Reativar
                  </button>
                )}
              </td>
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
