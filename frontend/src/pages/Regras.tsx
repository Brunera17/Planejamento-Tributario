import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, lerSessao, mensagemErro } from "../api/cliente";
import { Botao, Cabecalho, Card, Erro, Tabela } from "../components/ui";
import { brl } from "../lib/formato";

type RegraNcm = {
  ncm: string;
  monofasico: boolean;
  confianca: "ALTA" | "MEDIA";
  sujeito_st: boolean;
  indicio_ncm_incorreto: boolean;
  requer_revisao: boolean;
  acao_recomendada: string | null;
  cst_ibs_cbs: string | null;
  cclass_trib: string | null;
  beneficio_reforma: string | null;
  fundamento: string | null;
  produto_exemplo: string | null;
  observacao: string | null;
};
type RegraCfop = { cfop: number; natureza: string; gera_receita: boolean };
type Pendente = { codigo: string | number; produto_exemplo: string | null; valor: number; planejamentos: number };

const NOVO_NCM: RegraNcm = {
  ncm: "",
  monofasico: false,
  confianca: "ALTA",
  sujeito_st: false,
  indicio_ncm_incorreto: false,
  requer_revisao: false,
  acao_recomendada: "",
  cst_ibs_cbs: "000",
  cclass_trib: "000001",
  beneficio_reforma: "Não – alíquota padrão",
  fundamento: "",
  produto_exemplo: "",
  observacao: "",
};
const ncmFmt = (n: string) => (n.length === 8 ? `${n.slice(0, 4)}.${n.slice(4, 6)}.${n.slice(6)}` : n);
const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";

