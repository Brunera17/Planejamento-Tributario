# Histórico do Planejador Tributário

O que cada agente entregou, em ordem cronológica. Mantido pela sessão gerente ("Planejador automático de
tributação"): a cada merge ela acrescenta a entrega à seção do agente. As datas são as do horário de Brasília.

**Atenção à autoria:** até 09/11/2026 todos os commits saíram com o mesmo autor, `Bruno David Martins`, então a
divisão abaixo foi feita pela branch, pelo título e pelo que cada sessão informou. Onde ficou dedução, está
indicado. Daqui em diante cada commit termina com a linha `Sessão: <nome da sessão>` (ver `docs/ROADMAP.md`).

Números gerais em 09/11/2026: cerca de 110 commits na `main`, 45 PRs (24 do Dependabot, 12 deles mergeados), migrações
0001 a 0015.

## Planejador automático de tributação (hoje a gerente)

Construiu a aplicação inteira até 04/11, antes de passar a coordenar os outros agentes.

| Data | Entrega |
|---|---|
| 29/10 | Motor de cálculo (Simples, Presumido, Real, Reforma), API, telas e relatório PDF. |
| 30/10 | Importação do relatório contábil, exemplo completo, bens e documentos, fluxo completo pela tela, premissas e origem das compras, base legal do monofásico, revisão de produtos, cadastro de empresas e usuários. |
| 03/11 | Correção da importação de empresas e padronização da interface, premissas preenchidas pelas notas, cronograma da Reforma editável (CBS de 11,3% do TCU), apresentação em PowerPoint, data de cadastro das empresas, biblioteca de normas, ST de SP por NCM com vigência, crédito do estoque da ST, alíquota de 4% dos importados, DIFAL, testes com contas à mão. |
| 04/11 | Reduções de CBS e IBS por NCM (Anexos I, VII, VIII e XV da LC 214), Anexo II do Simples com sugestão pelo CNAE, leitura do extrato do PGDAS-D, encargos da folha por empresa (RAT, FAP e terceiros), redesenho da aba Premissas, `render.yaml` e `vercel.json`. Commit feito pela sessão de segurança e desempenho ao começar (`f59dbe7`, dedução). |
| 06/11 | Passou a gerente: roadmap (PR #35), regras, donos por área e rotina dos sinalizadores. Limpeza das branches remotas já mergeadas. |

## Gargalos e escalabilidade (desempenho e sinalizadora)

| Data | Entrega |
|---|---|
| 04/11 | Dentro do PR #1: memória por requisição, progresso sem consultas repetidas, limites de upload, agregação no banco, memória por NCM e índices das notas (migração 0014). |
| 06/11 | PR #4: importação de NF-e em lote e despesas salvas por mês. |
| 09/11 | PR #42, item 6: memória de cálculo fora do `resultado_json`. Sem migração, porque a memória guarda 8 casas e o motor gera até 10. JSON 38% menor nas simulações novas, que passam a ter 8 casas nos passos de cálculo. Aceito assim; ampliar a coluna fica registrado como possibilidade. Revisou também o #41. |

## Planejamento JWT com refresh e Redis (segurança e deploy)

| Data | Entrega |
|---|---|
| 04/11 | Dentro do PR #1: sessões com refresh em cookie HttpOnly, Redis, trilha de auditoria (migração 0013) e limite de tentativas de login. |
| 06/11 | PR #20: leitura do extrato do PGDAS-D gravada no envio (migração 0015). |
| 09/11 | PR #44, etapa 4: arquivos dos clientes cifrados (AES-256-GCM, marca `PTC1` centralizada, três comandos de chave) e a parte de segurança da especificação. Sem migração. |

## Planejamento de CI para aplicação (CI e dependências)

| Data | Entrega |
|---|---|
| 06/11 | PR #3: CI com testes, migrações no Postgres, build do frontend e imagens Docker. |
| 06/11 | PR #21: `alembic check` bloqueante e suíte do backend no Postgres. PR #22: correção de tipos do axios que deixou a `main` vermelha. |
| 06/11 | PRs #23 e #30: Dependabot sem versões principais no npm e um PR agrupado por mês. PR #31: pisos das dependências do backend, juntando 6 PRs soltos. |
| 06/11 | PR #36: testes no Postgres passam a bloquear (item 8). |
| 09/11 | PR #37: versões do backend travadas e CI verificando todo commit da `main` (item 9). PR #40: texto sobre o CI sem proteção de branch. Abriu a sessão de Migração do frontend. |

## Migração do frontend (tela)

| Data | Entrega |
|---|---|
| 06/11 | PR #24: React 19, TypeScript 7, Vite 8, Vitest 5 e plugin-react 6. |
| 09/11 | PR #38: abas recriadas ao trocar de planejamento (item 1), com teste. |

## Agente de bugs e sinalizações

| Data | Entrega |
|---|---|
| 04 a 09/11 | Revisões dos PRs #3, #4, #20, #21, #36, #37, #38, #39 e #40. Achou o rodapé colado no `st_sp.json` (erro da extração) e o cancelamento de runs da `main` no CI. |
| 09/11 | PR #41: texto da tabela de ST e `concurrency` do CI. |

## Sem autor identificado

PR #2 (04/11): capturas de tela da aplicação em funcionamento.

## Dependabot (não é agente)

24 PRs entre 06/11 e 09/11: 12 mergeados e 12 fechados e substituídos pelos PRs agrupados. Desde 06/11 abre um
PR por ecossistema, uma vez por mês.
