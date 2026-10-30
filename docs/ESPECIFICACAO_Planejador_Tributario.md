# Mini-projeto Full Stack — Planejador Tributário Automático

> Revisão do documento *"Mini-projeto Full Stack – Portal de Despesas para Planejamento Tributário"* (01/10/2026).
> O portal de despesas deixa de ser o produto final e passa a ser **um dos módulos de entrada** de um sistema que
> **calcula, compara e recomenda** o regime tributário (Simples Nacional × Lucro Presumido × Lucro Real), incluindo a
> transição da Reforma Tributária (2027–2033).
>
> Base dos cálculos: a planilha inicial de planejamento e a planilha final, adotada como **referência oficial**
> do motor. Ambas são de um cliente de referência do comércio de autopeças, aqui anonimizado.

---

## 1. Contexto do Projeto

Hoje o planejamento tributário de cada cliente é montado à mão em várias planilhas:

| Etapa atual (manual) | Planilha / aba | Problema |
|---|---|---|
| Levantamento de despesas | `DESPESAS SIMULAÇÃO TRIBUTÁRIA` | Coberto pelo portal original |
| Saídas item a item (NF-e) | abas `06-2026`, `07-2026`, `08-2026` (~17,6 mil linhas) | Colagem manual de relatórios; fórmulas por linha |
| Premissas e tabelas legais | aba `Premissas` | Tabela do Anexo I, alíquotas e cronograma da Reforma copiados em cada arquivo |
| Monofásico por NCM | `Premissas` seção 8 + `Verificação por NCM` | Classificação refeita para cada cliente |
| Créditos (ICMS, PIS/COFINS, IBS/CBS) | `Memória dos Créditos` | Médias e parâmetros digitados |
| IRPJ/CSLL (LP e LR) | `IRPJ e CSLL` | DRE fiscal manual |
| Comparativo e Reforma | `Comparativo 3 Regimes` | — |
| Relatório ao cliente | `Resumo Executivo` + PPTX/PDF timbrado | Texto e conclusões escritos à mão |

**Objetivo:** um sistema web em que o escritório cadastra a empresa, importa as notas fiscais e o levantamento de
despesas e recebe automaticamente:

1. a carga tributária de cada regime por competência, por trimestre e pela alíquota efetiva;
2. o regime mais vantajoso hoje e em cada ano da Reforma (2026 → 2033);
3. a memória de cálculo auditável, linha a linha, com fundamento legal;
4. as oportunidades de economia ou recuperação identificadas por regras;
5. o relatório final em PDF (substitui o Resumo Executivo e o PDF timbrado) e a exportação Excel.

O sistema **não substitui o contador**: ele gera uma simulação com premissas explícitas. A conclusão só vale para o
cliente depois de revisada e aprovada pelo contador.

---

## 2. Prazo, Fases e Entrega

O escopo cresce em relação ao portal original (5 dias). Sugestão de divisão em três entregas incrementais, cada uma
funcionando de ponta a ponta:

| Fase | Conteúdo | Estimativa |
|---|---|---|
| **F1 – Coleta** | Autenticação, empresas, planejamento, levantamento de despesas (escopo do PDF original), compras, folha, progresso | 5 dias |
| **F2 – Motor** | Importação de NF-e (XML e relatório Domínio), regras CFOP/NCM, parâmetros versionados, motor dos 3 regimes, memória de cálculo, testes de referência (caso do cliente de referência) | 6 dias |
| **F3 – Resultado** | Reforma 2027–2033, oportunidades, simulação de crescimento, relatório PDF, exportação Excel, dashboard | 4 dias |

A entrega deve conter:

- código-fonte completo (backend e frontend);
- instruções completas de execução;
- banco de dados com scripts de criação, carga inicial (catálogo de despesas, tabelas legais, regras de CFOP e NCM,
  usuários de demonstração) e dicionário de dados;
- **Memorial Técnico de Desenvolvimento**;
- README;
- **suíte de testes de referência** que reproduz os números do caso de referência (seção 9) até o centavo;
- evidências da aplicação funcionando, incluindo o PDF final e a planilha exportada pelo sistema.

---

## 3. Requisitos Funcionais

### 3.1 Autenticação e perfis

Mantém as regras do documento original: login com usuário e senha, sessão JWT, logout, sem autocadastro, permissões
verificadas no backend em cada rota.

| Funcionalidade | Contador | Analista |
|---|---|---|
| Importar e editar empresas | Sim | Não |
| Cadastrar usuários | Sim | Não |
| Criar planejamento (empresa + período) | Sim | Não |
| Preencher despesas, compras, folha, bens e documentos | Sim | Sim |
| Importar NF-e (saídas e entradas) | Sim | Sim |
| Classificar NCMs pendentes | Sim | Sim (sugestão) / aprovação só do contador |
| Enviar levantamento para conferência | Sim | Sim |
| Conferir ou devolver levantamento | Sim | Não |
| Ajustar premissas do planejamento | Sim | Não |
| **Executar simulação** | Sim | Sim (gera versão *preliminar*) |
| **Aprovar simulação e emitir relatório final** | Sim | Não |
| Manter tabelas legais (Anexo I, alíquotas, Reforma, NCM, CFOP) | Sim | Não |
| Ver progresso, pendências e dashboard | Sim | Sim |
| Relatório PDF e exportação Excel | Sim | Não |

### 3.2 Empresas

Mantém a importação de empresas do documento original (xlsx/csv, prévia linha a linha, CNPJ validado e gravado com
14 dígitos, upsert por CNPJ, inativação em vez de exclusão). Campos novos:

| Campo | Obrigatório | Uso no cálculo |
|---|---|---|
| UF | Sim | Alíquota interna de ICMS, âmbito interno × interestadual |
| CNAE principal | Sim | Define o anexo do Simples e a presunção do LP (comércio 8%/12%; serviços 32%) |
| Atividade (comércio / indústria / serviço) | Sim | Seleciona o anexo e as regras |
| Regime atual | Sim | Ponto de partida da comparação |
| Anexo do Simples atual | Se regime atual = Simples | Tabela de faixas |

> **Escopo da 1ª versão:** comércio (Anexo I do Simples, presunção 8%/12%). Os demais anexos e atividades ficam
> cadastráveis nas tabelas, mas sem regras validadas — o sistema avisa quando a empresa não é de comércio.

### 3.3 Planejamento (cabeçalho do estudo)

Um **planejamento** reúne todas as informações de uma empresa para um **período-base** (normalmente um trimestre,
ex.: 06 a 08/2026) e é a unidade sobre a qual o motor roda.

Campos: empresa, competência inicial, competência final, status, progresso, responsável, observações aceitas, `sem_bens`.

Status do planejamento:

```
Em coleta ──► Em conferência ──► Pronto para simular ──► Simulado ──► Aprovado (relatório final emitido)
     ▲               │                                       │
     └── devolvido ──┘                                       └── nova versão se os dados mudarem
```

