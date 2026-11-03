import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { api, mensagemErro } from "../api/cliente";
import type { Empresa } from "../api/tipos";
import { REGIMES } from "../lib/formato";
import { Botao, Erro, LegendaObrigatorio, Modal, Obrigatorio } from "./ui";

const UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split(" ");
const ATIVIDADES = { COMERCIO: "Comércio", INDUSTRIA: "Indústria", SERVICO: "Serviço" };
const campo = "mt-1 block w-full rounded border border-border bg-white px-2 py-1.5";

const vazio = () => ({ razao_social: "", cnpj: "", regime_tributario: "SIMPLES_NACIONAL", anexo_simples: "I", uf: "SP", cnae: "", atividade: "COMERCIO", representante_legal: "", telefone: "" });

/** Inclusão e correção pontual; a carga em volume continua sendo a importação da planilha. */
export function FormEmpresa({ empresa, fechar }: { empresa: Empresa | null; fechar: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState(() =>
    empresa
      ? { ...vazio(), ...empresa, anexo_simples: empresa.anexo_simples ?? "I", cnae: empresa.cnae ?? "", representante_legal: empresa.representante_legal ?? "", telefone: empresa.telefone ?? "" }
      : vazio(),
  );
  const [erro, setErro] = useState<string | null>(null);
  const salvar = useMutation({
    mutationFn: () => {
      const corpo = {
        razao_social: f.razao_social.trim(), cnpj: f.cnpj, regime_tributario: f.regime_tributario, uf: f.uf, atividade: f.atividade,
        anexo_simples: f.regime_tributario === "SIMPLES_NACIONAL" ? f.anexo_simples : null,
        cnae: f.cnae || null, representante_legal: f.representante_legal.trim() || null, telefone: f.telefone || null,
      };
      return empresa ? api.put(`/empresas/${empresa.id}`, corpo) : api.post("/empresas", corpo);
    },
    onSuccess: () => {
      qc.invalidateQueries();
      fechar();
    },
    onError: (e) => setErro(mensagemErro(e)),
  });

  function enviar(e: FormEvent) {
    e.preventDefault();
    if (f.razao_social.trim().length < 2) return setErro("Informe a razão social");
    if (f.cnpj.replace(/[^0-9A-Za-z]/g, "").length !== 14) return setErro("O CNPJ tem 14 caracteres");
    setErro(null);
    salvar.mutate();
  }
  const muda = empresa && (empresa.regime_tributario !== f.regime_tributario || empresa.uf !== f.uf);

  return (
    <Modal aberto titulo={empresa ? "Editar empresa" : "Nova empresa"} descricao={empresa?.razao_social} fechar={fechar} largura="max-w-3xl">
      <form onSubmit={enviar} className="grid gap-3 text-sm md:grid-cols-6">
        <label className="md:col-span-4">
          Razão social<Obrigatorio />
          <input autoFocus className={campo} maxLength={200} value={f.razao_social} onChange={(e) => setF({ ...f, razao_social: e.target.value })} />
        </label>
        <label className="md:col-span-2">
          CNPJ<Obrigatorio />
          <input className={campo} maxLength={18} placeholder="00.000.000/0000-00" value={f.cnpj} onChange={(e) => setF({ ...f, cnpj: e.target.value })} />
        </label>
        <label className="md:col-span-2">
          Regime atual<Obrigatorio />
          <select className={campo} value={f.regime_tributario} onChange={(e) => setF({ ...f, regime_tributario: e.target.value })}>
            {Object.entries(REGIMES).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          UF<Obrigatorio />
          <select className={campo} value={f.uf} onChange={(e) => setF({ ...f, uf: e.target.value })}>
            {UFS.map((u) => (
              <option key={u}>{u}</option>
            ))}
          </select>
        </label>
        <label>
          Atividade<Obrigatorio />
          <select className={campo} value={f.atividade} onChange={(e) => setF({ ...f, atividade: e.target.value })}>
            {Object.entries(ATIVIDADES).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="md:col-span-2">
          CNAE principal
          <input className={campo} maxLength={10} placeholder="4530-7/03" value={f.cnae} onChange={(e) => setF({ ...f, cnae: e.target.value })} />
        </label>
        <label className="md:col-span-4">
          Representante legal
          <input className={campo} maxLength={120} value={f.representante_legal} onChange={(e) => setF({ ...f, representante_legal: e.target.value })} />
        </label>
        <label className="md:col-span-2">
          Telefone com DDD
          <input className={campo} maxLength={16} placeholder="(11) 3333-4444" value={f.telefone} onChange={(e) => setF({ ...f, telefone: e.target.value })} />
        </label>
        <div className="space-y-2 md:col-span-6">
          {f.atividade !== "COMERCIO" && <p className="text-warning-ink">O cálculo está validado só para comércio (Anexo I do Simples e presunção de 8% e 12%).</p>}
          {muda && <p className="text-warning-ink">Mudar o regime ou a UF deixa as simulações desta empresa desatualizadas.</p>}
          <Erro mensagem={erro} />
          <div className="flex items-center justify-between gap-2 border-t border-surface pt-3">
            <LegendaObrigatorio />
            <div className="flex gap-2">
              <Botao variante="secundario" onClick={fechar}>
                Cancelar
              </Botao>
              <Botao type="submit" disabled={salvar.isPending}>
                {empresa ? "Salvar alterações" : "Cadastrar empresa"}
              </Botao>
            </div>
          </div>
        </div>
      </form>
    </Modal>
  );
}
