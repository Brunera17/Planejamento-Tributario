import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { api, lerSessao, mensagemErro, type Usuario } from "../api/cliente";
import { Botao, Cabecalho, Card, Erro, LegendaObrigatorio, Modal, Obrigatorio, Tabela } from "../components/ui";

type Linha = Usuario & { ativo: boolean };
const PERFIS = { CONTADOR: "Contador", ANALISTA: "Analista" };
const VAZIO = {
  nome: "",
  usuario: "",
  senha: "",
  perfil: "ANALISTA" as Usuario["perfil"],
  ativo: true,
};
const SENHA_MINIMA = 8;
const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5 disabled:bg-bg";

export function Usuarios() {
  const sessao = lerSessao();
  const contador = sessao?.usuario.perfil === "CONTADOR";
  const qc = useQueryClient();
  const [form, setForm] = useState(VAZIO);
  const [editando, setEditando] = useState<number | null>(null);
  const [aberto, setAberto] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const { data = [] } = useQuery({
    queryKey: ["usuarios"],
    enabled: contador,
    queryFn: async () => (await api.get<Linha[]>("/usuarios")).data,
  });

  function fechar() {
    setAberto(false);
    setEditando(null);
    setForm(VAZIO);
    setErro(null);
  }
  const salvar = useMutation({
    // axios 1.21 tipa a resposta pelo corpo enviado: put e post viram tipos diferentes, então não há retorno
    mutationFn: async () => {
      if (editando) {
        await api.put(`/usuarios/${editando}`, {
          nome: form.nome.trim(),
          perfil: form.perfil,
          ativo: form.ativo,
          senha: form.senha || null,
        });
      } else {
        await api.post("/usuarios", {
          nome: form.nome.trim(),
          usuario: form.usuario.trim(),
          senha: form.senha,
          perfil: form.perfil,
        });
      }
    },
    onSuccess: () => {
      fechar();
      qc.invalidateQueries({ queryKey: ["usuarios"] });
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  function enviar(e: FormEvent) {
    e.preventDefault();
    if (form.nome.trim().length < 2) return setErro("Informe o nome");
    if (!editando && !/^[A-Za-z0-9._-]{3,}$/.test(form.usuario.trim())) return setErro("O login tem ao menos 3 caracteres, sem espaços");
    if ((!editando || form.senha) && form.senha.length < SENHA_MINIMA) return setErro(`A senha precisa de ao menos ${SENHA_MINIMA} caracteres`);
    setErro(null);
    salvar.mutate();
  }

  if (!contador) return <p>Só o contador gerencia usuários.</p>;
  const proprio = editando === sessao?.usuario.id;

  return (
    <>
      <Cabecalho
        titulo="Usuários"
        descricao="Quem acessa o sistema. Não há autocadastro: as contas são criadas aqui."
        acoes={<Botao onClick={() => setAberto(true)}>Novo usuário</Botao>}
      />
      {aberto && (
        <Modal aberto fechar={fechar} titulo={editando ? "Editar usuário" : "Novo usuário"} descricao={editando ? form.usuario : undefined}>
          <form onSubmit={enviar} className="grid gap-3 text-sm md:grid-cols-4">
            <label className="md:col-span-2">
              Nome
              <Obrigatorio />
              <input autoFocus className={campo} maxLength={120} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} />
            </label>
            <label>
              Login{!editando && <Obrigatorio />}
              <input
                className={campo}
                maxLength={60}
                disabled={!!editando}
                autoComplete="off"
                value={form.usuario}
                onChange={(e) => setForm({ ...form, usuario: e.target.value })}
              />
            </label>
            <label>
              Perfil
              <Obrigatorio />
              <select
                className={campo}
                disabled={proprio}
                value={form.perfil}
                onChange={(e) =>
                  setForm({
                    ...form,
                    perfil: e.target.value as Usuario["perfil"],
                  })
                }
              >
                <option value="ANALISTA">Analista: preenche os dados</option>
                <option value="CONTADOR">Contador: confere, aprova e gerencia</option>
              </select>
            </label>
            <label className="md:col-span-2">
              {editando ? (
                "Nova senha (vazio mantém a atual)"
              ) : (
                <>
                  Senha inicial
                  <Obrigatorio />
                </>
              )}
              <input
                type="password"
                className={campo}
                maxLength={72}
                autoComplete="new-password"
                value={form.senha}
                onChange={(e) => setForm({ ...form, senha: e.target.value })}
              />
            </label>
            {editando && (
              <label className="flex items-center gap-2 self-end pb-2">
                <input type="checkbox" disabled={proprio} checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} />
                Usuário ativo
              </label>
            )}
            <div className="space-y-2 md:col-span-4">
              {proprio && <p className="text-text-muted">No próprio usuário, perfil e situação ficam travados para o sistema não ficar sem contador.</p>}
              <Erro mensagem={erro} />
              <div className="flex items-center justify-between gap-2 border-t border-surface pt-3">
                <LegendaObrigatorio />
                <div className="flex gap-2">
                  <Botao variante="secundario" onClick={fechar}>
                    Cancelar
                  </Botao>
                  <Botao type="submit" disabled={salvar.isPending}>
                    {editando ? "Salvar alterações" : "Criar usuário"}
                  </Botao>
                </div>
              </div>
            </div>
          </form>
        </Modal>
      )}
      <Card titulo={`${data.filter((u) => u.ativo).length} usuários ativos`} semPadding>
        <Tabela cabecalho={["Nome", "Login", "Perfil", "Situação", ""]}>
          {data.map((u) => (
            <tr key={u.id} className={u.ativo ? "" : "text-text-muted"}>
              <td className="px-4 py-2 font-medium">
                {u.nome}
                {u.id === sessao?.usuario.id && <span className="ml-1.5 font-normal text-text-muted">(você)</span>}
              </td>
              <td className="px-2 py-2">{u.usuario}</td>
              <td className="px-2 py-2">{PERFIS[u.perfil]}</td>
              <td className="px-2 py-2">{u.ativo ? "Ativo" : "– Inativo"}</td>
              <td className="px-4 py-2 text-right">
                <Botao
                  variante="linha"
                  onClick={() => {
                    setErro(null);
                    setEditando(u.id);
                    setForm({
                      nome: u.nome,
                      usuario: u.usuario,
                      senha: "",
                      perfil: u.perfil,
                      ativo: u.ativo,
                    });
                    setAberto(true);
                  }}
                >
                  Editar
                </Botao>
              </td>
            </tr>
          ))}
        </Tabela>
      </Card>
    </>
  );
}