Cada transição é gravada em `historico_status` (usuário, data, motivo).

### 3.4 Módulo de coleta (entradas do motor)

#### a) Levantamento de despesas — mantido do documento original

Todo o item 3 do documento original permanece (formulário no layout da planilha, quatro grupos, outras despesas,
vazio ≠ zero, copiar competência anterior, observações com aceite, envio para conferência).

**Novidade:** cada item do catálogo passa a ter a **classificação tributária** usada pelo motor (configurável pelo
contador, com valor padrão na carga inicial):

| Campo do item | Valores | Exemplo (aba `IRPJ e CSLL`) |
|---|---|---|
| `dedutivel_irpj_csll` | Sim / Não / Integra custo | Publicidade = Sim |
| `credito_pis_cofins_lr` | Sim / Não / Proporcional | Fretes na venda = Sim; Contabilidade = Não |
| `credito_ibs_cbs` | Sim / Não / Limitado | Tarifas do marketplace = Sim |
| `natureza` | texto + fundamento legal | "Frete na venda: crédito (Lei 10.833/2003, art. 3º, IX)" |

A folha de salários **não** é item do catálogo: fica no bloco de folha e pró-labore, que calcula os encargos. O item antigo "Folha de Pagamento" está desativado e, se tiver valor, é ignorado nos meses em que o bloco de folha foi informado, para não deduzir duas vezes no Lucro Real.

O catálogo recebe os itens que aparecem nos clientes de marketplace: *Tarifas de envio*, *Tarifas de venda
(comissão)*, *Tarifas de armazenamento*, *Tarifas de envio Full*, *Campanhas de publicidade no marketplace*,
*Garantia* e *Embalagens*.

#### b) Faturamento — notas fiscais de saída

Formas de importação (em ordem de prioridade):

1. **XML das NF-e** (upload de .zip ou de vários arquivos) — fonte mais confiável;
2. **Relatório "Movimentação de Produtos – ICMS – PIS – COFINS"** do sistema contábil (.xlsx), no formato usado nas
   abas mensais da planilha;
3. digitação manual do faturamento mensal por âmbito e por monofásico × não monofásico (modo simplificado, sem
   análise por item; o relatório indica que o estudo foi feito em modo simplificado).

Para cada item importado são gravados: NF-e, data, código e descrição do produto, NCM, CFOP, natureza, quantidade,
valor unitário, valor dos produtos, valor total, UF de destino. O sistema **deriva** (regras das seções 4.2 e 4.3):

- `gera_receita` (pelo CFOP);
- `ambito` (interna × interestadual, pela UF do emitente e do destinatário);
- `monofasico` (pelo NCM);
- `receita_liquida` (valor total menos devoluções rateadas — seção 5.1).

Regras:

- uma mesma NF-e/item não pode ser importada duas vezes no mesmo planejamento (chave de acesso + nº do item);
- importação de grande volume (≥ 20 mil itens) é processada em segundo plano, com barra de andamento;
- relatório de importação: itens lidos, importados, ignorados (com o motivo), CFOPs desconhecidos e NCMs sem regra.
  CFOP desconhecido ou NCM sem regra **viram pendência** e bloqueiam a simulação final (a preliminar roda e mostra o
  aviso).

#### c) Devoluções de vendas

Por competência: valor das devoluções (digitado ou somado das NF-e de entrada com CFOP 1.202/2.202). O motor rateia
proporcionalmente sobre os itens que geram receita.

#### d) Compras de mercadorias (entradas)

Por competência: valor total das compras para revenda. Opcional e preferível: importar os XML de entrada, o que
permite usar o **ICMS destacado real** e o CST de PIS/COFINS real em vez de médias.

Composição das compras por origem (para o crédito de ICMS quando não há XML): interna (alíquota interna da UF),
interestadual S/SE 12%, interestadual N/NE/CO/ES 7%, importados 4%. **A soma deve dar 100%.**

#### e) Folha e pró-labore

Por competência: folha de salários e pró-labore. Campo vazio = "não informado" (pendência), igual às despesas.
Encargos padrão: 27,8% sobre a folha (CPP 20% + RAT + Terceiros) e 20% sobre o pró-labore (parametrizáveis).

#### f) Bens próprios e documentos

Mantidos do documento original (bens acima de R$ 1.200,00; checklist de documentos com upload). Documentos novos no
checklist: *XML ou relatório de saídas*, *relatório de entradas*, *relatório de tarifas do marketplace*, *extrato do
PGDAS-D (RBT12)*, *inventário de estoque*.

#### g) Premissas do planejamento

Valores padrão vêm das tabelas legais; o contador pode sobrescrever por planejamento (cada alteração fica registrada):

| Premissa | Padrão | Referência na planilha |
|---|---|---|
| RBT12 informado (PGDAS-D) | vazio → estimado | `Premissas!B15` |
| Aplicar ICMS-ST nas vendas internas | Não | `Premissas!B69` |
| Alíquota interna de ICMS | pela UF/NCM | `Premissas!B70` (18%) |
| Alíquota interestadual média | 12% | `Premissas!B71` |
| Excluir ICMS da base do PIS/COFINS (Tema 69) | Não | `Premissas!B85` |
| Crédito de PIS/COFINS sobre fretes/armazenagem | Proporcional | `Premissas!B80` |
| % das compras com crédito de IBS/CBS | 100% | `Premissas!B63` |
| Estoque inicial e final | vazio → estoque constante | aviso do Resumo Executivo, ponto 2 |
| Adições, exclusões e prejuízo fiscal a compensar (LR) | 0 | `IRPJ e CSLL!B54:B55` |
| Ano-base da Reforma para a análise item a item | 2033 | `Premissas!B41` |

### 3.5 Tabelas legais versionadas (mantidas pelo contador)

Nenhuma alíquota fica fixa no código. Cada tabela tem **vigência** (`vigencia_inicio`, `vigencia_fim`), e cada simulação
grava a versão usada, para que um relatório antigo continue reproduzível.

| Tabela | Conteúdo da carga inicial |
|---|---|
| `simples_faixa` | Anexo I: 6 faixas (RBT12 de/até, alíquota nominal, parcela a deduzir) e repartição (IRPJ, CSLL, COFINS, PIS, CPP, ICMS) — `Premissas` A31:K37 |
| `parametro_tributario` | PIS/COFINS cumulativo 0,65%/3%; não cumulativo 1,65%/7,6%; IRPJ 15%; adicional 10% acima de R$ 20 mil/mês; CSLL 9%; presunções 8%/12%; limite LC 224/2025 R$ 5 mi/ano com acréscimo de 10% na presunção; sublimite R$ 3,6 mi; teto R$ 4,8 mi; encargos de folha |
| `reforma_cronograma` | por ano de 2027 a 2033: CBS, IBS, fator de ICMS mantido — `Premissas` A44:E50 (alíquotas de referência CBS 8,8% e IBS 17,7%) |
| `icms_aliquota` | por UF de origem × destino e, opcionalmente, por NCM |
| `cfop_regra` | CFOP, natureza, gera receita?, CSOSN/CST por regime, CST IBS/CBS e cClassTrib — `Premissas` seção 7 |
| `ncm_regra` | NCM, monofásico?, confiança (Alta/Média), fundamento (Lei 10.485/2002, Anexos I e II), sujeito a ST?, CEST, observação, ação recomendada — `Premissas` seção 8 e `Verificação por NCM` |

