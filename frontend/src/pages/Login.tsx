import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, gravarSessao, mensagemErro, type Sessao } from "../api/cliente";
import { Botao, Erro } from "../components/ui";

export function Login() {
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const navegar = useNavigate();

  async function entrar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    try {
      const { data } = await api.post<Sessao>("/auth/login", { usuario, senha });
      gravarSessao(data);
      navegar("/");
    } catch (err) {
      setErro(mensagemErro(err));
    }
  }

  return (
    <div className="grid min-h-screen md:grid-cols-[1fr_28rem]">
      <section className="flex flex-col justify-end bg-brand px-8 py-10 text-white md:px-14 md:py-16">
        <p className="expandido max-w-[16ch] text-balance text-[2.4rem] font-semibold leading-[1.1] tracking-tight">Simples, Presumido ou Real?</p>
        <p className="mt-4 max-w-[46ch] text-white/80">
          Compare os três regimes com as notas fiscais e despesas reais de cada empresa, inclusive na transição da Reforma Tributária.
        </p>
      </section>
      <form onSubmit={entrar} className="flex flex-col justify-center space-y-4 bg-white px-8 py-10 md:px-12">
        <h1>Entrar no Planejador Tributário</h1>
        <label className="block text-sm">
          Usuário
          <input className="mt-1 w-full rounded border border-border px-2 py-2" value={usuario} onChange={(e) => setUsuario(e.target.value)} autoFocus />
        </label>
        <label className="block text-sm">
          Senha
          <input type="password" className="mt-1 w-full rounded border border-border px-2 py-2" value={senha} onChange={(e) => setSenha(e.target.value)} />
        </label>
        <Erro mensagem={erro} />
        <Botao type="submit" className="w-full py-2">
          Entrar
        </Botao>
      </form>
    </div>
  );
}
