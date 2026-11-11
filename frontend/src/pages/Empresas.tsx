import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import { useLista } from "../api/lista";
import type { Empresa } from "../api/tipos";
import { FormEmpresa } from "../components/FormEmpresa";
import { Botao, Cabecalho, CarregarMais, Card, EnvioArquivo, Erro, Modal, Tabela, useConfirmacao } from "../components/ui";
import { dataHora, formatarCnpj, formatarTelefone, REGIMES } from "../lib/formato";

type LinhaPrevia = { linha: number; dados: Record<string, string>; situacao: string; erros: string[]; avisos: string[] };

export function Empresas() {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const qc = useQueryClient();
  const [confirmar, janelaConfirmacao] = useConfirmacao();
  const [inativas, setInativas] = useState(false);
  const [busca, setBusca] = useState("");
  const [importando, setImportando] = useState(false);
  const [editando, setEditando] = useState<Empresa | "nova" | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const lista = useLista<Empresa>(["empresas", inativas, busca], "/empresas", { ativas: !inativas, busca: busca || undefined });
  const data = lista.itens;
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

  async function pedirRemocao(e: Empresa) {
    const ok = await confirmar({
      titulo: "Remover empresa",
      mensagem: (
        <>
          <p className="font-medium">{e.razao_social}</p>
          <p className="mt-1 text-text-muted">Se a empresa tiver planejamentos, ela fica inativa e pode ser reativada. Sem planejamentos, é excluída junto com os bens cadastrados.</p>
        </>
      ),
      confirmar: "Remover empresa",
      perigo: true,
    });
    if (ok) remover.mutate(e.id);
  }

  return (
    <>
      <Cabecalho
        titulo="Empresas"
        descricao="Empresas atendidas pelo escritório. Importe a planilha para cadastrar várias de uma vez."
        acoes={
          contador && (
            <>
              <Botao variante="secundario" onClick={() => setImportando(true)}>
                Importar planilha
              </Botao>
              <Botao onClick={() => setEditando("nova")}>Nova empresa</Botao>
            </>
          )
        }
      />
      <Erro mensagem={erro} />
      {editando && <FormEmpresa key={editando === "nova" ? 0 : editando.id} empresa={editando === "nova" ? null : editando} fechar={() => setEditando(null)} />}
      {importando && <Importacao fechar={() => setImportando(false)} />}
      {janelaConfirmacao}
      <Card
        titulo={
          inativas // com inativas na lista, as páginas seguintes misturam as duas: conta só o que está na tela
            ? `${data.length}${lista.temMais ? "+" : ""} ${data.length === 1 ? "empresa" : "empresas"}`
            : `${ativas}${lista.temMais ? "+" : ""} ${ativas === 1 ? "empresa ativa" : "empresas ativas"}`
        }
        semPadding
        acoes={
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <input
              aria-label="Buscar por razão social ou CNPJ"
              placeholder="Razão social ou CNPJ"
              className="rounded border border-border px-2 py-1"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={inativas} onChange={(e) => setInativas(e.target.checked)} />
              Mostrar inativas
            </label>
          </div>
        }
      >
        <Tabela cabecalho={["Razão social", "CNPJ", "Regime", "UF", "Representante", "Telefone", "Cadastro", ""]}>
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
              <td className="num whitespace-nowrap px-2 py-2">{e.criado_em ? dataHora(e.criado_em) : "—"}</td>
              <td className="px-4 py-2">
                <div className="flex justify-end gap-1.5">
                  {contador && e.ativo && (
                    <>
                      <Botao variante="linha" onClick={() => setEditando(e)}>
                        Editar
                      </Botao>
                      <Botao variante="linha-perigo" onClick={() => pedirRemocao(e)}>
                        Remover
                      </Botao>
                    </>
                  )}
                  {contador && !e.ativo && (
                    <Botao variante="linha" onClick={() => reativar.mutate(e.id)}>
                      Reativar
                    </Botao>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </Tabela>
        <CarregarMais lista={lista} />
      </Card>
    </>
  );
}

function Importacao({ fechar }: { fechar: () => void }) {
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
  const verPrevia = useMutation({
    mutationFn: () => enviar("previa"),
    onSuccess: (r) => {
      setErro(null);
      setPrevia(r.data);
    },
    onError: (e) => setErro(mensagemErro(e)),
  });
  const confirmar = useMutation({
    mutationFn: () => enviar("confirmar"),
    onSuccess: (r) => {
      setResumo(`Importação concluída: ${r.data.incluidas} incluídas, ${r.data.atualizadas} atualizadas e ${r.data.rejeitadas} rejeitadas.`);
      setPrevia(null);
      setArquivo(null);
      qc.invalidateQueries({ queryKey: ["empresas"] });
    },
    onError: (e) => setErro(mensagemErro(e)),
  });
  const validas = previa?.filter((l) => l.situacao !== "ERRO").length ?? 0;

  return (
    <Modal
      aberto
      fechar={fechar}
      largura="max-w-4xl"
      titulo="Importar empresas"
      descricao="Colunas obrigatórias: Empresa, CNPJ e Regime tributário. Representante legal, Telefone, UF e CNAE são opcionais."
    >
      <div className="space-y-4 text-sm">
        {resumo ? (
          <p className="rounded border border-success/40 bg-success-soft px-3 py-2 font-medium text-success-ink">{resumo}</p>
        ) : (
          <EnvioArquivo
            formatos={[".xlsx", ".xls", ".csv"]}
            arquivos={arquivo ? [arquivo] : []}
            aoEscolher={(fs) => {
              setArquivo(fs[0] ?? null);
              setPrevia(null);
              setErro(null);
            }}
          />
        )}
        <Erro mensagem={erro} />
        {previa && (
          <>
            <p>
              {validas} de {previa.length} {previa.length === 1 ? "linha pode" : "linhas podem"} ser importadas.
              {validas < previa.length && " As linhas com erro ficam de fora; corrija a planilha e envie de novo se precisar delas."}
            </p>
            <div className="max-h-80 overflow-y-auto rounded border border-surface">
              <Tabela cabecalho={["Linha", "Empresa", "CNPJ", "Situação", "Motivo / aviso"]}>
                {previa.map((l) => (
                  <tr key={l.linha} className={l.situacao === "ERRO" ? "bg-alert-soft" : ""}>
                    <td className="px-2 py-1">{l.linha}</td>
                    <td className="px-2 py-1">{l.dados.razao_social}</td>
                    <td className="px-2 py-1">{l.dados.cnpj}</td>
                    <td className={`whitespace-nowrap px-2 py-1 font-medium ${l.situacao === "ERRO" ? "text-alert" : ""}`}>
                      {l.situacao === "ERRO" ? "Não será importada" : l.situacao === "EXISTENTE" ? "Atualiza cadastro" : "Nova empresa"}
                    </td>
                    <td className="px-2 py-1">{[...l.erros, ...l.avisos].join("; ")}</td>
                  </tr>
                ))}
              </Tabela>
            </div>
          </>
        )}
        <div className="flex justify-end gap-2 border-t border-surface pt-3">
          <Botao variante="secundario" onClick={fechar}>
            {resumo ? "Fechar" : "Cancelar"}
          </Botao>
          {!resumo &&
            (previa ? (
              <Botao onClick={() => confirmar.mutate()} disabled={!validas || confirmar.isPending}>
                Importar {validas} {validas === 1 ? "empresa" : "empresas"}
              </Botao>
            ) : (
              <Botao disabled={!arquivo || verPrevia.isPending} onClick={() => verPrevia.mutate()}>
                Conferir linhas
              </Botao>
            ))}
        </div>
      </div>
    </Modal>
  );
}
