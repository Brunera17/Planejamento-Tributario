import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";

import { api, mensagemErro } from "../api/cliente";
import type { Empresa } from "../api/tipos";
import { Botao, Cabecalho, Card, CampoMoeda, EnvioArquivo, Erro, Ficha, Tabela } from "../components/ui";
import { brl, competenciaExtenso, lerMoeda, percentual } from "../lib/formato";

type Linha = {
  descricao: string;
  valor: number;
  anexo: string;
  competencia: string | null;
  st: boolean;
  monofasico: boolean;
  iss_retido: boolean;
  fator_r: boolean;
};

type Resultado = {
  rbt12: number;
  das: number;
  receita: number;
  aliquota_media: number;
  tributos: Record<string, number>;
  por_competencia: Record<string, number>;
  faixas: Record<string, { faixa: number; aliquota_nominal: number; aliquota_efetiva: number; falta_proxima_faixa: number }>;
  fator_r: number | null;
  avisos: string[];
  linhas: { linha: Linha; anexo: string; aliquota: number; das: number }[];
};

type DadosEmpresa = { anexo: string; rbt12: number | null; rbt12_competencia: string | null };

const ANEXOS: Record<string, string> = {
  I: "Anexo I (comércio)",
  II: "Anexo II (indústria)",
  III: "Anexo III (serviços)",
  IV: "Anexo IV (serviços)",
  V: "Anexo V (serviços)",
  R: "Anexo III ou V, pelo Fator R",
};
const ORDEM_TRIBUTOS = ["ICMS", "ISS", "IPI", "PIS", "COFINS", "IRPJ", "CSLL", "CPP"];
const mesAtual = () => new Date().toISOString().slice(0, 7);
const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";