A tabela `ncm_regra` é **compartilhada entre clientes**: um NCM classificado no planejamento do cliente de referência já vem resolvido
para a próxima autopeças. Classificação com confiança *Média* aparece no relatório como ponto a validar.

### 3.6 Motor de cálculo

Executa as fórmulas da seção 5 sobre os dados de um planejamento e grava uma **simulação** (versionada, imutável).

- Disparado manualmente ("Simular") ou automaticamente quando o planejamento passa para *Pronto para simular*.
- Cada execução grava: versão das tabelas legais, premissas usadas, hash dos dados de entrada, usuário, data/hora,
  resultado por regime × tributo × competência × ano da Reforma e **memória de cálculo** (cada passo com a fórmula, os
  valores de entrada e o resultado — equivalente às colunas "Origem / fórmula" da `Memória dos Créditos`).
- Se os dados de entrada mudarem depois da simulação, ela é marcada como **desatualizada** e o relatório final fica
  bloqueado até nova execução.
- O motor é um módulo de **funções puras** (entrada → saída, sem acesso a banco), testável isoladamente.
- Valores monetários em `Decimal`; arredondamento para 2 casas **apenas na apresentação** e nos totais finais de cada
  tributo (a planilha trabalha sem arredondar por linha; o sistema deve fazer igual para bater com ela).

### 3.7 Comparativo e recomendação

Telas equivalentes às abas da planilha final:

1. **Base da operação** — faturamento bruto, devoluções, receita líquida, monofásico × não monofásico, interna ×
   interestadual, remessas sem receita, compras, despesas (por mês e trimestre, com % sobre o faturamento).
2. **Simples Nacional** — RBT12, faixa, alíquota efetiva, repartição e DAS por tributo.
3. **Lucro Presumido** — ICMS (débito, crédito, a recolher), PIS/COFINS cumulativos, IRPJ (com adicional e
   acréscimo da LC 224/2025), CSLL.
4. **Lucro Real** — ICMS, PIS/COFINS não cumulativos (débitos, créditos, saldo credor), DRE fiscal até IRPJ e CSLL.
5. **Comparativo 2026** — carga estadual, federal, total, alíquota efetiva, diferença para o melhor, posição (1º, 2º, 3º).
6. **Reforma 2027–2033** — carga por regime em cada ano, alíquota efetiva e melhor regime por ano (tabela e gráfico).
7. **Margem de equilíbrio LR × LP** — margem de LAIR abaixo da qual o Lucro Real fica mais barato.
8. **Simulação de crescimento** — alíquota do Simples para RBT12 atual, R$ 3,6 mi, R$ 3,6 mi + R$ 0,01, R$ 4,2 mi e R$ 4,8 mi
   contra LP e LR; o contador pode incluir outros valores.
9. **Matriz por produto e por NCM** — receita, monofásico, CSTs sugeridos por regime e carga de débitos por item.

A recomendação é o regime de menor carga total no período-base, acompanhada do texto gerado a partir do resultado
(como a célula `Resumo Executivo!A20`) e dos pontos críticos ativos (seção 3.9).

### 3.8 Oportunidades (motor de regras)

Cada oportunidade é uma regra cadastrada com condição, fórmula de impacto, prioridade e texto de ação. O motor avalia
todas a cada simulação; o contador pode marcar como *descartada* (com motivo) ou *confirmada*.

| # | Oportunidade | Condição | Impacto estimado (trimestre) | Prioridade |
|---|---|---|---|---|
| 1 | CPP embutida no DAS | Regime atual = Simples | `CPP_SN − 3 × (folha × 27,8% + pró-labore × 20%)` | Alta |
| 2 | Segregação dos monofásicos no PGDAS-D (recuperação 5 anos) | Simples e NF-e com CST 99 em itens monofásicos | `RL_mono × Aef × (%PIS + %COFINS)` | Alta |
| 3 | ICMS-ST nas vendas internas (recuperação) | Simples, itens sujeitos à ST com CSOSN 102 | `RL_interna × Aef × %ICMS` | Alta |
| 4 | Revisão de NCM (possível monofásico) | NCMs marcados "indício de NCM incorreto" | Receita desses NCMs × `Aef × (%PIS + %COFINS)` | Média |
| 5 | Sublimite de R$ 3,6 mi | RBT12 ≥ 80% do sublimite | Qualitativo (aponta a simulação de crescimento) | Alta |
| 6 | Crédito de ICMS pela alíquota real das compras | Composição das entradas ≠ premissa anterior | `Compras × (alíq. real − alíq. anterior)` | Média |
| 7 | Exclusão do ICMS da base de PIS/COFINS (Tema 69) | Premissa Tema 69 = Não | `ICMS débito dos itens não monofásicos × 9,25%` (LR) / `× 3,65%` (LP) | Média |
| 8 | Crédito integral de PIS/COFINS sobre fretes e armazenagem | LR, premissa = Proporcional | `Despesas com crédito × (1 − part. não monofásica) × 9,25%` | Média |
| 9 | Despesas típicas não informadas | Itens do catálogo vazios (lista da aba `IRPJ e CSLL`, seção 4) | Qualitativo, com a lista | Alta |
| 10 | Devoluções | Devoluções > 0 | Valor deduzido; conferir PGDAS-D e estorno de ICMS | Média |
| 11 | Remessas interestaduais para fulfillment | CFOP 6.949 / 6.905 presentes | Qualitativo | Média |
| 12 | Opção pelo IBS/CBS por fora do DAS | Simples, vendas majoritariamente B2C | Qualitativo | Baixa |

O total de **recuperação imediata** (itens 2 + 3) aparece em destaque, com a observação de que o direito alcança os
5 anos anteriores (CTN, art. 168).

### 3.9 Pontos críticos (avisos automáticos)

O relatório lista automaticamente as premissas frágeis da simulação:

- folha e/ou pró-labore não informados (LP e LR sem INSS sobre folha);
- estoque não informado (CMV = compras do período);
- crédito de ICMS por média de origem (sem XML de entrada);
- NCMs com confiança *Média* ou indício de classificação incorreta;
- RBT12 estimado (sem extrato do PGDAS-D);
- alíquotas de IBS/CBS são projeções sujeitas a Resolução do Senado;
- troca de regime só vale a partir de janeiro do ano seguinte.

### 3.10 Progresso do planejamento

