# Evidências — aplicação em funcionamento

Capturas da execução local (`uvicorn` + `npm run dev`, http://localhost:5173, SQLite) com a carga de demonstração
(`python -m app.seeds.carga --demo`), usando um navegador automatizado (Edge em modo headless) e o perfil **Contador**.
Desktop em 1440×900; celular em 390×844.

## Acesso e visão geral

| | |
|---|---|
| **01 — Login.** Tela de entrada com a proposta do sistema: comparar Simples, Presumido e Real. | **02 — Visão geral.** Economia estimada, recuperações de monofásico e ICMS-ST, empresas perto do sublimite, simulações desatualizadas e planejamentos por etapa. |
| ![Login](01-login.png) | ![Visão geral](02-visao-geral.png) |
| **03 — Planejamentos.** Empresa, regime atual, período, documentos resolvidos, progresso da coleta e situação. | **15 — Empresas.** Cadastro com CNPJ, regime, UF e representante; importação por planilha. |
| ![Planejamentos](03-planejamentos.png) | ![Empresas](15-empresas.png) |

## Coleta de dados

| | |
|---|---|
| **04 — Movimento mensal.** Faturamento vindo das notas de saída e compras, devoluções, folha e pró-labore por competência. | **05 — Levantamento de despesas.** Catálogo por competência com classificação tributária e confirmação de leitura das observações. |
| ![Movimento mensal](04-coleta-movimento-mensal.png) | ![Despesas](05-levantamento-de-despesas.png) |
| **06 — Documentos.** Situação de cada documento por competência: enviado ou "não se aplica" com justificativa. | **07 — Premissas do cálculo.** RBT12, estoques, origem das compras, encargos da folha, estoque com ST e opções tributárias. |
| ![Documentos](06-documentos.png) | ![Premissas](07-premissas-do-calculo.png) |
| **08 — Pendências.** Planejamento ainda em coleta: o que falta em cada bloco, com o peso de cada um no progresso. | **09 — Simulações.** Versões calculadas, menor carga e situação (aprovada, desatualizada). |
| ![Pendências](08-pendencias-em-coleta.png) | ![Simulações](09-simulacoes.png) |

## Resultado da simulação

| | |
|---|---|
| **10 — Comparativo.** Veredito, carga de cada regime com composição por tributo, alíquota efetiva e diferença para o menor; exportação para Excel, apresentação e relatório PDF. | **11 — Reforma Tributária.** Carga de cada regime ano a ano de 2026 a 2033 (CBS, IBS e ICMS mantido), com o regime de menor carga em cada ano. |
| ![Comparativo](10-resultado-comparativo.png) | ![Reforma](11-resultado-reforma-tributaria.png) |
| **12 — Oportunidades.** Impacto no período, prioridade, o que fazer e situação de cada oportunidade de economia ou recuperação. | **13 — Verificação por NCM.** Receita por NCM, tratamento de PIS/COFINS, confiança e ação recomendada. |
| ![Oportunidades](12-resultado-oportunidades.png) | ![NCM](13-resultado-verificacao-por-ncm.png) |
| **14 — Memória de cálculo.** Cada etapa com competência, fórmula, resultado e fundamento legal. | |
| ![Memória de cálculo](14-resultado-memoria-de-calculo.png) | |

## Base legal e usuários

| | |
|---|---|
| **16 — Base legal.** Lei 10.485/2002 (monofásico), substituição tributária, ICMS por UF, CFOP, Reforma e normas. | **17 — Usuários.** Perfis Contador e Analista, situação e edição; não há autocadastro. |
| ![Base legal](16-base-legal.png) | ![Usuários](17-usuarios.png) |

## Celular

| | |
|---|---|
| **18 — Visão geral no celular.** | **19 — Resultado no celular.** |
| ![Visão geral no celular](18-celular-visao-geral.png) | ![Resultado no celular](19-celular-resultado.png) |
