import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";

import { api, mensagemErro } from "../api/cliente";
import type { Empresa } from "../api/tipos";
import { PainelDas } from "../components/PainelDas";
import { Botao, Cabecalho, Card, CampoMoeda, EnvioArquivo, Erro, Ficha, Tabela } from "../components/ui";
import { brl, competenciaExtenso, formatarCnpj, lerMoeda, percentual } from "../lib/formato";

type Linha = {
  descricao: string;
  valor: number;
  anexo: string;
  competencia: string | null;
  st: boolean;
  monofasico: boolean;
  iss_fora_do_das: string | null;
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
  iss_municipio: number;
  avisos: string[];
  linhas: { linha: Linha; anexo: string; aliquota: number; das: number; iss_municipio: number; tributos: Record<string, number> }[];
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
const ISS_FORA: Record<string, string> = {
  "": "ISS no DAS",
  RETIDO: "Retido pelo tomador",
  FIXO: "Valor fixo no município",
  ISENTO: "Isento pelo município",
};
const ORDEM_TRIBUTOS = ["ICMS", "ISS", "IPI", "PIS", "COFINS", "IRPJ", "CSLL", "CPP"];
const mesAtual = () => new Date().toISOString().slice(0, 7);
const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";

export function CalculadoraSimples() {
  const [busca, setBusca] = useState("");
  const [empresaId, setEmpresaId] = useState("");
  const [rbt12, setRbt12] = useState<number | null>(null);
  const [folha, setFolha] = useState<number | null>(null);
  const [aliqIss, setAliqIss] = useState("");
  const [linhas, setLinhas] = useState<Linha[]>([]);
  const [avisosLeitura, setAvisosLeitura] = useState<string[]>([]);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [nova, setNova] = useState({ descricao: "", valor: "", anexo: "I", competencia: mesAtual(), st: false, monofasico: false, iss_fora_do_das: "" });

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
      (await api.post<Resultado>("/calculadora-simples", { rbt12, folha_12m: folha, aliq_iss_municipio: aliquotaIss, linhas })).data,
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
        iss_fora_do_das: nova.iss_fora_do_das || null,
        fator_r: fatorR,
      },
    ]);
    // as marcações voltam ao padrão: a próxima nota não herda ST, monofásico ou ISS da anterior sem ninguém ver
    setNova({ ...nova, descricao: "", valor: "", st: false, monofasico: false, iss_fora_do_das: "" });
    setErro(null);
  }

  const aliquotaIss = aliqIss.trim() ? Number(aliqIss.replace(",", ".")) / 100 : null;

  function enviarCalculo() {
    if (aliquotaIss != null && !(aliquotaIss >= 0 && aliquotaIss <= 0.05)) return setErro("A alíquota de ISS do município vai de 0% a 5%");
    if (rbt12 == null) return setErro("Informe o RBT12: a receita bruta dos 12 meses anteriores");
    if (!linhas.length) return setErro("Inclua ao menos uma nota ou valor");
    if (linhas.some((l) => l.fator_r) && folha == null) return setErro("Informe a folha dos 12 meses para calcular o Fator R");
    calcular.mutate();
  }

  const alternar = (i: number, chave: "st" | "monofasico") =>
    mudarLinhas(linhas.map((l, j) => (j === i ? { ...l, [chave]: !l[chave] } : l)));
  const issFora = (i: number, v: string) => mudarLinhas(linhas.map((l, j) => (j === i ? { ...l, iss_fora_do_das: v || null } : l)));
  const servico = (a: string) => ["III", "IV", "V", "R"].includes(a);
  const usaFatorR = linhas.some((l) => l.fator_r) || nova.anexo === "R";
  const temServico = linhas.some((l) => l.fator_r || servico(l.anexo)) || servico(nova.anexo);

  return (
    <>
      <Cabecalho
        titulo="Calculadora do Simples"
        descricao="DAS aproximado de notas avulsas ou do mês, sem abrir um planejamento. Nada fica gravado."
        acoes={resultado && <Botao variante="secundario" onClick={() => window.print()}>Imprimir ou salvar em PDF</Botao>}
      />
      <Erro mensagem={erro} />

      <Card titulo="Empresa e receita" adendo="A empresa é necessária só para ler XML; o RBT12 vem do último PGDAS-D enviado.">
        <div className="grid gap-3 text-sm md:grid-cols-[minmax(0,1fr)_11rem_11rem_11rem]">
          <EscolhaEmpresa
            busca={busca}
            escolhida={!!empresaId}
            opcoes={empresas.filter((e) => e.regime_tributario === "SIMPLES_NACIONAL")}
            aoDigitar={(t) => {
              setBusca(t);
              setEmpresaId("");
            }}
            aoEscolher={(e) => {
              setBusca(e ? e.razao_social : "");
              setEmpresaId(e ? String(e.id) : "");
            }}
          />
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
          {temServico && (
            <label>
              ISS do município (%)
              <input
                inputMode="decimal"
                className={`${campo} num`}
                placeholder="2 a 5"
                value={aliqIss}
                onChange={(e) => {
                  setAliqIss(e.target.value.replace(/[^\d,]/g, ""));
                  setResultado(null);
                }}
              />
              <span className="mt-1 block text-xs font-normal text-text-muted">Só entra com RBT12 acima de R$ 3,6 milhões, quando o ISS sai do DAS</span>
            </label>
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
                    ISS
                    <select className="rounded border border-border bg-white px-2 py-1" value={nova.iss_fora_do_das} onChange={(e) => setNova({ ...nova, iss_fora_do_das: e.target.value })}>
                      {Object.entries(ISS_FORA).map(([k, v]) => (
                        <option key={k} value={k}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
              <Botao type="submit" variante="secundario">
                Incluir valor
              </Botao>
            </div>
          </form>

          {linhas.length > 0 && (
            <Tabela cabecalho={["Nota", "Anexo", "Mês", "Valor", "Fora do DAS", ""]} numericas={[3]}>
              {linhas.map((l, i) => (
                <tr key={i}>
                  <td className="px-2 py-1">{l.descricao}</td>
                  <td className="px-2 py-1">{l.fator_r ? "Fator R" : l.anexo}</td>
                  <td className="px-2 py-1">{l.competencia ? competenciaExtenso(l.competencia) : "—"}</td>
                  <td className="num px-2 py-1 text-right">{brl(l.valor)}</td>
                  <td className="px-2 py-1">
                    <div className="flex flex-wrap gap-3 text-xs">
                      {servico(l.anexo) || l.fator_r ? (
                        <select
                          aria-label={`ISS de ${l.descricao}`}
                          className="rounded border border-border bg-white px-1 py-0.5"
                          value={l.iss_fora_do_das ?? ""}
                          onChange={(e) => issFora(i, e.target.value)}
                        >
                          {Object.entries(ISS_FORA).map(([k, v]) => (
                            <option key={k} value={k}>
                              {v}
                            </option>
                          ))}
                        </select>
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
          ...(r.iss_municipio > 0 ? [{ rotulo: "ISS ao município, fora do DAS", valor: brl(r.iss_municipio), largo: true }] : []),
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
      <PainelDas linhas={r.linhas} />
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
    </>
  );
}

/** Um campo só: digita para filtrar por razão social ou CNPJ e escolhe na lista que abre logo abaixo. */
function EscolhaEmpresa({
  busca,
  escolhida,
  opcoes,
  aoDigitar,
  aoEscolher,
}: {
  busca: string;
  escolhida: boolean;
  opcoes: Empresa[];
  aoDigitar: (t: string) => void;
  aoEscolher: (e: Empresa | null) => void;
}) {
  const [aberta, setAberta] = useState(false);
  const [ativa, setAtiva] = useState(0);
  const lista = opcoes.slice(0, 8);
  const mostrar = aberta && !escolhida;

  function escolher(e: Empresa) {
    aoEscolher(e);
    setAberta(false);
  }

  return (
    <div className="relative">
      <label htmlFor="empresa-calculadora">Empresa</label>
      <div className="relative">
        <input
          id="empresa-calculadora"
          role="combobox"
          aria-expanded={mostrar}
          aria-controls="empresas-calculadora"
          aria-activedescendant={mostrar && lista[ativa] ? `empresa-opcao-${lista[ativa].id}` : undefined}
          autoComplete="off"
          placeholder="Nenhuma: digite a razão social ou o CNPJ"
          className={`${campo} pr-8`}
          value={busca}
          onFocus={() => setAberta(true)}
          onBlur={() => setAberta(false)}
          onChange={(e) => {
            aoDigitar(e.target.value);
            setAtiva(0);
            setAberta(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setAberta(true);
              setAtiva((i) => Math.min(i + 1, lista.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setAtiva((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter" && mostrar && lista[ativa]) {
              e.preventDefault();
              escolher(lista[ativa]);
            } else if (e.key === "Escape") {
              setAberta(false);
            }
          }}
        />
        {busca && (
          <button
            type="button"
            aria-label="Limpar empresa"
            className="absolute right-2 top-1/2 mt-0.5 -translate-y-1/2 px-1 text-text-muted hover:text-alert"
            onClick={() => aoEscolher(null)}
          >
            ×
          </button>
        )}
      </div>
      {mostrar && (
        <ul id="empresas-calculadora" role="listbox" className="absolute z-10 mt-1 max-h-64 w-full overflow-auto rounded border border-border bg-white text-sm">
          {lista.length === 0 ? (
            <li className="px-3 py-2 text-text-muted">Nenhuma empresa do Simples encontrada</li>
          ) : (
            lista.map((e, i) => (
              <li
                key={e.id}
                id={`empresa-opcao-${e.id}`}
                role="option"
                aria-selected={i === ativa}
                className={`cursor-pointer px-3 py-1.5 ${i === ativa ? "bg-highlight" : ""}`}
                onMouseDown={(ev) => ev.preventDefault()} // escolhe antes do blur fechar a lista
                onMouseEnter={() => setAtiva(i)}
                onClick={() => escolher(e)}
              >
                <span className="block">{e.razao_social}</span>
                <span className="num text-xs text-text-muted">{formatarCnpj(e.cnpj)}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