Mesma mecânica do documento original — `Progresso = Σ (peso do bloco × itens preenchidos ÷ itens esperados)`,
calculado no backend, arredondado para baixo, 100% só quando nada falta, pesos configuráveis (soma = 100%) — com os
blocos novos:

| Bloco | Peso padrão | Itens esperados | Conta como preenchido quando |
|---|---|---|---|
| Saídas (faturamento) | 20% | 1 por competência | NF-e/relatório importado ou faturamento manual informado |
| Despesas do catálogo | 20% | cada item × cada competência | valor informado, inclusive R$ 0,00 ou "não houve" |
| Compras | 15% | 1 por competência | valor informado (e composição por origem = 100%) |
| Classificação de NCM | 10% | cada NCM distinto das saídas | NCM com regra aprovada |
| Folha e pró-labore | 10% | 2 por competência | valor informado ou "não houve" |
| Documentos | 10% | cada documento × cada competência | arquivo enviado ou "não se aplica" com justificativa |
| Outras despesas | 5% | cada grupo × cada competência | "não possui" ou ao menos uma linha |
| Bens próprios | 5% | 1 por empresa | ao menos um bem ou "não possui bens" |
| Observações | 5% | 1 por planejamento | aceite registrado |

A tela de pendências continua igual (agrupada por competência e bloco, com link direto para o campo) e agora inclui
"CFOP sem regra" e "NCM sem regra".

### 3.11 Relatório PDF (somente contador)

Substitui o `Resumo Executivo` e o PDF timbrado. Gerado no backend, A4, com número de página e data/hora no rodapé,
arquivado (quem gerou, quando, hash SHA-256), nome `PLANEJAMENTO_<CNPJ>_<periodo>_<data>.pdf`. Marca d'água
**PRELIMINAR** quando o progresso < 100%, a simulação não está aprovada ou está desatualizada.

Conteúdo:

1. Cabeçalho do escritório; empresa, CNPJ, regime atual, CNAE, período-base, data e usuário.
2. Escopo e base do estudo (receita líquida, RBT12 e se é estimado, tributos comparados, cenário de ICMS).
3. Quadro-síntese: carga e alíquota efetiva por regime em 2026, 2027 e 2033 e melhor regime em cada ano.
4. Oportunidades identificadas (tabela da seção 3.8, com impacto e prioridade).
5. Simulação de crescimento.
6. Pontos críticos e premissas a validar.
7. Recomendação e próximos passos (texto-base gerado e editável pelo contador antes da emissão).
8. Anexos: comparativo detalhado, IRPJ/CSLL, memória dos créditos, verificação por NCM, despesas por grupo e
   competência, bens, documentos, histórico de status.
9. Fontes legais (lista mantida em tabela).

### 3.12 Exportação Excel (somente contador)

Arquivo .xlsx que reproduz as abas da planilha final (`Resumo Executivo`, `Comparativo 3 Regimes`, `IRPJ e CSLL`,
`Memória dos Créditos`, `Verificação por NCM`, `Premissas`, `Matriz por Produto` e uma aba por competência com os itens),
**com valores** e, nas abas de resumo, com as fórmulas que ligam as células, para que o contador possa auditar no Excel.
Critério de aceite: os totais exportados batem com a tela e com a seção 9.

A exportação do levantamento de despesas no layout antigo (uma aba por competência ou trimestre lado a lado)
continua disponível como no documento original.

### 3.13 Consulta, filtros e dashboard

Filtros do documento original (período, empresa, status, grupo de despesa, texto livre) mais: regime atual,
regime recomendado, faixa de economia estimada.

Dashboard: empresas em planejamento por status; faixas de progresso; simulações desatualizadas; **economia anual
estimada da carteira** (soma de "carga atual − carga do melhor regime" × 4); recuperações identificadas (itens 2 e 3);
empresas próximas do sublimite.

---

## 4. Regras de classificação (pré-processamento dos itens)

### 4.1 CFOP → receita e CSTs (carga inicial — `Premissas` seção 7)

| CFOP | Natureza | Gera receita? | Simples CSOSN / CST PIS-COF | LP/LR CST ICMS | LP/LR CST PIS-COF | IBS/CBS CST / cClassTrib |
|---|---|---|---|---|---|---|
| 5106 | Venda – mercadoria que não transita (interna) | Sim | 102 (500 se ST) / 99 ou 04 | 00 (60 se ST) | 01 ou 04 | 000 / 000001 |
| 6106 | Venda – mercadoria que não transita (interestadual) | Sim | 102 (500 se ST) / 99 ou 04 | 00 (60 se ST) | 01 ou 04 | 000 / 000001 |
| 5949 | Outras saídas / remessa (interna) | Não | 400 / 49 | 41 | 49 | 410 / 410999 |
| 6949 | Outras saídas / remessa (interestadual) | Não | 400 / 49 | 41 | 49 | 410 / 410999 |
| 6905 | Remessa para depósito fechado / armazém geral | Não | 400 / 49 | 41 | 49 | 410 / 410999 |

Os CFOPs de venda mais comuns (5101, 5102, 6101, 6102, 5405, 6108 etc.) entram na carga com a mesma lógica. CFOP fora
da tabela = pendência.

### 4.2 Derivações por item

```
gera_receita  = cfop_regra.gera_receita
ambito        = "Interna" se UF destino = UF empresa, senão "Interestadual"
monofasico    = ncm_regra.monofasico (NCM sem regra → pendência; na preliminar, assume "Não")
st_interna    = premissa aplicar_st = Sim  E  ambito = Interna  E  gera_receita
```

### 4.3 CSTs sugeridos (Matriz por Produto)

```
CSOSN (Simples)     = "400" se não gera receita; "500" se st_interna; senão "102"
CST PIS/COF Simples = "49" se não gera receita; "04" se monofásico; senão "99"
CST ICMS (LP/LR)    = "41" se não gera receita; "60" se st_interna; senão "00"
CST PIS/COF (LP/LR) = "49" se não gera receita; "04" se monofásico; senão "01"
```

---

## 5. Fórmulas do motor (referência: planilha final)

Notação por competência `m` do período-base; "trimestre" = soma das competências. `Σ` = soma dos itens que geram
receita, salvo indicação.

### 5.1 Base da operação

```
RB_m        = Σ vl_total_item                                  (faturamento bruto)
DEV_m       = devoluções informadas
fdev_m      = DEV_m / RB_m
RL_item     = vl_total_item × (1 − fdev_m)                     (receita líquida, devolução rateada)
RL_m        = Σ RL_item
RL_mono_m   = Σ RL_item  onde monofasico
RL_trib_m   = RL_m − RL_mono_m
RL_int_m    = Σ RL_item  onde ambito = Interna
part_trib_m = RL_trib_m / RL_m                                 (participação não monofásica)
```

### 5.2 Simples Nacional (Anexo I)