export function CalculadoraSimples() {
  const [busca, setBusca] = useState("");
  const [empresaId, setEmpresaId] = useState("");
  const [rbt12, setRbt12] = useState<number | null>(null);
  const [folha, setFolha] = useState<number | null>(null);
  const [linhas, setLinhas] = useState<Linha[]>([]);
  const [avisosLeitura, setAvisosLeitura] = useState<string[]>([]);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [nova, setNova] = useState({ descricao: "", valor: "", anexo: "I", competencia: mesAtual(), st: false, monofasico: false, iss_retido: false });

  const { data: empresas = [] } = useQuery({
    queryKey: ["empresas", "escolha", busca],
    queryFn: async () => (await api.get<Empresa[]>("/empresas", { params: { busca: busca || undefined } })).data,
  });
  const { data: dadosEmpresa } = useQuery({
    queryKey: ["calculadora", "empresa", empresaId],
    enabled: !!empresaId,
    queryFn: async () => (await api.get<DadosEmpresa>(`/calculadora-simples/empresas/${empresaId}`)).data,
  });
  useEffect(() => {
    if (!dadosEmpresa) return;
    setRbt12(dadosEmpresa.rbt12); // o RBT12 do PGDAS é o ponto de partida; o usuário corrige se estiver desatualizado
    setNova((n) => ({ ...n, anexo: dadosEmpresa.anexo }));
    setResultado(null);
  }, [dadosEmpresa]);

  function mudarLinhas(l: Linha[]) {
    setLinhas(l);
    setResultado(null); // resultado antigo não pode ficar na tela com notas diferentes
  }

  const lerNfe = useMutation({
    mutationFn: async (arquivos: File[]) => {
      const lidas: Linha[] = [];
      const avisos: string[] = [];
      for (const f of arquivos) {
        const corpo = new FormData();
        corpo.append("arquivo", f);
        corpo.append("empresa_id", empresaId);
        const d = (await api.post<{ linhas: Linha[]; avisos: string[]; erros: string[] }>("/calculadora-simples/nfe", corpo)).data;
        lidas.push(...d.linhas);
        avisos.push(...d.avisos, ...d.erros);
      }
      return { lidas, avisos };
    },
    onSuccess: ({ lidas, avisos }) => {
      mudarLinhas([...linhas, ...lidas]);
      setAvisosLeitura(avisos);
      setErro(null);
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  const calcular = useMutation({
    mutationFn: async () =>
      (await api.post<Resultado>("/calculadora-simples", { rbt12, folha_12m: folha, linhas })).data,
    onSuccess: (r) => {
      setResultado(r);
      setErro(null);
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  function adicionar(e: FormEvent) {
    e.preventDefault();
    const valor = lerMoeda(nova.valor);
    if (valor == null || valor <= 0) return setErro("Informe o valor da nota");
    const fatorR = nova.anexo === "R";
    mudarLinhas([
      ...linhas,
      {
        descricao: nova.descricao.trim() || "Valor digitado",
        valor,
        anexo: fatorR ? "III" : nova.anexo,
        competencia: nova.competencia || null,
        st: nova.st,
        monofasico: nova.monofasico,
        iss_retido: nova.iss_retido,
        fator_r: fatorR,
      },
    ]);
    setNova({ ...nova, descricao: "", valor: "" });
    setErro(null);
  }

  function enviarCalculo() {
    if (rbt12 == null) return setErro("Informe o RBT12: a receita bruta dos 12 meses anteriores");
    if (!linhas.length) return setErro("Inclua ao menos uma nota ou valor");
    if (linhas.some((l) => l.fator_r) && folha == null) return setErro("Informe a folha dos 12 meses para calcular o Fator R");
    calcular.mutate();
  }

  const alternar = (i: number, chave: "st" | "monofasico" | "iss_retido") =>
    mudarLinhas(linhas.map((l, j) => (j === i ? { ...l, [chave]: !l[chave] } : l)));
  const servico = (a: string) => ["III", "IV", "V"].includes(a);
  const usaFatorR = linhas.some((l) => l.fator_r) || nova.anexo === "R";

  return (
    <>
      <Cabecalho
        titulo="Calculadora do Simples"
        descricao="DAS aproximado de notas avulsas ou do mês, sem abrir um planejamento. Nada fica gravado."
        acoes={resultado && <Botao variante="secundario" onClick={() => window.print()}>Imprimir ou salvar em PDF</Botao>}
      />
      <Erro mensagem={erro} />

      <Card titulo="Empresa e receita" adendo="A empresa é necessária só para ler XML; o RBT12 vem do último PGDAS-D enviado.">
        <div className="grid gap-3 text-sm md:grid-cols-[minmax(0,1fr)_11rem_11rem]">
          <label>
            Empresa
            <input aria-label="Buscar empresa por razão social ou CNPJ" placeholder="Buscar por razão social ou CNPJ" className={campo} value={busca} onChange={(e) => setBusca(e.target.value)} />
            <select aria-label="Empresa" className={campo} value={empresaId} onChange={(e) => setEmpresaId(e.target.value)}>
              <option value="">Nenhuma (só valores digitados)</option>
              {empresas
                .filter((e) => e.regime_tributario === "SIMPLES_NACIONAL")
                .map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.razao_social}
                  </option>
                ))}
            </select>
          </label>
          <div>
            <span>RBT12 (R$)</span>
            <div className="mt-1">
              <CampoMoeda rotulo="RBT12" valor={rbt12} onChange={(v) => { setRbt12(v); setResultado(null); }} />
            </div>
            <p className="mt-1 text-xs text-text-muted">
              {dadosEmpresa?.rbt12_competencia
                ? `Do PGDAS-D de ${competenciaExtenso(dadosEmpresa.rbt12_competencia)}; confira se é o do mês`
                : "Receita bruta dos 12 meses anteriores"}
            </p>
          </div>
          {usaFatorR && (
            <div>
              <span>Folha dos 12 meses (R$)</span>
              <div className="mt-1">
                <CampoMoeda rotulo="Folha dos 12 meses" valor={folha} onChange={(v) => { setFolha(v); setResultado(null); }} />
              </div>
              <p className="mt-1 text-xs text-text-muted">Salários, pró-labore, FGTS e CPP</p>
            </div>
          )}
        </div>
      </Card>

      <Card titulo="Notas" adendo="Envie XML de NF-e (avulso ou .zip) ou digite o valor. Confira as marcações antes de calcular.">
        <div className="space-y-4">
          {empresaId ? (
            <div>
              <EnvioArquivo formatos={[".xml", ".zip"]} multiplo arquivos={[]} aoEscolher={(fs) => fs.length && lerNfe.mutate(fs)} />
              {lerNfe.isPending && <p role="status" className="mt-2 text-sm text-text-muted">Lendo os arquivos…</p>}
            </div>
          ) : (
            <p className="text-sm text-text-muted">Escolha a empresa para enviar XML de NF-e.</p>
          )}
          {avisosLeitura.length > 0 && (
            <ul className="space-y-1 rounded border border-warning bg-warning-soft px-3 py-2 text-sm text-warning-ink">
              {avisosLeitura.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}

          <form onSubmit={adicionar} className="grid gap-3 border-t border-surface pt-4 text-sm md:grid-cols-[minmax(0,1fr)_9rem_14rem_9rem]">
            <label>
              Descrição
              <input className={campo} maxLength={150} placeholder="NFS-e 123, consultoria" value={nova.descricao} onChange={(e) => setNova({ ...nova, descricao: e.target.value })} />
            </label>
            <label>
              Valor (R$)
              <input inputMode="decimal" className={`${campo} num`} placeholder="0,00" value={nova.valor} onChange={(e) => setNova({ ...nova, valor: e.target.value.replace(/[^\d.,]/g, "") })} />
            </label>
            <label>
              Anexo
              <select className={campo} value={nova.anexo} onChange={(e) => setNova({ ...nova, anexo: e.target.value })}>
                {Object.entries(ANEXOS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Mês
              <input type="month" className={campo} value={nova.competencia} onChange={(e) => setNova({ ...nova, competencia: e.target.value })} />
            </label>
            <div className="flex flex-wrap items-center justify-between gap-3 md:col-span-4">
              <div className="flex flex-wrap gap-4">
                {nova.anexo === "I" || nova.anexo === "II" ? (
                  <>
                    <label className="flex items-center gap-1.5">
                      <input type="checkbox" checked={nova.st} onChange={(e) => setNova({ ...nova, st: e.target.checked })} /> Com ICMS-ST
                    </label>
                    <label className="flex items-center gap-1.5">
                      <input type="checkbox" checked={nova.monofasico} onChange={(e) => setNova({ ...nova, monofasico: e.target.checked })} /> PIS e COFINS monofásicos
                    </label>
                  </>
                ) : (
                  <label className="flex items-center gap-1.5">
                    <input type="checkbox" checked={nova.iss_retido} onChange={(e) => setNova({ ...nova, iss_retido: e.target.checked })} /> ISS retido pelo tomador
                  </label>
                )}
              </div>
              <Botao type="submit" variante="secundario">
                Incluir valor
              </Botao>
            </div>
          </form>

          {linhas.length > 0 && (
            <Tabela cabecalho={["Nota", "Anexo", "Mês", "Valor", "Sai do DAS", ""]} numericas={[3]}>
              {linhas.map((l, i) => (
                <tr key={i}>
                  <td className="px-2 py-1">{l.descricao}</td>
                  <td className="px-2 py-1">{l.fator_r ? "Fator R" : l.anexo}</td>
                  <td className="px-2 py-1">{l.competencia ? competenciaExtenso(l.competencia) : "—"}</td>
                  <td className="num px-2 py-1 text-right">{brl(l.valor)}</td>
                  <td className="px-2 py-1">
                    <div className="flex flex-wrap gap-3 text-xs">
                      {servico(l.anexo) || l.fator_r ? (
                        <label className="flex items-center gap-1">
                          <input type="checkbox" checked={l.iss_retido} onChange={() => alternar(i, "iss_retido")} /> ISS retido
                        </label>
                      ) : (
                        <>
                          <label className="flex items-center gap-1">
                            <input type="checkbox" checked={l.st} onChange={() => alternar(i, "st")} /> ICMS-ST
                          </label>
                          <label className="flex items-center gap-1">
                            <input type="checkbox" checked={l.monofasico} onChange={() => alternar(i, "monofasico")} /> Monofásico
                          </label>
                        </>
                      )}
                    </div>
                  </td>
                  <td className="px-2 py-1 text-right">
                    <Botao variante="linha-perigo" onClick={() => mudarLinhas(linhas.filter((_, j) => j !== i))}>
                      Retirar
                    </Botao>
                  </td>
                </tr>
              ))}
            </Tabela>
          )}
          <div className="flex justify-end gap-2">
            {linhas.length > 0 && (
              <Botao variante="secundario" onClick={() => { mudarLinhas([]); setAvisosLeitura([]); }}>
                Limpar notas
              </Botao>
            )}
            <Botao onClick={enviarCalculo} disabled={calcular.isPending}>
              {calcular.isPending ? "Calculando…" : "Calcular DAS"}
            </Botao>
          </div>
        </div>
      </Card>

      {resultado && <ResultadoCalculo r={resultado} />}
    </>
  );
}

function ResultadoCalculo({ r }: { r: Resultado }) {
  const faixas = Object.entries(r.faixas);
  const meses = Object.entries(r.por_competencia).sort();
  const tributos = ORDEM_TRIBUTOS.filter((t) => r.tributos[t]);
  return (
    <>
      <Ficha
        campos={[
          { rotulo: "RBT12", valor: brl(r.rbt12) },
          { rotulo: "Receita das notas", valor: brl(r.receita) },
          { rotulo: "DAS estimado", valor: brl(r.das) },
          { rotulo: "Alíquota média", valor: percentual(r.aliquota_media) },
          ...(r.fator_r != null ? [{ rotulo: "Fator R", valor: percentual(r.fator_r) }] : []),
        ]}
      />
      {r.avisos.length > 0 && (
        <ul className="space-y-1 rounded border border-warning bg-warning-soft px-3 py-2 text-sm text-warning-ink">
          {r.avisos.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card titulo="Faixa e alíquota efetiva">
          <Tabela cabecalho={["Anexo", "Faixa", "Nominal", "Efetiva", "Falta para a próxima"]} numericas={[2, 3, 4]}>
            {faixas.map(([anexo, f]) => (
              <tr key={anexo}>
                <td className="px-2 py-1">{anexo}</td>
                <td className="px-2 py-1">{f.faixa}ª</td>
                <td className="num px-2 py-1 text-right">{percentual(f.aliquota_nominal)}</td>
                <td className="num px-2 py-1 text-right">{percentual(f.aliquota_efetiva)}</td>
                <td className="num px-2 py-1 text-right">{f.falta_proxima_faixa > 0 ? brl(f.falta_proxima_faixa) : "última faixa"}</td>
              </tr>
            ))}
          </Tabela>
        </Card>
        <Card titulo="DAS por tributo">
          <Tabela cabecalho={["Tributo", "Valor", "Parte do DAS"]} numericas={[1, 2]}>
            {tributos.map((t) => (
              <tr key={t}>
                <td className="px-2 py-1">{t}</td>
                <td className="num px-2 py-1 text-right">{brl(r.tributos[t])}</td>
                <td className="num px-2 py-1 text-right">{percentual(r.das ? r.tributos[t] / r.das : 0)}</td>
              </tr>
            ))}
          </Tabela>
        </Card>
      </div>
      {meses.length > 0 && (
        <Card titulo="Previsão do DAS por mês">
          <Tabela cabecalho={["Mês", "DAS estimado"]} numericas={[1]}>
            {meses.map(([m, v]) => (
              <tr key={m}>
                <td className="px-2 py-1">{competenciaExtenso(m)}</td>
                <td className="num px-2 py-1 text-right">{brl(v)}</td>
              </tr>
            ))}
          </Tabela>
        </Card>
      )}
      <Card titulo="DAS por nota" semPadding>
        <Tabela cabecalho={["Nota", "Anexo", "Valor", "Alíquota", "DAS"]} numericas={[2, 3, 4]}>
          {r.linhas.map((l, i) => (
            <tr key={i}>
              <td className="px-2 py-1">{l.linha.descricao}</td>
              <td className="px-2 py-1">{l.anexo}</td>
              <td className="num px-2 py-1 text-right">{brl(l.linha.valor)}</td>
              <td className="num px-2 py-1 text-right">{percentual(l.aliquota)}</td>
              <td className="num px-2 py-1 text-right">{brl(l.das)}</td>
            </tr>
          ))}
        </Tabela>
      </Card>
    </>
  );
}
