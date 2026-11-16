import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";

import { api, mensagemErro } from "../api/cliente";
import type { Empresa } from "../api/tipos";
import { PainelDas } from "../components/PainelDas";
import { Botao, Cabecalho, Card, CampoMoeda, EnvioArquivo, Erro, Ficha, Paginacao, Tabela } from "../components/ui";
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
  xml?: boolean; // veio dos XML enviados: é refeita quando o lote muda
};

type Leitura = { linhas: Linha[]; avisos: string[]; info: string[]; erros: string[]; vendas: number; compras: number };
type Parcela = { anexo: string; monofasico: boolean; st: boolean; iss_fora_do_das: string | null; receita: number };

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
  parcelas: Parcela[];
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
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [leitura, setLeitura] = useState<Omit<Leitura, "linhas"> | null>(null);
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
    // o RBT12 do PGDAS é o ponto de partida (o usuário corrige se estiver desatualizado); sem PGDAS, fica o que foi digitado
    if (dadosEmpresa.rbt12 != null) setRbt12(dadosEmpresa.rbt12);
    setNova((n) => ({ ...n, anexo: dadosEmpresa.anexo }));
    setResultado(null);
  }, [dadosEmpresa]);

  function mudarLinhas(l: Linha[]) {
    setLinhas(l);
    setResultado(null); // resultado antigo não pode ficar na tela com notas diferentes
  }

  // o lote inteiro vai de uma vez: as compras (opcionais) conferem o ST e o monofásico de todas as vendas
  const lerNfe = useMutation({
    mutationFn: async (lote: File[]) => {
      if (!lote.length) return null;
      const corpo = new FormData();
      lote.forEach((f) => corpo.append("arquivos", f));
      corpo.append("empresa_id", empresaId);
      return (await api.post<Leitura>("/calculadora-simples/nfe", corpo)).data;
    },
    onSuccess: (d) => {
      const digitadas = linhas.filter((l) => !l.xml);
      mudarLinhas([...(d?.linhas ?? []).map((l) => ({ ...l, xml: true })), ...digitadas]);
      setLeitura(d && { avisos: d.avisos, info: d.info, erros: d.erros, vendas: d.vendas, compras: d.compras });
      setErro(null);
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  /** O componente de envio manda só os novos ao escolher e a lista restante ao retirar um arquivo: a retirada devolve os
   * mesmos objetos que já estavam no lote; um arquivo escolhido de novo chega como objeto novo e não é retirada. */
  function mudarArquivos(fs: File[]) {
    const mesmo = (a: File, b: File) => a.name === b.name && a.size === b.size;
    const retirada = fs.every((f) => arquivos.includes(f));
    const lote = retirada ? fs : [...arquivos, ...fs.filter((f) => !arquivos.some((a) => mesmo(a, f)))];
    setArquivos(lote);
    lerNfe.mutate(lote);
  }

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

      <Card titulo="Notas" adendo="Envie os XML de venda do mês (avulsos ou .zip) e, se tiver, os de compra. Ou digite o valor.">
        <div className="space-y-4">
          {empresaId ? (
            <div>
              <EnvioArquivo formatos={[".xml", ".zip"]} multiplo arquivos={arquivos.length <= 20 ? arquivos : []} aoEscolher={mudarArquivos} />
              {arquivos.length > 20 && (
                <p className="mt-2 flex items-center justify-between text-sm text-text-muted">
                  {arquivos.length} arquivos enviados
                  <Botao variante="linha-perigo" onClick={() => mudarArquivos([])}>
                    Retirar todos
                  </Botao>
                </p>
              )}
              {lerNfe.isPending && <p role="status" className="mt-2 text-sm text-text-muted">Lendo os arquivos…</p>}
            </div>
          ) : (
            <p className="text-sm text-text-muted">Escolha a empresa para enviar XML de NF-e.</p>
          )}
          {leitura && !lerNfe.isPending && (
            <p className="text-sm">
              {leitura.vendas} {leitura.vendas === 1 ? "nota de venda" : "notas de venda"} e {leitura.compras}{" "}
              {leitura.compras === 1 ? "nota de compra" : "notas de compra"} lidas.
            </p>
          )}
          {leitura?.info.map((t) => (
            <p key={t} className="rounded border border-brand/30 bg-highlight px-3 py-2 text-sm text-text">
              {t}
            </p>
          ))}
          {leitura && leitura.avisos.length + leitura.erros.length > 0 && (
            <ul className="max-h-56 space-y-1 overflow-auto rounded border border-warning bg-warning-soft px-3 py-2 text-sm text-warning-ink">
              {[...leitura.avisos, ...leitura.erros].map((a) => (
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
            <ListaNotas
              linhas={linhas}
              alternar={alternar}
              issFora={issFora}
              retirar={(i) => mudarLinhas(linhas.filter((_, j) => j !== i))}
              servico={servico}
            />
          )}
          <div className="flex justify-end gap-2">
            {linhas.length > 0 && (
              <Botao variante="secundario" onClick={() => { mudarLinhas([]); setArquivos([]); setLeitura(null); }}>
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

/** O nome da parcela segue o PGDAS-D: o que sai do DAS em cada receita. */
function rotuloParcela(p: Parcela) {
  const fora = [
    ...(p.monofasico ? ["tributação monofásica de PIS e COFINS"] : []),
    ...(p.st ? ["substituição tributária de ICMS"] : []),
    ...(p.iss_fora_do_das ? [`ISS ${ISS_FORA[p.iss_fora_do_das].toLowerCase()}`] : []),
  ];
  return fora.length ? `Com ${fora.join(" e ")}` : "Sem substituição tributária nem tributação monofásica";
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
      <Card titulo="Receita para o PGDAS-D" adendo="Segregada como se lança na declaração: por anexo, com e sem ST e monofásico.">
        <Tabela cabecalho={["Anexo", "Parcela", "Receita"]} numericas={[2]}>
          {r.parcelas.map((p) => (
            <tr key={`${p.anexo}-${p.monofasico}-${p.st}-${p.iss_fora_do_das}`}>
              <td className="px-2 py-1">{p.anexo}</td>
              <td className="px-2 py-1">{rotuloParcela(p)}</td>
              <td className="num px-2 py-1 text-right">{brl(p.receita)}</td>
            </tr>
          ))}
          <tr className="font-medium">
            <td className="px-2 py-1" colSpan={2}>
              Total
            </td>
            <td className="num px-2 py-1 text-right">{brl(r.receita)}</td>
          </tr>
        </Tabela>
      </Card>
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

const LIMITE_SEM_ABAS = 20;
const POR_PAGINA = 20; // cabe numa tela
type Filtro = "todas" | "st" | "monofasico" | "nenhum";
const FILTROS: Record<Filtro, string> = { todas: "Todas", st: "Com ICMS-ST", monofasico: "Monofásicas", nenhum: "Sem ST nem monofásico" };

/** Poucas notas: a lista direto. Muitas: um resumo por parcela e a lista em outra aba, paginada e com busca. */
function ListaNotas({
  linhas,
  alternar,
  issFora,
  retirar,
  servico,
}: {
  linhas: Linha[];
  alternar: (i: number, chave: "st" | "monofasico") => void;
  issFora: (i: number, v: string) => void;
  retirar: (i: number) => void;
  servico: (anexo: string) => boolean;
}) {
  const [aba, setAba] = useState<"resumo" | "notas">("resumo");
  const [busca, setBusca] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [pagina, setPagina] = useState(0);
  const muitas = linhas.length > LIMITE_SEM_ABAS;

  // o índice original acompanha cada linha: marcar ou retirar numa página filtrada mexe na nota certa
  const termo = busca.trim().toLowerCase();
  const visiveis = linhas
    .map((l, i) => ({ l, i }))
    .filter(({ l }) => !termo || l.descricao.toLowerCase().includes(termo))
    .filter(({ l }) =>
      filtro === "todas" ? true : filtro === "st" ? l.st : filtro === "monofasico" ? l.monofasico : !l.st && !l.monofasico && !l.iss_fora_do_das,
    );
  const paginas = Math.max(1, Math.ceil(visiveis.length / POR_PAGINA));
  const atual = Math.min(pagina, paginas - 1);
  const daPagina = muitas ? visiveis.slice(atual * POR_PAGINA, (atual + 1) * POR_PAGINA) : visiveis;

  const resumo = new Map<string, Parcela & { itens: number }>();
  for (const l of linhas) {
    const anexo = l.fator_r ? "III ou V" : l.anexo;
    const chave = `${anexo}|${l.monofasico}|${l.st}|${l.iss_fora_do_das ?? ""}`;
    const p = resumo.get(chave) ?? { anexo, monofasico: l.monofasico, st: l.st, iss_fora_do_das: l.iss_fora_do_das, receita: 0, itens: 0 };
    p.receita += l.valor;
    p.itens += 1;
    resumo.set(chave, p);
  }
  const total = linhas.reduce((s, l) => s + l.valor, 0);
  const n = (v: number) => v.toLocaleString("pt-BR");

  const tabela = (
    <Tabela cabecalho={["Nota", "Anexo", "Mês", "Valor", "Fora do DAS", ""]} numericas={[3]}>
      {daPagina.map(({ l, i }) => (
        <tr key={i}>
          <td className="max-w-[28rem] truncate px-2 py-1" title={l.descricao}>
            {l.descricao}
          </td>
          <td className="px-2 py-1">{l.fator_r ? "Fator R" : l.anexo}</td>
          <td className="whitespace-nowrap px-2 py-1">{l.competencia ? competenciaExtenso(l.competencia) : "—"}</td>
          <td className="num px-2 py-1 text-right">{brl(l.valor)}</td>
          <td className="px-2 py-1">
            <div className="flex flex-nowrap gap-3 whitespace-nowrap text-xs">
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
            <Botao variante="linha-perigo" onClick={() => retirar(i)}>
              Retirar
            </Botao>
          </td>
        </tr>
      ))}
    </Tabela>
  );
  if (!muitas) return tabela;

  const botaoAba = (valor: "resumo" | "notas", rotulo: string) => (
    <button
      type="button"
      role="tab"
      aria-selected={aba === valor}
      onClick={() => setAba(valor)}
      className={`-mb-px border-b-2 px-3 py-1.5 text-sm ${aba === valor ? "border-brand font-medium text-brand" : "border-transparent text-text-muted hover:text-brand"}`}
    >
      {rotulo}
    </button>
  );
  return (
    <div className="space-y-3">
      <div role="tablist" aria-label="Notas incluídas" className="flex gap-1 border-b border-surface">
        {botaoAba("resumo", "Resumo")}
        {botaoAba("notas", `Notas (${n(linhas.length)})`)}
      </div>
      {aba === "resumo" ? (
        <Tabela cabecalho={["Anexo", "Parcela", "Itens", "Receita"]} numericas={[2, 3]}>
          {[...resumo.values()]
            .sort((a, b) => b.receita - a.receita)
            .map((p) => (
              <tr key={`${p.anexo}-${p.monofasico}-${p.st}-${p.iss_fora_do_das}`}>
                <td className="px-2 py-1">{p.anexo}</td>
                <td className="px-2 py-1">{rotuloParcela(p)}</td>
                <td className="num px-2 py-1 text-right">{n(p.itens)}</td>
                <td className="num px-2 py-1 text-right">{brl(p.receita)}</td>
              </tr>
            ))}
          <tr className="font-medium">
            <td className="px-2 py-1" colSpan={2}>
              Total
            </td>
            <td className="num px-2 py-1 text-right">{n(linhas.length)}</td>
            <td className="num px-2 py-1 text-right">{brl(total)}</td>
          </tr>
        </Tabela>
      ) : (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <input
              aria-label="Buscar nota ou produto"
              placeholder="Buscar por produto ou número da nota"
              className="w-72 rounded border border-border bg-white px-2 py-1"
              value={busca}
              onChange={(e) => {
                setBusca(e.target.value);
                setPagina(0);
              }}
            />
            <select
              aria-label="Filtrar notas"
              className="rounded border border-border bg-white px-2 py-1"
              value={filtro}
              onChange={(e) => {
                setFiltro(e.target.value as Filtro);
                setPagina(0);
              }}
            >
              {Object.entries(FILTROS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
            <span className="text-text-muted">
              {n(visiveis.length)} {visiveis.length === 1 ? "item" : "itens"}
            </span>
          </div>
          {tabela}
          <Paginacao pagina={atual} total={visiveis.length} porPagina={POR_PAGINA} mudar={setPagina} />
        </div>
      )}
    </div>
  );
}