```
RBT12  = RBT12 informado  OU  (Σ RL do período / nº de meses) × 12        [marcar "estimado"]
faixa  = maior faixa com RBT12_de ≤ RBT12
Aef    = (RBT12 × aliq_nominal − parcela_deduzir) / RBT12

ICMS_SN_item   = 0 se st_interna, senão RL_item × Aef × %ICMS
PIS_SN_item    = 0 se monofasico, senão RL_item × Aef × %PIS
COFINS_SN_item = 0 se monofasico, senão RL_item × Aef × %COFINS
IRPJ_CSLL_SN   = RL × Aef × (%IRPJ + %CSLL)
CPP_SN         = RL × Aef × %CPP
DAS            = Σ ICMS_SN + Σ PIS_SN + Σ COFINS_SN + IRPJ_CSLL_SN + CPP_SN
```

Melhorias obrigatórias em relação à planilha:

- se houver histórico de 12 meses, calcular o RBT12 **de cada competência** (a planilha usa um RBT12 único);
- **RBT12 acima do sublimite (R$ 3,6 mi):** o ICMS sai do DAS e é calculado como no regime normal (seção 5.3); a
  planilha só sinaliza isso em texto;
- RBT12 acima de R$ 4,8 mi: Simples marcado como "inelegível".

### 5.3 ICMS — regime normal (LP e LR)

```
Base_ICMS_item = RL_item  se CST ICMS = "00",  senão 0
Aliq_item      = aliquota interna se Interna, senão aliquota interestadual (tabela icms_aliquota)
DEB_ICMS_m     = Σ Base_ICMS_item × Aliq_item

com XML de entrada:  CRED_ICMS_m = Σ ICMS destacado nas entradas
sem XML:             CRED_ICMS_m = Compras_m × Σ(%origem × alíquota da origem)

ICMS_rec_m     = max(0, DEB_ICMS_m − CRED_ICMS_m)
```

Melhoria: o saldo credor de um mês (`CRED > DEB`) é **transportado** para o mês seguinte (a planilha descarta).

### 5.4 Lucro Presumido

```
Base_PISCOF_LP_item = RL_item − (Tema69 ? DEB_ICMS_item : 0)    apenas CST 01 (não monofásico)
PIS_LP  = Σ Base × 0,65%      COFINS_LP = Σ Base × 3%

R        = RL do trimestre
Limite   = R$ 5.000.000 / 4 = R$ 1.250.000 por trimestre (LC 224/2025)
Base_IR  = min(R, Limite) × 8%  + max(0, R − Limite) × 8,8%
IRPJ_LP  = Base_IR × 15% + max(0, Base_IR − 20.000 × nº meses) × 10%
Base_CS  = min(R, Limite) × 12% + max(0, R − Limite) × 13,2%
CSLL_LP  = Base_CS × 9%

Total_LP = Σ ICMS_rec + PIS_LP + COFINS_LP + IRPJ_LP + CSLL_LP  (+ INSS sobre folha, se informada)
```

### 5.5 Lucro Real

PIS/COFINS não cumulativos, por competência:

```
DEB_PISCOF_m  = Σ Base_PISCOF_item × 9,25%                      (mesma base do LP)
Compras_cred_m = Compras_m × part_trib_m                        (sem XML: mix das vendas)
Desp_cred_m    = Σ despesas com credito_pis_cofins = Sim × (premissa Integral ? 1 : part_trib_m)
CRED_PISCOF_m  = (Compras_cred_m + Desp_cred_m) × 9,25%
PISCOF_rec_m   = max(0, DEB − CRED);    Saldo_credor_m = max(0, CRED − DEB)  (acumulável)
```

DRE fiscal do trimestre:

```
RL
(−) Σ ICMS_rec
(−) Σ PISCOF_rec
(−) CMV  = Estoque_inicial + Compras − Estoque_final   (sem estoque: CMV = Compras, com aviso)
(−) Despesas dedutíveis (catálogo com dedutivel_irpj_csll = Sim)
(−) Pessoal = Σ [folha × (1 + 27,8%) + pró-labore × (1 + 20%)]
(=) LAIR
(+) Adições  (−) Exclusões
(−) Compensação de prejuízo fiscal (limitada a 30% do lucro ajustado)
(=) Lucro Real = max(0, …)
IRPJ_LR = LR × 15% + max(0, LR − 20.000 × nº meses) × 10%
CSLL_LR = LR × 9%
Total_LR = Σ ICMS_rec + Σ PISCOF_rec + IRPJ_LR + CSLL_LR  (+ INSS sobre folha, se informada)
```

Os créditos de ICMS e PIS/COFINS **não** são abatidos do CMV: CMV e despesas entram pelo valor integral e a receita é
deduzida só dos tributos a recolher (mesma convenção da planilha, `IRPJ e CSLL!A65`).

**Margem de equilíbrio LR × LP:** margem de LAIR (LAIR ÷ RL) em que `PISCOF_LR + IRPJ_LR + CSLL_LR = PISCOF_LP +
IRPJ_LP + CSLL_LP`, obtida por busca numérica (bissecção) sobre o LAIR, com ICMS igual nos dois regimes.

### 5.6 Comparativo

```
Carga_regime      = estadual (ICMS) + federal (PIS, COFINS, IRPJ, CSLL; CPP no Simples)
Aliq_efetiva      = Carga_regime / RL
Diferença         = Carga_regime − min(Cargas)
Melhor regime     = argmin(Cargas)   (empate: manter o regime atual)
```

### 5.7 Reforma Tributária (por ano `a` de 2027 a 2033)

```
CBS_a, IBS_a, fICMS_a  ← reforma_cronograma
Base_cred_IBS = Compras × %compras_creditaveis + Σ despesas com credito_ibs_cbs = Sim

Simples_a = RL × Aef                    (premissa da planilha: DAS constante, sem segregação de monofásico)
LP_a      = Σ ICMS_rec × fICMS_a + (CBS_a + IBS_a) × (RL − Base_cred_IBS) + IRPJ_LP + CSLL_LP
LR_a      = Σ ICMS_rec × fICMS_a + (CBS_a + IBS_a) × (RL − Base_cred_IBS) + IRPJ_LR + CSLL_LR
```

A análise item a item da Reforma (colunas AI:AQ das abas mensais) usa o ano-base selecionado nas premissas:
`CBS_item = RL_item × CBS_a`, `IBS_item = RL_item × IBS_a`, `IBS_no_DAS_item = RL_item × Aef × %ICMS × (1 − fICMS_a)`.

### 5.8 Simulação de crescimento

Para cada RBT12 da lista: `Aef(RBT12)` pela tabela do Simples; LP e LR com as alíquotas efetivas atuais (linear, como
na planilha). Melhoria prevista: recalcular LP e LR escalando a operação (receita, compras e despesas proporcionais),
o que capta o adicional de IRPJ e o acréscimo da LC 224/2025.

---

## 6. Mapeamento das planilhas para o sistema

