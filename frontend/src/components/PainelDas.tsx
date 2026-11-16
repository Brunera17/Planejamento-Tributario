import { useMemo, useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { brl, competenciaExtenso, percentual } from "../lib/formato";
import { Ficha, Paginacao, Tabela } from "./ui";

export type LinhaPainel = {
  linha: { descricao: string; valor: number; competencia: string | null };
  anexo: string;
  aliquota: number;
  das: number;
  iss_municipio: number;
  tributos: Record<string, number>;
};

type Dimensao = "nota" | "atividade" | "anexo" | "mes";
type Medida = "das" | "receita";

// composição de cada fatia na dica
const GRUPOS = [
  { chave: "consumo", nome: "ICMS e ISS", tributos: ["ICMS", "ISS", "IPI"] },
  { chave: "piscofins", nome: "PIS e COFINS", tributos: ["PIS", "COFINS"] },
  { chave: "renda", nome: "IRPJ e CSLL", tributos: ["IRPJ", "CSLL"] },
  { chave: "cpp", nome: "CPP", tributos: ["CPP"] },
] as const;

const ROTULO_DIMENSAO: Record<Dimensao, string> = { nota: "Nota", atividade: "Atividade", anexo: "Anexo", mes: "Mês" };
const ROTULO_MEDIDA: Record<Medida, string> = { das: "DAS", receita: "Receita" };
// cores validadas como paleta categórica (validate_palette.js, modo claro): petróleo da marca, laranja, violeta, amarelo
const COR_FATIA = ["var(--color-serie-1)", "var(--color-serie-2)", "var(--color-serie-3)", "var(--color-serie-4)"];
const COR_OUTROS = "var(--color-t-cpp)";
const MAX_FATIAS = COR_FATIA.length; // acima disso, as menores viram "Outros"
const POR_PAGINA = 20; // linhas da tabela de notas abaixo da rosca: cabe numa tela

const atividade = (anexo: string) => (anexo === "I" ? "Comércio" : anexo === "II" ? "Indústria" : "Serviço");

function grupoDa(l: LinhaPainel, d: Dimensao): string {
  if (d === "atividade") return atividade(l.anexo);
  if (d === "anexo") return `Anexo ${l.anexo}`;
  if (d === "mes") return l.linha.competencia ? competenciaExtenso(l.linha.competencia) : "Sem mês";
  return l.linha.descricao;
}

type Fatia = { nome: string; receita: number; das: number; notas: number; indices: number[]; outros?: boolean } & Record<string, number | string | number[] | boolean | undefined>;

const vazia = (nome: string): Fatia => ({ nome, receita: 0, das: 0, notas: 0, indices: [], ...Object.fromEntries(GRUPOS.map((g) => [g.chave, 0])) });

function agregar(linhas: LinhaPainel[], d: Dimensao): Fatia[] {
  const mapa = new Map<string, Fatia>();
  linhas.forEach((l, i) => {
    // na visão por nota cada linha é uma fatia, mesmo com descrições repetidas
    const nome = d === "nota" ? `${l.linha.descricao}${linhas.findIndex((x) => x.linha.descricao === l.linha.descricao) !== i ? ` (${i + 1})` : ""}` : grupoDa(l, d);
    const f = mapa.get(nome) ?? vazia(nome);
    f.indices.push(i);
    f.receita += l.linha.valor;
    f.das += l.das;
    f.notas += 1;
    for (const g of GRUPOS) f[g.chave] = (f[g.chave] as number) + g.tributos.reduce((s, t) => s + (l.tributos[t] ?? 0), 0);
    mapa.set(nome, f);
  });
  return [...mapa.values()].sort((a, b) => b.das - a.das);
}

/** As menores entram juntas numa fatia só, para a rosca continuar legível com as cores validadas. */
function limitar(fatias: Fatia[], d: Dimensao): Fatia[] {
  if (fatias.length <= MAX_FATIAS) return fatias;
  const resto = fatias.slice(MAX_FATIAS - 1);
  const outras: Fatia = { ...vazia(d === "nota" ? `Outras ${resto.length} notas` : `Outros ${resto.length}`), outros: true };
  for (const f of resto) {
    outras.indices.push(...f.indices);
    outras.receita += f.receita;
    outras.das += f.das;
    outras.notas += f.notas;
    for (const g of GRUPOS) outras[g.chave] = (outras[g.chave] as number) + (f[g.chave] as number);
  }
  return [...fatias.slice(0, MAX_FATIAS - 1), outras];
}

function Segmentado<T extends string>({ rotulo, valor, opcoes, aoMudar }: { rotulo: string; valor: T; opcoes: [T, string][]; aoMudar: (v: T) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-text-muted">{rotulo}</span>
      <div role="group" aria-label={rotulo} className="inline-flex overflow-hidden rounded border border-border">
        {opcoes.map(([v, nome]) => (
          <button
            key={v}
            type="button"
            aria-pressed={v === valor}
            onClick={() => aoMudar(v)}
            className={`border-l border-border px-3 py-1 first:border-l-0 ${v === valor ? "bg-brand font-medium text-white" : "bg-white text-brand hover:bg-highlight"}`}
          >
            {nome}
          </button>
        ))}
      </div>
    </div>
  );
}

export function PainelDas({ linhas }: { linhas: LinhaPainel[] }) {
  const distintos = (d: Dimensao) => new Set(linhas.map((l) => grupoDa(l, d))).size;
  const dimensoes: Dimensao[] = [
    ...(distintos("atividade") > 1 ? (["atividade"] as const) : []),
    ...(distintos("anexo") > distintos("atividade") ? (["anexo"] as const) : []),
    ...(distintos("mes") > 1 ? (["mes"] as const) : []),
    "nota",
  ];
  const [dimensao, setDimensao] = useState<Dimensao>(dimensoes[0]);
  const [medida, setMedida] = useState<Medida>("das");
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [pagina, setPagina] = useState(0);

  const d =dimensoes.includes(dimensao) ? dimensao : dimensoes[0];
  const fatias = useMemo(() => limitar(agregar(linhas, d), d), [linhas, d]);
  const valor = (f: Fatia) => (medida === "receita" ? f.receita : f.das);
  const total = fatias.reduce((s, f) => s + valor(f), 0);
  const cor = (f: Fatia, i: number) => (f.outros ? COR_OUTROS : COR_FATIA[i]);

  const escolhida = fatias.find((f) => f.nome === selecionado);
  const filtradas = escolhida ? escolhida.indices.map((i) => linhas[i]) : linhas;
  const sel = filtradas.reduce((s, l) => ({ receita: s.receita + l.linha.valor, das: s.das + l.das }), { receita: 0, das: 0 });
  const iss = linhas.some((l) => l.iss_municipio > 0);
  const termo = busca.trim().toLowerCase();
  const naTabela = termo ? filtradas.filter((l) => l.linha.descricao.toLowerCase().includes(termo)) : filtradas;
  const atual = Math.min(pagina, Math.max(0, Math.ceil(naTabela.length / POR_PAGINA) - 1));
  const daPagina = naTabela.slice(atual * POR_PAGINA, (atual + 1) * POR_PAGINA);

  function mudarDimensao(v: Dimensao) {
    setDimensao(v);
    setSelecionado(null); // o filtro de uma visão não vale na outra
    setPagina(0);
  }
  const alternarSelecao = (nome: string) => {
    setSelecionado((s) => (s === nome ? null : nome));
    setPagina(0);
  };

  return (
    <section className="rounded-md border border-surface bg-white" aria-labelledby="titulo-painel-das">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-surface px-4 py-2.5">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h2 id="titulo-painel-das">Painel do DAS</h2>
          <p className="text-sm text-text-muted">Clique numa fatia para filtrar os números e a tabela abaixo.</p>
        </div>
      </header>
      <div className="space-y-4 p-4">
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <Segmentado rotulo="Ver por" valor={d} opcoes={dimensoes.map((x) => [x, ROTULO_DIMENSAO[x]])} aoMudar={mudarDimensao} />
          <Segmentado rotulo="Medida" valor={medida} opcoes={[["das", "DAS"], ["receita", "Receita"]]} aoMudar={setMedida} />
        </div>

        {escolhida && (
          <p className="flex items-center gap-2 text-sm">
            <span className="text-text-muted">Filtro:</span>
            <span className="inline-flex items-center gap-1 rounded-full bg-highlight px-2.5 py-0.5 font-medium text-brand">
              {escolhida.nome}
              <button type="button" aria-label="Tirar o filtro" className="px-0.5 hover:text-alert" onClick={() => setSelecionado(null)}>
                ×
              </button>
            </span>
          </p>
        )}

        <Ficha
          campos={[
            { rotulo: escolhida ? "Receita do filtro" : "Receita", valor: brl(sel.receita) },
            { rotulo: escolhida ? "DAS do filtro" : "DAS", valor: brl(sel.das) },
            { rotulo: "Alíquota média", valor: percentual(sel.receita ? sel.das / sel.receita : 0) },
            { rotulo: "Notas", valor: filtradas.length },
          ]}
        />

        <div className="grid items-center gap-4 md:grid-cols-[18rem_minmax(0,1fr)]">
          <div className="relative h-72" role="img" aria-label={`${ROTULO_MEDIDA[medida]} por ${ROTULO_DIMENSAO[d].toLowerCase()}: ${fatias.map((f) => `${f.nome} ${brl(valor(f))}`).join(", ")}`}>
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={fatias}
                  dataKey={medida}
                  nameKey="nome"
                  innerRadius="62%"
                  outerRadius="95%"
                  stroke="#fff"
                  strokeWidth={2}
                  startAngle={90}
                  endAngle={-270}
                  isAnimationActive={false}
                  onClick={(f: { nome: string }) => alternarSelecao(f.nome)}
                  cursor="pointer"
                >
                  {fatias.map((f, i) => (
                    <Cell key={f.nome} fill={cor(f, i)} fillOpacity={!escolhida || escolhida.nome === f.nome ? 1 : 0.3} />
                  ))}
                </Pie>
                {/* por cima do total escrito no centro da rosca */}
                <Tooltip content={<Dica />} isAnimationActive={false} wrapperStyle={{ zIndex: 10 }} />
              </PieChart>
            </ResponsiveContainer>
            {/* o centro mostra o total, ou a fatia escolhida quando há filtro */}
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
              <span className="text-xs text-text-muted">{escolhida ? escolhida.nome : `${ROTULO_MEDIDA[medida]} total`}</span>
              <span className="num text-lg font-semibold">{brl(escolhida ? valor(escolhida) : total)}</span>
              {escolhida && total > 0 && <span className="num text-xs text-text-muted">{percentual(valor(escolhida) / total)} do total</span>}
            </div>
          </div>
          <ul className="space-y-1 text-sm">
            {fatias.map((f, i) => (
              <li key={f.nome}>
                <button
                  type="button"
                  aria-pressed={escolhida?.nome === f.nome}
                  onClick={() => alternarSelecao(f.nome)}
                  className={`grid w-full grid-cols-[auto_minmax(0,1fr)_auto_4.5rem] items-center gap-2 rounded px-2 py-1 text-left hover:bg-highlight ${escolhida?.nome === f.nome ? "bg-highlight" : ""} ${escolhida && escolhida.nome !== f.nome ? "text-text-muted" : ""}`}
                >
                  <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: cor(f, i) }} />
                  <span className="truncate">{f.nome}</span>
                  <span className="num">{brl(valor(f))}</span>
                  <span className="num text-right text-text-muted">{percentual(total ? valor(f) / total : 0)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <input
              aria-label="Buscar nota ou produto no painel"
              placeholder="Buscar por produto ou número da nota"
              className="w-72 rounded border border-border bg-white px-2 py-1"
              value={busca}
              onChange={(e) => {
                setBusca(e.target.value);
                setPagina(0);
              }}
            />
            <span className="text-text-muted">
              {naTabela.length.toLocaleString("pt-BR")} {naTabela.length === 1 ? "item" : "itens"}
              {escolhida ? ` em ${escolhida.nome}` : ""}
            </span>
          </div>
          <Tabela
            cabecalho={["Nota", "Atividade", "Anexo", "Valor", "Alíquota", "DAS", ...(iss ? ["ISS ao município"] : [])]}
            numericas={[3, 4, 5, 6]}
          >
            {daPagina.map((l, i) => (
              <tr key={atual * POR_PAGINA + i}>
                <td className="max-w-[28rem] truncate px-2 py-1" title={l.linha.descricao}>
                  {l.linha.descricao}
                </td>
                <td className="px-2 py-1">{atividade(l.anexo)}</td>
                <td className="px-2 py-1">{l.anexo}</td>
                <td className="num px-2 py-1 text-right">{brl(l.linha.valor)}</td>
                <td className="num px-2 py-1 text-right">{percentual(l.aliquota)}</td>
                <td className="num px-2 py-1 text-right">{brl(l.das)}</td>
                {iss && <td className="num px-2 py-1 text-right">{brl(l.iss_municipio)}</td>}
              </tr>
            ))}
          </Tabela>
          <Paginacao pagina={atual} total={naTabela.length} porPagina={POR_PAGINA} mudar={setPagina} />
        </div>
      </div>
    </section>
  );
}

// os tributos ficam sem cor: na rosca as cores já identificam as fatias, e a mesma cor não pode ter dois sentidos
function Dica({ active, payload }: { active?: boolean; payload?: { payload: Fatia }[] }) {
  if (!active || !payload?.length) return null;
  const f = payload[0].payload;
  return (
    <div className="min-w-56 rounded border border-border bg-white px-3 py-2 text-sm shadow-sm">
      <p className="mb-1 font-medium">{f.nome}</p>
      <dl className="num grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5">
        {GRUPOS.filter((g) => (f[g.chave] as number) > 0).map((g) => (
          <div key={g.chave} className="contents">
            <dt className="text-text-muted">{g.nome}</dt>
            <dd className="text-right">{brl(f[g.chave] as number)}</dd>
          </div>
        ))}
        <dt className="border-t border-surface pt-0.5 font-medium">DAS</dt>
        <dd className="border-t border-surface pt-0.5 text-right font-medium">{brl(f.das)}</dd>
        <dt className="text-text-muted">Receita</dt>
        <dd className="text-right">{brl(f.receita)}</dd>
        <dt className="text-text-muted">Alíquota</dt>
        <dd className="text-right">{percentual(f.receita ? f.das / f.receita : 0)}</dd>
        <dt className="text-text-muted">Notas</dt>
        <dd className="text-right">{f.notas}</dd>
      </dl>
    </div>
  );
}
