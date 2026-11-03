export type Planejamento = {
  id: number;
  empresa_id: number;
  razao_social: string;
  cnpj: string;
  regime_tributario: string;
  competencia_inicial: string;
  competencia_final: string;
  status: string;
  progresso: number;
  sem_bens: boolean;
  criado_em: string;
  documentos_faltando: number;
  documentos_recebidos_em: string | null;
};

export type Empresa = {
  id: number;
  razao_social: string;
  cnpj: string;
  regime_tributario: string;
  anexo_simples: string | null;
  atividade: string;
  uf: string;
  cnae: string | null;
  representante_legal: string | null;
  telefone: string | null;
  ativo: boolean;
  criado_em: string | null;
};

export type Bloco = {
  codigo: string;
  nome: string;
  peso: number;
  esperados: number;
  preenchidos: number;
  pendencias: { competencia: string | null; descricao: string }[];
};

export type SimulacaoResumo = {
  id: number;
  versao: number;
  tipo: "PRELIMINAR" | "FINAL";
  regime_recomendado: string;
  pendencias: string | null;
  desatualizada: boolean;
  executada_em: string;
  aprovada_em: string | null;
};

export type Tributo = { tributo: string; valor: number; competencia: string | null };
export type ResultadoRegime = {
  regime: string;
  estadual: number;
  federal: number;
  total: number;
  tributos: Tributo[];
  detalhes: Record<string, number>;
  elegivel: boolean;
};

export type Resultado = {
  base: Record<string, Record<string, number>>;
  simples: ResultadoRegime;
  presumido: ResultadoRegime;
  real: ResultadoRegime;
  comparativo: {
    regime: string;
    estadual: number;
    federal: number;
    total: number;
    aliquota_efetiva: number;
    diferenca_melhor: number;
    posicao: number;
  }[];
  melhor_regime: string;
  reforma: {
    ano: number;
    cbs: number;
    ibs: number;
    fator_icms: number;
    cargas: Record<string, number>;
    aliquotas: Record<string, number>;
    melhor: string;
  }[];
  oportunidades: {
    id: number;
    codigo: string;
    titulo: string;
    impacto: number | null;
    prioridade: string;
    acao: string;
    situacao: string;
  }[];
  pontos_criticos: { codigo: string; texto: string }[];
  crescimento: {
    rbt12: number;
    aliquota_das: number;
    aliquota_simples: number | null;
    aliquota_lp: number;
    aliquota_lr: number;
    melhor: string;
    observacao: string;
  }[];
  margem_equilibrio_lr_lp: number | null;
  verificacao_ncm?: LinhaNcm[];
};

export type LinhaNcm = {
  ncm: string;
  receita: number;
  participacao: number;
  monofasico: boolean;
  sujeito_st: boolean;
  sem_regra: boolean;
  produto_exemplo: string | null;
  confianca: "ALTA" | "MEDIA" | null;
  indicio_ncm_incorreto: boolean;
  requer_revisao: boolean;
  acao_recomendada: string | null;
  cst_ibs_cbs: string | null;
  cclass_trib: string | null;
  beneficio_reforma: string | null;
};

export type PassoMemoria = {
  secao: string;
  descricao: string;
  formula: string;
  valor: number;
  competencia: string | null;
  fundamento: string | null;
};

export type Catalogo = {
  id: number;
  nome: string;
  itens: { id: number; nome: string; ativo: boolean }[];
}[];