| Elemento da planilha | Onde fica no sistema |
|---|---|
| `DESPESAS SIMULAÇÃO TRIBUTÁRIA` (abas mensais) | `levantamento`, `levantamento_item`, `outra_despesa` (doc. original) |
| Abas `06-2026`, `07-2026`, `08-2026` – colunas A:P (identificação) | `nota_fiscal`, `nota_item` |
| Abas mensais – colunas Q:AQ (cálculos por linha) | calculadas pelo motor, gravadas em `simulacao_item` (não digitadas) |
| `Premissas` seção 2 (Anexo I) | `simples_faixa` |
| `Premissas` seção 3 (Reforma) | `reforma_cronograma` |
| `Premissas` seções 4–6 (parâmetros) | `parametro_tributario` + `premissa_planejamento` |
| `Premissas` seção 7 (CFOP × CST) | `cfop_regra` |
| `Premissas` seção 8 / `Verificação por NCM` | `ncm_regra` |
| `Premissas` seção 9 (compras) | `compra_mensal` (ou `nota_fiscal` de entrada) |
| `Premissas` seção 10 (origem das compras) | `compra_origem` |
| `Premissas` seção 11 (devoluções) | `devolucao_mensal` |
| `IRPJ e CSLL` seção 1 (despesas) + colunas F:I | `levantamento_item` + classificação em `item_despesa` |
| `IRPJ e CSLL` seções 2–3 | `simulacao_resultado` + `memoria_calculo` |
| `IRPJ e CSLL` seção 4 (despesas não informadas) | regra de oportunidade nº 9 |
| `Memória dos Créditos` | `memoria_calculo` |
| `Comparativo 3 Regimes` | `simulacao_resultado` (tela e PDF) |
| `Matriz por Produto` | consulta agregada sobre `simulacao_item` |
| `Resumo Executivo` | relatório PDF + `oportunidade` + texto de recomendação |
| a planilha inicial de planejamento (versão inicial) | substituída; ver inconsistências na seção 10 |

---

## 7. Dicionário de dados (resumo)

Tabelas do documento original mantidas: `usuario`, `empresa`, `importacao_empresa`, `grupo_despesa`, `item_despesa`,
`levantamento`, `levantamento_item`, `levantamento_grupo`, `outra_despesa`, `bem`, `tipo_documento`, `documento`,
`historico_status`, `relatorio_pdf`, `peso_progresso`.

Alterações e tabelas novas:

| Tabela | Campos principais | Restrições |
|---|---|---|
| `empresa` (+) | uf, cnae, atividade, regime_atual, anexo_simples | uf IN (27 UFs); atividade IN (COMERCIO, INDUSTRIA, SERVICO) |
| `item_despesa` (+) | dedutivel_irpj_csll, credito_pis_cofins, credito_ibs_cbs, natureza | enums |
| `planejamento` (+) | status, sem_bens, simulacao_atual_id | UNIQUE (empresa_id, competencia_inicial) |
| `premissa_planejamento` | planejamento_id, chave, valor, alterado_por, alterado_em | UNIQUE (planejamento_id, chave) |
| `importacao_nfe` | id, planejamento_id, tipo (SAIDA, ENTRADA), origem (XML, RELATORIO), arquivo, status, lidos, importados, ignorados, log | — |
| `nota_fiscal` | id, planejamento_id, importacao_id, chave_acesso, numero, data_emissao, tipo, uf_emitente, uf_destinatario | UNIQUE (planejamento_id, chave_acesso) |
| `nota_item` | id, nota_fiscal_id, n_item, cod_produto, descricao, ncm, cfop, quantidade, vl_unitario, vl_produtos, vl_total, vl_icms_destacado | UNIQUE (nota_fiscal_id, n_item); NUMERIC(14,2) |
| `faturamento_manual` | planejamento_id, competencia, ambito, monofasico, valor | modo simplificado |
| `devolucao_mensal` | planejamento_id, competencia, valor | valor ≥ 0 |
| `compra_mensal` | planejamento_id, competencia, valor | valor ≥ 0 |
| `compra_origem` | planejamento_id, origem, percentual | soma = 100 |
| `folha_mensal` | planejamento_id, competencia, folha, pro_labore | vazio = não informado |
| `estoque` | planejamento_id, estoque_inicial, estoque_final | opcional |
| `simples_faixa` | anexo, faixa, rbt12_de, rbt12_ate, aliq_nominal, parcela_deduzir, p_irpj, p_csll, p_cofins, p_pis, p_cpp, p_icms, p_iss, vigencia_inicio, vigencia_fim | soma das repartições = 100% |
| `parametro_tributario` | chave, valor, descricao, fundamento, vigencia_inicio, vigencia_fim | UNIQUE (chave, vigencia_inicio) |
| `reforma_cronograma` | ano, cbs, ibs, fator_icms, situacao | UNIQUE (ano) |
| `icms_aliquota` | uf_origem, uf_destino, ncm (opcional), aliquota, vigencia_inicio | — |
| `cfop_regra` | cfop, natureza, gera_receita, csosn_simples, cst_piscof_simples, cst_icms_normal, cst_piscof_normal, cst_ibs_cbs, cclass_trib | cfop único |
| `ncm_regra` | ncm, monofasico, confianca, fundamento, sujeito_st, cest, indicio_ncm_incorreto, observacao, acao_recomendada, aprovado_por, aprovado_em | ncm único (8 dígitos) |
| `simulacao` | id, planejamento_id, versao, tipo (PRELIMINAR, FINAL), hash_entrada, versao_tabelas, premissas_json, executada_por, executada_em, desatualizada, aprovada_por, aprovada_em | UNIQUE (planejamento_id, versao) |
| `simulacao_resultado` | simulacao_id, regime, ano, competencia (nula = trimestre), tributo, valor | NUMERIC(14,2) |
| `simulacao_item` | simulacao_id, nota_item_id, receita_liquida, monofasico, ambito, csts, icms_sn, pis_sn, cofins_sn, base_icms, icms_debito, pis_lp, cofins_lp, pis_lr, cofins_lr, cbs, ibs | gerada pelo motor |
| `memoria_calculo` | simulacao_id, ordem, secao, descricao, formula, entradas_json, resultado, fundamento | somente leitura |
| `oportunidade_regra` | codigo, titulo, condicao, formula_impacto, prioridade, texto_acao, ativa | codigo único |
| `oportunidade` | simulacao_id, regra_codigo, impacto, prioridade, situacao (ABERTA, CONFIRMADA, DESCARTADA), motivo | — |
| `fonte_legal` | id, sigla, descricao | — |

---

## 8. API REST (principais rotas)

