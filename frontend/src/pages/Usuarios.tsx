import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { api, lerSessao, mensagemErro, type Usuario } from "../api/cliente";
import { Botao, Cabecalho, Card, Erro, Tabela } from "../components/ui";

type Linha = Usuario & { ativo: boolean };
const PERFIS = { CONTADOR: "Contador", ANALISTA: "Analista" };
const VAZIO = { nome: "", usuario: "", senha: "", perfil: "ANALISTA" as Usuario["perfil"], ativo: true };
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
    mutationFn: () =>
      editando
        ? api.put(`/usuarios/${editando}`, { nome: form.nome.trim(), perfil: form.perfil, ativo: form.ativo, senha: form.senha || null })
        : api.post("/usuarios", { nome: form.nome.trim(), usuario: form.usuario.trim(), senha: form.senha, perfil: form.perfil }),
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
        acoes={!aberto && <Botao onClick={() => setAberto(true)}>Novo usuário</Botao>}
      />
      {aberto && (
        <Card titulo={editando ? `Editar ${form.usuario}` : "Novo usuário"}>
          <form onSubmit={enviar} className="grid gap-3 text-sm md:grid-cols-4">
            <label className="md:col-span-2">
              Nome
              <input autoFocus className={campo} maxLength={120} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} />
            </label>
            <label>
              Login
              <input className={campo} maxLength={60} disabled={!!editando} autoComplete="off" value={form.usuario} onChange={(e) => setForm({ ...form, usuario: e.target.value })} />
            </label>
            <label>
              Perfil
              <select className={campo} disabled={proprio} value={form.perfil} onChange={(e) => setForm({ ...form, perfil: e.target.value as Usuario["perfil"] })}>
                <option value="ANALISTA">Analista: preenche os dados</option>
                <option value="CONTADOR">Contador: confere, aprova e gerencia</option>
              </select>
            </label>
            <label className="md:col-span-2">
              {editando ? "Nova senha (vazio mantém a atual)" : "Senha inicial"}
              <input type="password" className={campo} maxLength={72} autoComplete="new-password" value={form.senha} onChange={(e) => setForm({ ...form, senha: e.target.value })} />
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
              <div className="flex gap-2">
                <Botao type="submit" disabled={salvar.isPending}>
                  {editando ? "Salvar alterações" : "Criar usuário"}
                </Botao>
                <Botao type="button" variante="secundario" onClick={fechar}>
                  Cancelar
                </Botao>
              </div>
            </div>
          </form>
        </Card>
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
                <button
                  className="text-brand underline underline-offset-2"
                  onClick={() => {
                    setErro(null);
                    setEditando(u.id);
                    setForm({ nome: u.nome, usuario: u.usuario, senha: "", perfil: u.perfil, ativo: u.ativo });
                    setAberto(true);
                    window.scrollTo({ top: 0 });
                  }}
                >
                  Editar
                </button>
              </td>
            </tr>
          ))}
        </Tabela>
      </Card>
    </>
  );
}
