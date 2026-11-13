import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, baixarArquivo, lerSessao, mensagemErro } from "../api/cliente";
import { Botao, Card, Erro, Ficha, Modal, Obrigatorio, Tabela, useConfirmacao } from "../components/ui";
import { brl } from "../lib/formato";

type Alerta = { tipo: string; rotulo: string; trava: boolean };
type Produto = {
  id_revisao: number | null;
  cod_produto: string;
  descricao: string;
  ncm_nota: string;
  ncm: string;
  receita: number;
  csts: string[];
  enquadramento: "MONOFASICO" | "CONDICIONAL" | "NAO_LISTADO";
  fundamento: string | null;
  motivo_lei: string;
  condicional: boolean;
  monofasico: boolean;
  sem_st: boolean;
  pendente: boolean;
  revisado: boolean;
  alertas: Alerta[];
  motivo: string | null;
  revisado_por: string | null;
  revisado_em: string | null;
  revisao_herdada: { planejamento_id: number; periodo: string | null } | null;
};
type TipoResumo = { rotulo: string; trava: boolean; produtos: number; receita: number };
type Dados = {
  resumo: { produtos: number; pendentes: number; revisados: number; receita_pendente: number; por_tipo: Record<string, TipoResumo> };
  produtos: Produto[];
};

const ncmFmt = (n: string) => (n.length === 8 ? `${n.slice(0, 4)}.${n.slice(4, 6)}.${n.slice(6)}` : n);
const ENQUADRAMENTO = { MONOFASICO: "Na lei", CONDICIONAL: "Depende de confirmação", NAO_LISTADO: "Fora da lei" };
const FILTROS = [
  { id: "pendentes", rotulo: "Para revisar" },
  { id: "avisos", rotulo: "Avisos" },
  { id: "revisados", rotulo: "Revisados" },
  { id: "todos", rotulo: "Todos" },
];