| Recurso | Rotas |
|---|---|
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Empresas | `GET/POST /empresas`, `PUT /empresas/{id}`, `POST /empresas/importacao/previa`, `POST /empresas/importacao/confirmar` |
| Planejamentos | `GET/POST /planejamentos`, `GET /planejamentos/{id}`, `POST /planejamentos/{id}/status`, `GET /planejamentos/{id}/pendencias`, `GET /planejamentos/{id}/progresso` |
| Coleta | `/planejamentos/{id}/levantamentos/...` (doc. original), `PUT /planejamentos/{id}/compras`, `PUT /planejamentos/{id}/devolucoes`, `PUT /planejamentos/{id}/folha`, `PUT /planejamentos/{id}/estoque`, `PUT /planejamentos/{id}/premissas` |
| NF-e | `POST /planejamentos/{id}/nfe` (upload; retorna id da importação), `GET /importacoes-nfe/{id}`, `GET /planejamentos/{id}/nfe/itens?filtros` |
| Tabelas legais | `/tabelas/simples-faixas`, `/tabelas/parametros`, `/tabelas/reforma`, `/tabelas/icms`, `/tabelas/cfop`, `/tabelas/ncm` (GET para todos; escrita só contador) |
| Motor | `POST /planejamentos/{id}/simulacoes`, `GET /simulacoes/{id}`, `GET /simulacoes/{id}/comparativo`, `GET /simulacoes/{id}/reforma`, `GET /simulacoes/{id}/memoria`, `GET /simulacoes/{id}/matriz-produto`, `GET /simulacoes/{id}/crescimento?rbt12=...`, `POST /simulacoes/{id}/aprovar` |
| Oportunidades | `GET /simulacoes/{id}/oportunidades`, `PATCH /oportunidades/{id}` |
| Saídas | `POST /simulacoes/{id}/relatorio-pdf`, `GET /relatorios/{id}/download`, `GET /simulacoes/{id}/excel` |
| Dashboard | `GET /dashboard` |

Erros padronizados: código HTTP + `{ "erro": "...", "campos": { "campo": "mensagem" } }`.

---

## 9. Caso de referência (testes de aceitação)

O planejamento do **cliente de referência (comércio de autopeças), jun a ago/2026,** é carregado como dado de demonstração e vira teste automatizado.
O motor deve reproduzir os valores abaixo (tolerância de R$ 0,01 nos totais):

**Entradas:** faturamento bruto 202.771,78 / 249.228,28 / 231.668,34; devoluções 9.915,07 / 11.535,67 / 11.632,02;
compras 106.485,13 / 92.957,60 / 90.172,60; despesas da aba `IRPJ e CSLL` (72.512,31 / 90.347,07 / 86.388,42);
composição das compras 100% interna a 18%; ST = Não; Tema 69 = Não; crédito de frete = Proporcional; folha e
pró-labore = 0.

| Indicador | Esperado |
|---|---|
| Receita líquida do trimestre | 650.585,64 |
| Receita monofásica / não monofásica | 443.287,43 / 207.298,21 |
| RBT12 estimado · faixa · alíquota efetiva | 2.602.342,56 · 5ª · 10,9453% |
| **Simples** — ICMS / PIS+COFINS / IRPJ+CSLL / CPP | 23.854,93 / 3.516,87 / 6.408,79 / 29.907,67 |
| **Simples — total (alíq. efetiva)** | **63.688,26 (9,79%)** |
| ICMS débito / crédito / a recolher | 89.496,87 / 52.130,76 / 37.366,11 |
| **LP** — PIS+COFINS / IRPJ / CSLL | 7.566,38 / 7.807,03 / 7.026,32 |
| **LP — total (alíq. efetiva)** | **59.765,84 (9,19%)** |
| **LR** — PIS/COFINS débitos / créditos / a recolher | 19.175,08 / 12.288,64 / 6.886,45 |
| LR — LAIR / IRPJ / CSLL | 67.469,96 / 10.867,49 / 6.072,30 |
| **LR — total (alíq. efetiva)** | **61.192,34 (9,41%)** |
| Melhor regime 2026 | Lucro Presumido |
| 2027 — SN / LP / LR | 71.208,75 / 62.031,04 / 64.137,47 |
| 2033 — SN / LP / LR | 71.208,75 / 44.439,82 / 46.546,25 |
| Oportunidade 1 (CPP) / 2 (monofásico) / 3 (ST) | 29.907,67 / 7.520,49 / 6.982,95 |

---

## 10. Inconsistências encontradas nas planilhas (corrigidas no sistema)

Comparando a planilha inicial de planejamento com a planilha final:

| # | Onde | Problema | Tratamento no sistema |
|---|---|---|---|
| 1 | Compras de agosto | **R$ 90.712,60** na planilha inicial × **R$ 90.172,60** na final (diferença de R$ 540,00, provável inversão de dígitos) | Confirmar com o cliente; o valor vem de um único cadastro |
| 2 | Inicial – `RESULTADO PLANEJAMENTO!C6` | Simples com alíquota fixa de 9,58% sobre o faturamento, sem tabela, repartição ou monofásico | Alíquota efetiva calculada pela tabela (5.2) |
| 3 | Inicial – `LUCRO PRE!F6` | Adicional de IR **negativo** (−795,31) somado ao total do LP | `max(0, …)` em todo adicional |
| 4 | Inicial – `LUCRO REA!H12` e `E25` | CMV% = (compras + despesas) ÷ faturamento, e as despesas são subtraídas de novo → despesas contadas duas vezes, prejuízo artificial de −82 mil | DRE fiscal (5.5) |
| 5 | Inicial – `APURAÇÃO PIS COFINS` | PIS/COFINS sobre 100% da receita, ignorando os monofásicos; crédito do LR sobre 100% das compras | Base apenas de itens CST 01; crédito proporcional |
| 6 | Inicial – `APURAÇÃO PIS COFINS` | Títulos "04/2026, 05/2026, 06/2026" sobre dados de 06 a 08/2026 | Competência vem do dado, não de texto |
| 7 | Inicial – `APURAÇÃO ICMS` | Abas vazias e valores digitados em fórmula (`=59623.8*18%`) | ICMS calculado por item |
| 8 | Inicial – despesas de junho | Tarifas do marketplace estimadas por % do faturamento (17,9915%, 9,6191%, 0,4557%) | Usar o valor real do relatório do marketplace; % só como estimativa marcada |
| 9 | Final – RBT12 | Estimado pela média do trimestre × 12 | Usar o RBT12 do PGDAS-D quando houver; aviso automático quando estimado |
| 10 | Final – ICMS a recolher | Saldo credor mensal descartado | Transporte do saldo credor (5.3) |
| 11 | Final – Simples na Reforma | DAS constante de 2027 a 2033 | Mantido como premissa explícita e parametrizável |
| 12 | Final – LP/LR | INSS sobre folha fora da comparação (folha não informada) | Incluído automaticamente quando a folha é informada; senão, aviso |
| 13 | Final – `Premissas` A34:K35 | Faixas 3 e 4 do Anexo I com repartição CPP 41,5% / ICMS 34% (pela LC 123/2006 são 42% / 33,5%, como a faixa 5). Não afeta o caso de referência (faixa 5) | Carga inicial usa os percentuais da lei |
| 14 | Ambas – CNPJ | Validação só numérica; desde jul/2026 a Receita emite CNPJ alfanumérico | Validação aceita os dois formatos (dígito verificador por ASCII − 48) |

