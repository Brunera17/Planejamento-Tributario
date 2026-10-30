import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import { Botao, Cabecalho, Card, Erro, Tabela } from "../components/ui";
import { brl } from "../lib/formato";

type RegraCfop = { cfop: number; natureza: string; gera_receita: boolean };
type ItemLei = { anexo: string; item: number | null; codigo: string; ex: string[]; condicao: string | null; nota: string | null };
type BaseLegal = { norma: string; fonte: string; consultado_em: string; aviso: string; itens: ItemLei[] };
type Pendente = { codigo: string | number; produto_exemplo: string | null; valor: number; planejamentos: number };

const ncmFmt = (n: string) => (n.length === 8 ? `${n.slice(0, 4)}.${n.slice(4, 6)}.${n.slice(6)}` : n);
const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";

const ENQUADRAMENTO: Record<string, string> = { MONOFASICO: "Na lei", CONDICIONAL: "Depende de confirmação", NAO_LISTADO: "Fora da lei" };

export function Regras() {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const [cfop, setCfop] = useState<RegraCfop | null>(null);
  const [busca, setBusca] = useState("");

  const { data: base } = useQuery({ queryKey: ["base-legal"], queryFn: async () => (await api.get<BaseLegal>("/tabelas/lei-monofasico")).data });
  const { data: cfops = [] } = useQuery({ queryKey: ["regras-cfop"], queryFn: async () => (await api.get<RegraCfop[]>("/tabelas/cfop")).data });
  const { data: cfopPendentes = [] } = useQuery({ queryKey: ["cfop-pendentes"], queryFn: async () => (await api.get<Pendente[]>("/tabelas/cfop/pendentes")).data });

  const digitos = busca.replace(/\D/g, "");
  const { data: consulta } = useQuery({
    queryKey: ["lei-ncm", digitos],
    enabled: digitos.length === 8,
    queryFn: async () => (await api.get<{ consulta: { enquadramento: string; motivo: string; fundamento: string | null } }>("/tabelas/lei-monofasico", { params: { ncm: digitos } })).data.consulta,
  });
  const itens = (base?.itens ?? []).filter((i) => !busca.trim() || digitos.startsWith(i.codigo.replace(/\./g, "")) || i.codigo.replace(/\./g, "").startsWith(digitos) && digitos.length > 0);

  return (
    <>
      <Cabecalho
        titulo="Base legal e CFOP"
        descricao="Os produtos de cada planejamento são confrontados com esta base. Inconsistências e correções ficam na aba Revisão de produtos do planejamento."
        acoes={contador && <Botao variante="secundario" onClick={() => setCfop({ cfop: 0, natureza: "", gera_receita: true })}>Novo CFOP</Botao>}
      />

      {cfop && <FormCfop inicial={cfop} fechar={() => setCfop(null)} />}

      {cfopPendentes.length > 0 && (
        <Card titulo="CFOP sem regra" semPadding>
          <Tabela cabecalho={["CFOP", "Produto de exemplo", "Valor nas notas", "Planejamentos", ""]} numericas={[2, 3]}>
            {cfopPendentes.map((p) => (
              <tr key={p.codigo} className="bg-alert-soft">
                <td className="px-4 py-2 font-medium">{p.codigo}</td>
                <td className="px-2 py-2">{p.produto_exemplo ?? "–"}</td>
                <td className="num px-2 py-2">{brl(p.valor)}</td>
                <td className="num px-2 py-2">{p.planejamentos}</td>
                <td className="px-4 py-2 text-right">
                  {contador && (
                    <button className="text-brand underline underline-offset-2" onClick={() => setCfop({ cfop: Number(p.codigo), natureza: "", gera_receita: true })}>
                      Classificar
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </Tabela>
        </Card>
      )}

      <Card
        titulo={base?.norma ?? "Base legal"}
        semPadding
        acoes={<input aria-label="Consultar NCM" placeholder="Consultar NCM" inputMode="numeric" maxLength={10} className="rounded border border-border px-2 py-1 text-sm" value={busca} onChange={(e) => setBusca(e.target.value)} />}
      >
        <div className="space-y-1 p-4 text-sm">
          {consulta && digitos.length === 8 && (
            <p className="font-medium">
              NCM {ncmFmt(digitos)}: {ENQUADRAMENTO[consulta.enquadramento]}. {consulta.motivo}
            </p>
          )}
          <p className="text-text-muted">
            Somente leitura. Fonte: <a className="text-brand underline underline-offset-2" href={base?.fonte} target="_blank" rel="noreferrer">texto atualizado da Câmara dos Deputados</a>, consultado em {base?.consultado_em.split("-").reverse().join("/")}. {base?.aviso}
          </p>
        </div>
        <Tabela cabecalho={["Anexo", "Código", "Ex", "Condição da lei"]}>
          {itens.map((i) => (
            <tr key={`${i.anexo}-${i.item ?? i.codigo}`}>
              <td className="px-4 py-2">{i.anexo}{i.item ? `, item ${i.item}` : ""}</td>
              <td className="whitespace-nowrap px-2 py-2 font-medium">{i.codigo}</td>
              <td className="px-2 py-2">{i.ex.length ? i.ex.join(" e ") : "–"}</td>
              <td className="px-2 py-2">{i.condicao ?? "Sem condição adicional"}</td>
            </tr>
          ))}
        </Tabela>
      </Card>

      <Card titulo={`${cfops.length} regras de CFOP`} semPadding>
        <Tabela cabecalho={["CFOP", "Natureza", "Gera receita", ""]}>
          {cfops.map((c) => (
            <tr key={c.cfop}>
              <td className="px-4 py-2 font-medium">{c.cfop}</td>
              <td className="px-2 py-2">{c.natureza}</td>
              <td className="px-2 py-2">{c.gera_receita ? "Sim" : "Não"}</td>
              <td className="px-4 py-2 text-right">
                {contador && (
                  <button className="text-brand underline underline-offset-2" onClick={() => { setCfop(c); window.scrollTo({ top: 0 }); }}>
                    Editar
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

function useConcluir(fechar: () => void) {
  const qc = useQueryClient();
  return () => {
    // a regra muda progresso e simulações de todos os planejamentos que usam o código
    qc.invalidateQueries();
    fechar();
  };
}

function FormCfop({ inicial, fechar }: { inicial: RegraCfop; fechar: () => void }) {
  const [f, setF] = useState(inicial);
  const [erro, setErro] = useState<string | null>(null);
  const concluir = useConcluir(fechar);
  useEffect(() => setF(inicial), [inicial]);
  const salvar = useMutation({ mutationFn: () => api.put("/tabelas/cfop", f), onSuccess: concluir, onError: (e) => setErro(mensagemErro(e)) });

  function enviar(e: FormEvent) {
    e.preventDefault();
    if (f.cfop < 1000 || f.cfop > 7999) return setErro("O CFOP tem 4 dígitos");
    if (f.natureza.trim().length < 3) return setErro("Descreva a natureza da operação");
    salvar.mutate();
  }

  return (
    <Card titulo="Regra de CFOP">
      <form onSubmit={enviar} className="grid gap-3 text-sm md:grid-cols-[8rem_1fr]">
        <label>
          CFOP
          <input className={campo} inputMode="numeric" maxLength={4} value={f.cfop || ""} onChange={(e) => setF({ ...f, cfop: Number(e.target.value.replace(/\D/g, "")) })} />
        </label>
        <label>
          Natureza da operação
          <input className={campo} maxLength={200} value={f.natureza} onChange={(e) => setF({ ...f, natureza: e.target.value })} />
        </label>
        <label className="flex items-center gap-2 md:col-span-2">
          <input type="checkbox" checked={f.gera_receita} onChange={(e) => setF({ ...f, gera_receita: e.target.checked })} />
          Gera receita (venda). Desmarque para remessas e outras saídas sem faturamento.
        </label>
        <div className="space-y-2 md:col-span-2">
          <Erro mensagem={erro} />
          <div className="flex gap-2">
            <Botao type="submit" disabled={salvar.isPending}>
              Salvar regra
            </Botao>
            <Botao type="button" variante="secundario" onClick={fechar}>
              Cancelar
            </Botao>
          </div>
        </div>
      </form>
    </Card>
  );
}