export function Regras() {
  const contador = lerSessao()?.usuario.perfil === "CONTADOR";
  const [params] = useSearchParams();
  const [ncm, setNcm] = useState<RegraNcm | null>(null);
  const [cfop, setCfop] = useState<RegraCfop | null>(null);
  const [busca, setBusca] = useState("");

  const { data: regras = [] } = useQuery({ queryKey: ["regras-ncm"], queryFn: async () => (await api.get<RegraNcm[]>("/tabelas/ncm")).data });
  const { data: cfops = [] } = useQuery({ queryKey: ["regras-cfop"], queryFn: async () => (await api.get<RegraCfop[]>("/tabelas/cfop")).data });
  const { data: ncmPendentes = [] } = useQuery({ queryKey: ["ncm-pendentes"], queryFn: async () => (await api.get<Pendente[]>("/tabelas/ncm/pendentes")).data });
  const { data: cfopPendentes = [] } = useQuery({ queryKey: ["cfop-pendentes"], queryFn: async () => (await api.get<Pendente[]>("/tabelas/cfop/pendentes")).data });

  // vindo das pendências de um planejamento, já abre a classificação do NCM
  const pedido = params.get("ncm");
  useEffect(() => {
    if (pedido && contador && regras.length && !regras.some((r) => r.ncm === pedido)) {
      setNcm({ ...NOVO_NCM, ncm: pedido, produto_exemplo: ncmPendentes.find((p) => p.codigo === pedido)?.produto_exemplo ?? "" });
    }
  }, [pedido, contador, regras, ncmPendentes]);

  const texto = busca.trim().toLowerCase();
  const visiveis = regras.filter((r) => !texto || r.ncm.includes(texto.replace(/\D/g, "") || "#") || (r.produto_exemplo ?? "").toLowerCase().includes(texto));
  const totalPendentes = ncmPendentes.length + cfopPendentes.length;

  return (
    <>
      <Cabecalho
        titulo="Regras de NCM e CFOP"
        descricao={
          totalPendentes === 0
            ? "Todos os códigos usados nas notas importadas têm regra. As regras valem para todas as empresas."
            : `${totalPendentes} ${totalPendentes === 1 ? "código usado nas notas ainda não tem regra" : "códigos usados nas notas ainda não têm regra"}. Sem ela, a simulação fica preliminar.`
        }
        acoes={
          contador && (
            <>
              <Botao variante="secundario" onClick={() => { setNcm(null); setCfop({ cfop: 0, natureza: "", gera_receita: true }); }}>
                Novo CFOP
              </Botao>
              <Botao onClick={() => { setCfop(null); setNcm(NOVO_NCM); }}>Novo NCM</Botao>
            </>
          )
        }
      />
      {!contador && <p className="text-sm text-text-muted">Só o contador classifica NCM e CFOP. Se algum código estiver pendente, avise o contador.</p>}

      {ncm && <FormNcm inicial={ncm} novo={!regras.some((r) => r.ncm === ncm.ncm)} fechar={() => setNcm(null)} />}
      {cfop && <FormCfop inicial={cfop} fechar={() => setCfop(null)} />}

      {totalPendentes > 0 && (
        <Card titulo="Sem regra" semPadding>
          <Tabela cabecalho={["Código", "Produto de exemplo", "Valor nas notas", "Planejamentos", ""]} numericas={[2, 3]}>
            {ncmPendentes.map((p) => (
              <tr key={`n${p.codigo}`} className="bg-alert-soft">
                <td className="whitespace-nowrap px-4 py-2 font-medium">NCM {ncmFmt(String(p.codigo))}</td>
                <td className="px-2 py-2">{p.produto_exemplo ?? "–"}</td>
                <td className="num px-2 py-2">{brl(p.valor)}</td>
                <td className="num px-2 py-2">{p.planejamentos}</td>
                <td className="px-4 py-2 text-right">
                  {contador && (
                    <button className="text-brand underline underline-offset-2" onClick={() => { setCfop(null); setNcm({ ...NOVO_NCM, ncm: String(p.codigo), produto_exemplo: p.produto_exemplo ?? "" }); }}>
                      Classificar
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {cfopPendentes.map((p) => (
              <tr key={`c${p.codigo}`} className="bg-alert-soft">
                <td className="whitespace-nowrap px-4 py-2 font-medium">CFOP {p.codigo}</td>
                <td className="px-2 py-2">{p.produto_exemplo ?? "–"}</td>
                <td className="num px-2 py-2">{brl(p.valor)}</td>
                <td className="num px-2 py-2">{p.planejamentos}</td>
                <td className="px-4 py-2 text-right">
                  {contador && (
                    <button className="text-brand underline underline-offset-2" onClick={() => { setNcm(null); setCfop({ cfop: Number(p.codigo), natureza: "", gera_receita: true }); }}>
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
        titulo={`${regras.length} regras de NCM`}
        semPadding
        acoes={<input aria-label="Buscar NCM ou produto" placeholder="NCM ou produto" className="rounded border border-border px-2 py-1 text-sm" value={busca} onChange={(e) => setBusca(e.target.value)} />}
      >
        <Tabela cabecalho={["NCM", "Produto de exemplo", "PIS/COFINS", "ST", "Confiança", "Situação", ""]}>
          {visiveis.map((r) => (
            <tr key={r.ncm}>
              <td className="whitespace-nowrap px-4 py-2 font-medium">{ncmFmt(r.ncm)}</td>
              <td className="px-2 py-2">{r.produto_exemplo ?? "–"}</td>
              <td className="px-2 py-2">{r.monofasico ? "Monofásico" : "Tributado"}</td>
              <td className="px-2 py-2">{r.sujeito_st ? "Sim" : "Não"}</td>
              <td className="px-2 py-2">{r.confianca === "MEDIA" ? "Média" : "Alta"}</td>
              <td className="px-2 py-2">{r.requer_revisao ? "! Revisar" : "Correta"}</td>
              <td className="px-4 py-2 text-right">
                {contador && (
                  <button className="text-brand underline underline-offset-2" onClick={() => { setCfop(null); setNcm(r); window.scrollTo({ top: 0 }); }}>
                    Editar
                  </button>
                )}
              </td>
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
                  <button className="text-brand underline underline-offset-2" onClick={() => { setNcm(null); setCfop(c); window.scrollTo({ top: 0 }); }}>
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

function FormNcm({ inicial, novo, fechar }: { inicial: RegraNcm; novo: boolean; fechar: () => void }) {
  const [f, setF] = useState(inicial);
  const [erro, setErro] = useState<string | null>(null);
  const concluir = useConcluir(fechar);
  useEffect(() => setF(inicial), [inicial]);
  const salvar = useMutation({
    mutationFn: () => api.put("/tabelas/ncm", { ...f, cst_ibs_cbs: f.cst_ibs_cbs || null, cclass_trib: f.cclass_trib || null }),
    onSuccess: concluir,
    onError: (e) => setErro(mensagemErro(e)),
  });
  const marca = (k: "monofasico" | "sujeito_st" | "indicio_ncm_incorreto" | "requer_revisao", rotulo: string) => (
    <label className="flex items-center gap-2">
      <input type="checkbox" checked={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.checked })} />
      {rotulo}
    </label>
  );

  function enviar(e: FormEvent) {
    e.preventDefault();
    if (!/^\d{8}$/.test(f.ncm)) return setErro("O NCM tem 8 dígitos, sem pontos");
    if (f.requer_revisao && !f.acao_recomendada?.trim()) return setErro("Diga o que deve ser revisado no campo ação recomendada");
    salvar.mutate();
  }

  return (
    <Card titulo={novo ? "Classificar NCM" : `Editar NCM ${ncmFmt(f.ncm)}`}>
      <form onSubmit={enviar} className="grid gap-3 text-sm md:grid-cols-4">
        <label>
          NCM
          <input className={campo} inputMode="numeric" maxLength={8} disabled={!novo} value={f.ncm} onChange={(e) => setF({ ...f, ncm: e.target.value.replace(/\D/g, "") })} />
        </label>
        <label className="md:col-span-2">
          Produto de exemplo
          <input className={campo} maxLength={200} value={f.produto_exemplo ?? ""} onChange={(e) => setF({ ...f, produto_exemplo: e.target.value })} />
        </label>
        <label>
          Confiança na classificação
          <select className={campo} value={f.confianca} onChange={(e) => setF({ ...f, confianca: e.target.value as RegraNcm["confianca"] })}>
            <option value="ALTA">Alta</option>
            <option value="MEDIA">Média (aparece como ponto a validar)</option>
          </select>
        </label>
        <fieldset className="grid gap-1 md:col-span-4 md:grid-cols-2">
          {marca("monofasico", "PIS/COFINS monofásico (revenda com alíquota zero)")}
          {marca("sujeito_st", "Sujeito à substituição tributária (ICMS-ST)")}
          {marca("requer_revisao", "Precisa de revisão no cadastro do produto")}
          {marca("indicio_ncm_incorreto", "Indício de NCM incorreto (reclassificado, passa a monofásico)")}
        </fieldset>
        <label className="md:col-span-4">
          Ação recomendada
          <input className={campo} value={f.acao_recomendada ?? ""} placeholder="Classificação correta." onChange={(e) => setF({ ...f, acao_recomendada: e.target.value })} />
        </label>
        <label>
          CST IBS/CBS
          <input className={campo} inputMode="numeric" maxLength={3} value={f.cst_ibs_cbs ?? ""} onChange={(e) => setF({ ...f, cst_ibs_cbs: e.target.value.replace(/\D/g, "") })} />
        </label>
        <label>
          cClassTrib
          <input className={campo} inputMode="numeric" maxLength={6} value={f.cclass_trib ?? ""} onChange={(e) => setF({ ...f, cclass_trib: e.target.value.replace(/\D/g, "") })} />
        </label>
        <label className="md:col-span-2">
          Benefício na Reforma
          <input className={campo} maxLength={120} value={f.beneficio_reforma ?? ""} onChange={(e) => setF({ ...f, beneficio_reforma: e.target.value })} />
        </label>
        <label className="md:col-span-2">
          Fundamento
          <input className={campo} maxLength={200} placeholder="Lei 10.485/2002, Anexos I e II" value={f.fundamento ?? ""} onChange={(e) => setF({ ...f, fundamento: e.target.value })} />
        </label>
        <label className="md:col-span-2">
          Observação
          <input className={campo} value={f.observacao ?? ""} onChange={(e) => setF({ ...f, observacao: e.target.value })} />
        </label>
        <div className="space-y-2 md:col-span-4">
          <Erro mensagem={erro} />
          <p className="text-text-muted">Vale para todas as empresas. As simulações que usam este NCM ficam desatualizadas.</p>
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