/** Confronto dos produtos vendidos com a Lei 10.485/2002: o sistema aponta, o contador decide. */
export function Revisao({ pid }: { pid: number }) {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const qc = useQueryClient();
  const [confirmar, janelaConfirmacao] = useConfirmacao();
  const [filtro, setFiltro] = useState("pendentes");
  const [tipo, setTipo] = useState<string | null>(null);
  const [aberto, setAberto] = useState<Produto | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["revisao", pid], queryFn: async () => (await api.get<Dados>(`/planejamentos/${pid}/revisao`)).data });

  function atualizar() {
    qc.invalidateQueries({ queryKey: ["revisao", pid] });
    qc.invalidateQueries({ queryKey: ["progresso", pid] });
    qc.invalidateQueries({ queryKey: ["planejamento", String(pid)] });
    qc.invalidateQueries({ queryKey: ["simulacoes", pid] });
  }
  const desfazer = useMutation({
    mutationFn: (id: number) => api.delete(`/planejamentos/${pid}/revisao/${id}`),
    onSuccess: () => {
      setErro(null);
      atualizar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  if (!data) return <p>Carregando…</p>;
  const { resumo, produtos } = data;
  if (produtos.length === 0) return <Card>Importe as notas de saída para o sistema confrontar os produtos com a lei.</Card>;

  const visiveis = produtos.filter((p) => {
    if (tipo) return p.alertas.some((a) => a.tipo === tipo);
    if (filtro === "pendentes") return p.pendente;
    if (filtro === "avisos") return !p.pendente && p.alertas.length > 0;
    if (filtro === "revisados") return p.revisado;
    return true;
  });
  const tipos = Object.entries(resumo.por_tipo).filter(([, t]) => t.produtos > 0);

  return (
    <div className="space-y-4">
      <Ficha
        campos={[
          { rotulo: "Produtos vendidos", valor: resumo.produtos },
          { rotulo: "Aguardando revisão", valor: resumo.pendentes },
          { rotulo: "Revisados", valor: resumo.revisados },
          { rotulo: "Receita aguardando revisão", valor: brl(resumo.receita_pendente) },
        ]}
      />
      <Erro mensagem={erro} />
      {resumo.pendentes > 0 ? (
        <p className="text-sm text-warning-ink">Enquanto houver produtos para revisar, a simulação sai como preliminar. O cálculo usa a presunção indicada em cada produto.</p>
      ) : (
        <p className="text-sm text-success-ink">✔ Nenhum produto trava a simulação final.</p>
      )}
      {janelaConfirmacao}
      {aberto && <FormRevisao key={`${aberto.cod_produto}-${aberto.ncm_nota}`} pid={pid} produto={aberto} fechar={() => setAberto(null)} concluido={atualizar} />}
      <Card
        titulo={`${visiveis.length} ${visiveis.length === 1 ? "produto" : "produtos"}`}
        semPadding
        acoes={
          <div className="flex flex-wrap items-center gap-1 text-sm">
            {FILTROS.map((f) => (
              <button
                key={f.id}
                aria-pressed={!tipo && filtro === f.id}
                className={`rounded px-2 py-1 ${!tipo && filtro === f.id ? "bg-brand text-white" : "hover:bg-highlight"}`}
                onClick={() => {
                  setTipo(null);
                  setFiltro(f.id);
                }}
              >
                {f.rotulo}
              </button>
            ))}
            <select aria-label="Filtrar por inconsistência" className="ml-1 rounded border border-border px-2 py-1" value={tipo ?? ""} onChange={(e) => setTipo(e.target.value || null)}>
              <option value="">Por inconsistência</option>
              {tipos.map(([k, t]) => (
                <option key={k} value={k}>
                  {t.rotulo} ({t.produtos})
                </option>
              ))}
            </select>
            <Botao
              variante="secundario"
              className="ml-1"
              onClick={() => baixarArquivo(`/planejamentos/${pid}/revisao/exportar`, "revisao-de-produtos.csv").catch((e) => setErro(mensagemErro(e)))}
            >
              Exportar lista
            </Botao>
          </div>
        }
      >
        {visiveis.length === 0 ? (
          <p className="p-4 text-text-muted">Nenhum produto neste filtro.</p>
        ) : (
          <Tabela cabecalho={["Produto", "NCM", "Lei 10.485/2002", "PIS/COFINS no cálculo", "Receita", "Inconsistência", ""]} numericas={[4]}>
            {visiveis.map((p) => (
              <tr key={`${p.cod_produto}-${p.ncm_nota}`} className={p.pendente ? "bg-warning-soft/60" : ""}>
                <td className="px-4 py-2">
                  <span className="font-medium">{p.descricao || "Itens agregados por NCM"}</span>
                  {p.cod_produto && <span className="block text-xs text-text-muted">{p.cod_produto}</span>}
                </td>
                <td className="whitespace-nowrap px-2 py-2">
                  {ncmFmt(p.ncm)}
                  {p.ncm !== p.ncm_nota && <span className="block text-xs text-text-muted">na nota: {ncmFmt(p.ncm_nota)}</span>}
                </td>
                <td className="px-2 py-2" title={p.motivo_lei}>
                  {ENQUADRAMENTO[p.enquadramento]}
                  {p.fundamento && <span className="block text-xs text-text-muted">{p.fundamento.replace("Lei 10.485/2002, ", "")}</span>}
                </td>
                <td className="px-2 py-2">
                  {p.monofasico ? "Monofásico" : "Tributado"}
                  {p.sem_st && <span className="block text-xs text-text-muted">Produção própria, sem ST</span>}
                  {p.csts.length > 0 && <span className="block text-xs text-text-muted">CST na nota: {p.csts.join(", ")}</span>}
                </td>
                <td className="num px-2 py-2">{brl(Number(p.receita))}</td>
                <td className="px-2 py-2 text-xs">
                  {p.alertas.map((a) => (
                    <span key={a.tipo} className="block">
                      {a.trava && !p.revisado ? "! " : ""}
                      {a.rotulo}
                    </span>
                  ))}
                  {p.revisado && (
                    <span className="block text-success-ink" title={p.motivo ?? ""}>
                      ✔ Revisado por {p.revisado_por}
                      {p.revisao_herdada && (
                        <span className="block text-xs text-text-muted">
                          {p.revisado_em ? `em ${new Date(p.revisado_em).toLocaleDateString("pt-BR")}, ` : ""}no planejamento{" "}
                          {p.revisao_herdada.periodo ?? `#${p.revisao_herdada.planejamento_id}`}
                        </span>
                      )}
                    </span>
                  )}
                </td>
                <td className="px-4 py-2">
                  <div className="flex justify-end gap-1.5">
                    {contador && (
                      <Botao variante="linha" onClick={() => setAberto(p)}>
                        {p.revisado ? "Alterar" : "Revisar"}
                      </Botao>
                    )}
                    {contador && p.id_revisao && (
                      <Botao
                        variante="linha-perigo"
                        onClick={async () =>
                          (await confirmar({
                            titulo: "Desfazer revisão",
                            mensagem: "O produto volta a seguir só a lei e, se a lei pedir confirmação, volta a travar a simulação final.",
                            confirmar: "Desfazer revisão",
                            perigo: true,
                          })) && desfazer.mutate(p.id_revisao!)
                        }
                      >
                        Desfazer
                      </Botao>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </Tabela>
        )}
      </Card>
    </div>
  );
}

function FormRevisao({ pid, produto, fechar, concluido }: { pid: number; produto: Produto; fechar: () => void; concluido: () => void }) {
  const [ncm, setNcm] = useState(produto.ncm);
  const [decisao, setDecisao] = useState<"SIM" | "NAO" | null>(produto.revisado && produto.condicional ? (produto.monofasico ? "SIM" : "NAO") : null);
  const [motivo, setMotivo] = useState(produto.motivo ?? "");
  const [semSt, setSemSt] = useState(produto.sem_st);
  const [erro, setErro] = useState<string | null>(null);
  const valido = /^\d{8}$/.test(ncm);
  const { data: consulta } = useQuery({
    queryKey: ["lei-ncm", ncm],
    enabled: valido,
    queryFn: async () => (await api.get<{ consulta: { enquadramento: Produto["enquadramento"]; motivo: string; fundamento: string | null } }>("/tabelas/lei-monofasico", { params: { ncm } })).data.consulta,
  });
  const condicional = consulta?.enquadramento === "CONDICIONAL";
  const salvar = useMutation({
    mutationFn: () =>
      api.put(`/planejamentos/${pid}/revisao`, {
        cod_produto: produto.cod_produto, ncm_nota: produto.ncm_nota, ncm_corrigido: ncm === produto.ncm_nota ? null : ncm,
        monofasico: condicional ? decisao === "SIM" : null, sem_st: semSt, motivo: motivo.trim(),
      }),
    onSuccess: () => {
      concluido();
      fechar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });
  const pronto = valido && consulta && motivo.trim().length >= 5 && (!condicional || decisao);

  return (
    <Modal aberto fechar={fechar} titulo="Revisar produto" descricao={produto.descricao || `Itens agregados no NCM ${ncmFmt(produto.ncm_nota)}`}>
      <div className="grid gap-4 text-sm md:grid-cols-[14rem_1fr]">
        <label>
          NCM a usar no cálculo<Obrigatorio />
          <input
            inputMode="numeric"
            maxLength={8}
            className="mt-1 block w-full rounded border border-border bg-white px-2 py-1.5"
            value={ncm}
            onChange={(e) => {
              setNcm(e.target.value.replace(/\D/g, ""));
              setDecisao(null);
            }}
          />
          <span className="mt-1 block text-xs text-text-muted">Na nota: {ncmFmt(produto.ncm_nota)}. A correção vale só para este planejamento; o cadastro é corrigido pelo cliente.</span>
        </label>
        <div>
          <p className="font-medium">O que diz a lei</p>
          {consulta && valido ? (
            <>
              <p>{ENQUADRAMENTO[consulta.enquadramento]}: {consulta.motivo}</p>
              {consulta.fundamento && <p className="text-text-muted">{consulta.fundamento}</p>}
            </>
          ) : (
            <p className="text-text-muted">Informe um NCM de 8 dígitos.</p>
          )}
        </div>
        {condicional && (
          <fieldset className="md:col-span-2">
            <legend className="mb-1 font-medium">
              Depois de conferir, este produto é monofásico?<Obrigatorio />
            </legend>
            <div className="flex gap-4">
              {(["SIM", "NAO"] as const).map((v) => (
                <label key={v} className="flex items-center gap-1.5">
                  <input type="radio" name="decisao" checked={decisao === v} onChange={() => setDecisao(v)} />
                  {v === "SIM" ? "Sim, atende à condição da lei" : "Não atende"}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <label className="flex items-start gap-2 md:col-span-2">
          <input type="checkbox" className="mt-1" checked={semSt} onChange={(e) => setSemSt(e.target.checked)} />
          <span>
            Produção própria: sem ICMS-ST
            <span className="block text-xs text-text-muted">
              Para o que a empresa prepara, como lanches e pizzas de um restaurante. A tabela de ST é por NCM e não separa o produto industrializado revendido do
              preparado na casa.
            </span>
          </span>
        </label>
        <label className="md:col-span-2">
          Motivo da decisão<Obrigatorio />
          <textarea
            rows={2}
            maxLength={500}
            className="mt-1 block w-full rounded border border-border bg-white px-2 py-1.5"
            placeholder="Ex.: Ex 01 confirmado na nota do fornecedor nº 1234"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
          />
        </label>
        <div className="space-y-2 md:col-span-2">
          <Erro mensagem={erro} />
          <div className="flex justify-end gap-2 border-t border-surface pt-3">
            <Botao variante="secundario" onClick={fechar}>
              Cancelar
            </Botao>
            <Botao disabled={!pronto || salvar.isPending} onClick={() => salvar.mutate()}>
              Salvar revisão
            </Botao>
          </div>
        </div>
      </div>
    </Modal>
  );
}
