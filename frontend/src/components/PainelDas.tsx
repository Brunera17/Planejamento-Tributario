import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { brl, competenciaExtenso, percentual } from "../lib/formato";
import { Ficha, Tabela } from "./ui";

export type LinhaPainel = {
  linha: { descricao: string; valor: number; competencia: string | null };
  anexo: string;
  aliquota: number;
  das: number;
  iss_municipio: number;
  tributos: Record<string, number>;
};

type Dimensao = "nota" | "atividade" | "anexo" | "mes";
type Medida = "das" | "aliquota" | "receita";

// cores validadas como paleta categórica (validate_palette.js, modo claro): petróleo da marca, laranja, violeta, amarelo
const GRUPOS = [
  { chave: "consumo", nome: "ICMS e ISS", tributos: ["ICMS", "ISS", "IPI"], cor: "var(--color-serie-1)" },
  { chave: "piscofins", nome: "PIS e COFINS", tributos: ["PIS", "COFINS"], cor: "var(--color-serie-2)" },
  { chave: "renda", nome: "IRPJ e CSLL", tributos: ["IRPJ", "CSLL"], cor: "var(--color-serie-3)" },
  { chave: "cpp", nome: "CPP", tributos: ["CPP"], cor: "var(--color-serie-4)" },
] as const;

const ROTULO_DIMENSAO: Record<Dimensao, string> = { nota: "Nota", atividade: "Atividade", anexo: "Anexo", mes: "Mês" };
const ROTULO_MEDIDA: Record<Medida, string> = { das: "DAS (R$)", aliquota: "Alíquota", receita: "Receita (R$)" };
const MAX_BARRAS = 12;

const atividade = (anexo: string) => (anexo === "I" ? "Comércio" : anexo === "II" ? "Indústria" : "Serviço");

function grupoDa(l: LinhaPainel, d: Dimensao): string {
  if (d === "atividade") return atividade(l.anexo);
  if (d === "anexo") return `Anexo ${l.anexo}`;
  if (d === "mes") return l.linha.competencia ? competenciaExtenso(l.linha.competencia) : "Sem mês";
  return l.linha.descricao;
}

type Barra = { nome: string; receita: number; das: number; notas: number; indices: number[] } & Record<string, number | string | number[]>;

function agregar(linhas: LinhaPainel[], d: Dimensao): Barra[] {
  const mapa = new Map<string, Barra>();
  linhas.forEach((l, i) => {
    // na visão por nota cada linha é uma barra, mesmo com descrições repetidas
    const nome = d === "nota" ? `${l.linha.descricao}${linhas.findIndex((x) => x.linha.descricao === l.linha.descricao) !== i ? ` (${i + 1})` : ""}` : grupoDa(l, d);
    const b = mapa.get(nome) ?? ({ nome, receita: 0, das: 0, notas: 0, indices: [], ...Object.fromEntries(GRUPOS.map((g) => [g.chave, 0])) } as Barra);
    b.indices.push(i);
    b.receita += l.linha.valor;
    b.das += l.das;
    b.notas += 1;
    for (const g of GRUPOS) b[g.chave] = (b[g.chave] as number) + g.tributos.reduce((s, t) => s + (l.tributos[t] ?? 0), 0);
    mapa.set(nome, b);
  });
  return [...mapa.values()].sort((a, b) => b.das - a.das);
}