---

## 11. Requisitos Técnicos

Mantém a stack sugerida no documento original, com acréscimos:

| Camada | Tecnologia | Uso |
|---|---|---|
| Backend | Python 3.12 + FastAPI | API, importação, motor, PDF e Excel |
| ORM / migrations | SQLAlchemy 2 + Alembic | Modelos e carga das tabelas legais |
| Validação | Pydantic | Schemas de entrada e saída |
| Autenticação | JWT (PyJWT) + bcrypt | Login, perfis |
| Banco | PostgreSQL 16 | `NUMERIC` para valores monetários e alíquotas |
| Motor de cálculo | Python puro + `decimal.Decimal` | Funções puras, sem dependência de banco |
| Leitura de NF-e | `lxml` (XML NF-e 4.00) + openpyxl (relatório) | Importação de saídas e entradas |
| Processamento em segundo plano | `BackgroundTasks` do FastAPI (ou RQ/Celery + Redis se o volume exigir) | Importações grandes e simulações |
| PDF | ReportLab | Relatório final com marca d'água. Escolhido no lugar do WeasyPrint porque é Python puro: o WeasyPrint depende de GTK/Pango, ausentes no Windows, e o PDF precisa sair igual no desenvolvimento local e no Docker |
| Excel | openpyxl | Exportação no layout das planilhas, com fórmulas nas abas de resumo |
| Frontend | React + TypeScript + Vite, React Hook Form + Zod, TanStack Query + Axios, Tailwind | SPA |
| Gráficos | Recharts | Comparativo e evolução da Reforma |
| Testes | pytest (motor, regras, caso de referência), Vitest | — |
| Containers | Docker Compose | API, front, banco |

Camadas do backend: `rotas → serviços → motor (puro) / repositórios → modelos`. O motor recebe um objeto
`EntradaSimulacao` (dados + premissas + tabelas vigentes) e devolve `ResultadoSimulacao` (resultados + memória +
oportunidades), sem I/O.

### Identidade visual

Tema claro, pensado para longas sessões de digitação: base neutra (ardósia), uma única cor de ação (azul-petróleo)
e cores de status separadas. Cores definidas só como tokens (variáveis CSS / Tailwind), nunca fixas nos componentes.

| Token | Hex | Uso |
|---|---|---|
| `bg` | `#F5F7FA` | Fundo da aplicação (cards em branco por cima) |
| `surface` | `#E4E9EF` | Cabeçalho de tabela, faixas alternadas, borda de card |
| `border` | `#CBD2D9` | Borda de campos de digitação |
| `highlight` | `#E0EFF3` | Linha sob o mouse, campo em foco |
| `text` | `#1F2933` | Texto (14,3:1 sobre o fundo) |
| `text-muted` | `#52606D` | Texto de apoio (6,2:1) |
| `brand` | `#155E75` | Menu, links, botão principal com texto branco (7,4:1) |
| `success` / `-soft` / `-ink` | `#2F855A` / `#E6F4EC` / `#22543D` | Barra em 100%, melhor regime, selos Aprovado/Final/"Menor carga" |
| `warning` / `-soft` / `-ink` | `#B7791F` / `#FBEFD9` / `#744210` | Barra de 50% a 99%, simulação preliminar |
| `alert` | `#C53030` | Erros, pendências, barra de 0% a 49% |

Regras mantidas: status sempre com texto e ícone (nunca só cor), números tabulares nos valores, no comparativo o
**melhor regime** com borda `success` e o selo "Menor carga". Gráfico da Reforma: Simples em `alert`, Presumido em
`brand`, Real em `text-muted`. O Excel exportado usa `surface` no cabeçalho e `brand` nos títulos.

---

## 12. Critérios de Avaliação

| Critério | O que será observado |
|---|---|
| 1. Correção do cálculo | Caso de referência (seção 9) reproduzido; totais da tela = PDF = Excel |
| 2. Rastreabilidade | Toda cifra do relatório leva à memória de cálculo e às premissas; simulações antigas reproduzíveis |
| 3. Funcionamento | Fluxo completo: cadastro → coleta → importação → simulação → aprovação → PDF |
| 4. Organização do código | Motor isolado e testável; camadas; nomenclatura |
| 5. Boas práticas | Nenhuma alíquota fixa no código; validações no front e no back; segurança básica; upload restrito |
| 6. Frontend | Experiência de preenchimento, telas de comparativo legíveis, pendências com link direto |
| 7. Documentação | README, Memorial Técnico, dicionário de dados, descrição das fórmulas |

---

## 13. Memorial Técnico (obrigatório)

Mesmas seções do documento original (tecnologias, justificativa técnica, justificativa conceitual, análise crítica),
respondendo também a:

- por que o motor é um módulo puro separado do banco e como isso permite testar contra a planilha;
- como as tabelas legais são versionadas por vigência e como uma simulação antiga é reproduzida;
- como foi tratada a precisão decimal (onde arredonda e onde não arredonda);
- como o sistema lida com volume (17,6 mil itens em um trimestre; centenas de milhares por ano);
- quais premissas da planilha foram mantidas, quais foram corrigidas (seção 10) e por quê;
- limitações conhecidas: só comércio/Anexo I validado, DIFAL fora do escopo, ICMS-ST simplificado, Reforma com
  alíquotas projetadas.

**Melhorias futuras sugeridas:** importação da EFD ICMS/IPI e EFD-Contribuições; integração com o relatório de
tarifas do Mercado Livre e de outros marketplaces; consulta automática do RBT12 no PGDAS-D; demais anexos do Simples e
atividades de serviço (ISS); DIFAL; simulação de filial em outra UF (fulfillment); comparação de vários cenários lado
a lado; alerta automático quando a empresa se aproxima do sublimite.

---

## 14. Requisitos de Deploy

Iguais ao documento original (pré-requisitos, instalação, `.env.example` com `DATABASE_URL`, `JWT_SECRET`,
`UPLOAD_DIR`, `VITE_API_URL`, comandos de execução, usuários `contador/demo123` e `analista/demo123`,
`empresas_exemplo.xlsx`), mais:

- carga das tabelas legais vigentes e do planejamento de demonstração (caso de referência da seção 9) com um comando;
- pasta `exemplos/` com XML de NF-e anonimizados e um relatório de movimentação de exemplo para teste da importação.

> **Atenção:** os arquivos de exemplo do caso de referência devem ser **anonimizados** antes de entrar no repositório (CNPJ,
> razão social, chaves de acesso). Certificados digitais e senhas da pasta do cliente nunca devem ir para o
> repositório.

### Não obrigatórios

- CI/CD (lint + testes, incluindo o caso de referência);
- responsividade para tablet;
- importação das planilhas antigas de planejamento para popular o histórico;
- gráfico de evolução mensal das despesas e da carga tributária.