/** Na visão por nota, as menores entram juntas numa barra só para o gráfico continuar legível. */
function limitar(barras: Barra[]): Barra[] {
  if (barras.length <= MAX_BARRAS) return barras;
  const resto = barras.slice(MAX_BARRAS - 1);
  const outras = { nome: `Outras ${resto.length} notas`, receita: 0, das: 0, notas: 0, indices: [], ...Object.fromEntries(GRUPOS.map((g) => [g.chave, 0])) } as Barra;
  for (const b of resto) {
    outras.indices.push(...b.indices);
    outras.receita += b.receita;
    outras.das += b.das;
    outras.notas += b.notas;
    for (const g of GRUPOS) outras[g.chave] = (outras[g.chave] as number) + (b[g.chave] as number);
  }
  return [...barras.slice(0, MAX_BARRAS - 1), outras];
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
  const [ocultos, setOcultos] = useState<Set<string>>(new Set());

  const d = dimensoes.includes(dimensao) ? dimensao : dimensoes[0];
  const barras = useMemo(() => {
    const todas = agregar(linhas, d);
    return d === "nota" ? limitar(todas) : todas;
  }, [linhas, d]);

  // a alíquota de cada fatia é o tributo ÷ a receita do grupo; a receita é uma série só
  const dados = barras.map((b) => ({
    ...b,
    ...Object.fromEntries(GRUPOS.map((g) => [g.chave, medida === "aliquota" ? (b.receita ? (b[g.chave] as number) / b.receita : 0) : b[g.chave]])),
  }));
  const series = medida === "receita" ? [] : GRUPOS.filter((g) => !ocultos.has(g.chave));
  const formatar = medida === "aliquota" ? percentual : brl;

  const escolhida = barras.find((b) => b.nome === selecionado);
  const filtradas = escolhida ? escolhida.indices.map((i) => linhas[i]) : linhas;
  const sel = filtradas.reduce((s, l) => ({ receita: s.receita + l.linha.valor, das: s.das + l.das }), { receita: 0, das: 0 });
  const iss = linhas.some((l) => l.iss_municipio > 0);

  function mudarDimensao(v: Dimensao) {
    setDimensao(v);
    setSelecionado(null); // o filtro de uma visão não vale na outra
  }
  const alternarSelecao = (nome: string) => setSelecionado((s) => (s === nome ? null : nome));

  return (
    <section className="rounded-md border border-surface bg-white" aria-labelledby="titulo-painel-das">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-surface px-4 py-2.5">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h2 id="titulo-painel-das">Painel do DAS</h2>
          <p className="text-sm text-text-muted">Clique numa barra para filtrar os números e a tabela abaixo.</p>
        </div>
      </header>
      <div className="space-y-4 p-4">
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <Segmentado rotulo="Ver por" valor={d} opcoes={dimensoes.map((x) => [x, ROTULO_DIMENSAO[x]])} aoMudar={mudarDimensao} />
          <Segmentado rotulo="Medida" valor={medida} opcoes={(["das", "aliquota", "receita"] as Medida[]).map((x) => [x, ROTULO_MEDIDA[x].replace(" (R$)", "")])} aoMudar={setMedida} />
        </div>

        {escolhida && (
          <p className="flex items-center gap-2 text-sm">
            <span className="text-text-muted">Filtro:</span>
            <span className="inline-flex items-center gap-1 rounded-full bg-highlight px-2.5 py-0.5 font-medium text-brand">
              {selecionado}
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

        {series.length > 0 && (
          <div className="flex flex-wrap gap-2 text-sm" aria-label="Grupos de tributo: clique para mostrar ou esconder">
            {GRUPOS.map((g) => {
              const visivel = !ocultos.has(g.chave);
              return (
                <button
                  key={g.chave}
                  type="button"
                  aria-pressed={visivel}
                  onClick={() =>
                    setOcultos((o) => {
                      const n = new Set(o);
                      if (n.has(g.chave)) n.delete(g.chave);
                      else if (n.size < GRUPOS.length - 1) n.add(g.chave); // sempre sobra um grupo no gráfico
                      return n;
                    })
                  }
                  className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 ${visivel ? "border-border bg-white text-text" : "border-dashed border-border bg-bg text-text-muted line-through"}`}
                >
                  <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: visivel ? g.cor : "var(--color-border)" }} />
                  {g.nome}
                </button>
              );
            })}
          </div>
        )}

        <div style={{ height: Math.max(140, barras.length * 38 + 40) }} role="img" aria-label={`${ROTULO_MEDIDA[medida]} por ${ROTULO_DIMENSAO[d].toLowerCase()}: ${dados.map((b) => `${b.nome} ${formatar(medida === "aliquota" ? (b.receita ? b.das / b.receita : 0) : medida === "receita" ? b.receita : b.das)}`).join(", ")}`}>
          <ResponsiveContainer>
            <BarChart data={dados} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }} barCategoryGap={8}>
              <CartesianGrid horizontal={false} stroke="var(--color-surface)" />
              <XAxis type="number" tickFormatter={(v: number) => (medida === "aliquota" ? percentual(v) : brl(v).replace(",00", ""))} tick={{ fontSize: 12, fill: "var(--color-text-muted)" }} axisLine={false} tickLine={false} />
              <YAxis
                type="category"
                dataKey="nome"
                width={190}
                tick={{ fontSize: 12, fill: "var(--color-text)", cursor: "pointer" }}
                tickFormatter={(v: string) => (v.length > 28 ? `${v.slice(0, 27)}…` : v)}
                axisLine={false}
                tickLine={false}
                onClick={(e: { value?: string }) => e.value && alternarSelecao(e.value)}
              />
              <Tooltip cursor={{ fill: "var(--color-highlight)" }} content={<Dica medida={medida} />} isAnimationActive={false} />
              {medida === "receita" ? (
                <Bar dataKey="receita" name="Receita" fill="var(--color-serie-1)" radius={[0, 4, 4, 0]} isAnimationActive={false} onClick={(b: { nome: string }) => alternarSelecao(b.nome)} cursor="pointer">
                  {dados.map((b) => (
                    <Cell key={b.nome} fillOpacity={!escolhida || escolhida.nome === b.nome ? 1 : 0.3} />
                  ))}
                </Bar>
              ) : (
                series.map((g, i) => (
                  <Bar
                    key={g.chave}
                    dataKey={g.chave}
                    name={g.nome}
                    stackId="das"
                    fill={g.cor}
                    stroke="#fff"
                    strokeWidth={2}
                    radius={i === series.length - 1 ? [0, 4, 4, 0] : 0}
                    isAnimationActive={false}
                    onClick={(b: { nome: string }) => alternarSelecao(b.nome)}
                    cursor="pointer"
                  >
                    {dados.map((b) => (
                      <Cell key={b.nome} fillOpacity={!escolhida || escolhida.nome === b.nome ? 1 : 0.3} />
                    ))}
                  </Bar>
                ))
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>

        <Tabela
          cabecalho={["Nota", "Atividade", "Anexo", "Valor", "Alíquota", "DAS", ...(iss ? ["ISS ao município"] : [])]}
          numericas={[3, 4, 5, 6]}
        >
          {filtradas.map((l, i) => (
            <tr key={i}>
              <td className="px-2 py-1">{l.linha.descricao}</td>
              <td className="px-2 py-1">{atividade(l.anexo)}</td>
              <td className="px-2 py-1">{l.anexo}</td>
              <td className="num px-2 py-1 text-right">{brl(l.linha.valor)}</td>
              <td className="num px-2 py-1 text-right">{percentual(l.aliquota)}</td>
              <td className="num px-2 py-1 text-right">{brl(l.das)}</td>
              {iss && <td className="num px-2 py-1 text-right">{brl(l.iss_municipio)}</td>}
            </tr>
          ))}
        </Tabela>
      </div>
    </section>
  );
}

function Dica({ active, payload, medida }: { active?: boolean; payload?: { payload: Barra }[]; medida: Medida }) {
  if (!active || !payload?.length) return null;
  const b = payload[0].payload;
  // a dica usa os valores em R$ da barra, qualquer que seja a medida do gráfico
  const original = { ...b, ...Object.fromEntries(GRUPOS.map((g) => [g.chave, medida === "aliquota" ? (b[g.chave] as number) * b.receita : b[g.chave]])) };
  return (
    <div className="min-w-56 rounded border border-border bg-white px-3 py-2 text-sm shadow-sm">
      <p className="mb-1 font-medium">{b.nome}</p>
      <dl className="num grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5">
        {GRUPOS.filter((g) => (original[g.chave] as number) > 0).map((g) => (
          <div key={g.chave} className="contents">
            <dt className="flex items-center gap-1.5 text-text-muted">
              <span aria-hidden className="h-2 w-2 rounded-sm" style={{ background: g.cor }} />
              {g.nome}
            </dt>
            <dd className="text-right">{brl(original[g.chave] as number)}</dd>
          </div>
        ))}
        <dt className="border-t border-surface pt-0.5 font-medium">DAS</dt>
        <dd className="border-t border-surface pt-0.5 text-right font-medium">{brl(b.das)}</dd>
        <dt className="text-text-muted">Receita</dt>
        <dd className="text-right">{brl(b.receita)}</dd>
        <dt className="text-text-muted">Alíquota</dt>
        <dd className="text-right">{percentual(b.receita ? b.das / b.receita : 0)}</dd>
        <dt className="text-text-muted">Notas</dt>
        <dd className="text-right">{b.notas}</dd>
      </dl>
    </div>
  );
}
