# Roadmap do Planejador Tributário

Plano de trabalho dos agentes, com a área de cada um, a fila e as decisões. Mantido pela sessão gerente
("Planejador automático de tributação") junto com o usuário; toda mudança neste arquivo passa por PR.
Leia antes de começar qualquer trabalho.

## Como trabalhamos

- **Quem decide:** o usuário libera cada item. A gerente planeja, propõe rotas de solução e coordena, mas não
  corrige código; quem corrige são os agentes da área.
- **Um PR por entrega:** correções, ajustes de revisão e acompanhamentos da mesma entrega vão no mesmo PR enquanto
  ele estiver aberto. PR já mergeado? Um único PR novo com tudo o que faltou.
- **Entrega terminada** só quando:
  1. o CI do GitHub Actions está verde e o PR foi mergeado;
  2. não sobrou nada da entrega: branch, worktree, teste prometido ou correção combinada;
  3. dados de cliente protegidos: nenhum nome de cliente no repositório (`git grep`), nenhum `.pfx`, senha ou `.env`
     versionado;
  4. `docs/ESPECIFICACAO_Planejador_Tributario.md` atualizado com o que mudou.
- **Especificação:** cada área atualiza a parte dela em `docs/ESPECIFICACAO_Planejador_Tributario.md`, no PR da própria
  entrega. Como o arquivo é de todos, quem for editar avisa a gerente para não haver duas edições ao mesmo tempo.
- **Mesmo arquivo ou assunto:** a gerente define a ordem; um faz merge e o outro parte da `main` depois.
- **Pendência sem dono:** avise a gerente, que sugere o dono ao usuário. Ninguém começa sem ele liberar.
- **Prioridade:** bug que afeta resultado ou dado > segurança (dados de clientes, LGPD) > função nova > desempenho.
- **Commit e push:** só quando o usuário pedir.

## Áreas

| Área | Dono |
|---|---|
| Tela (React) | Migração do frontend: React 19, TS 7, vite/vitest |
| Segurança e deploy | Planejamento JWT com refresh e Redis |
| Desempenho | Gargalos e escalabilidade |
| CI e dependências | Planejamento de CI para aplicação |
| Bugs e revisão | Agente de bugs e sinalizações |

Os nomes são os das sessões, que servem de endereço para mensagens. Relatório PDF, apresentação PPTX e exportação
Excel não têm área fixa: quem precisar mexer neles avisa a gerente antes.

## Rotina dos sinalizadores

As áreas de **Bugs e revisão** e de **Desempenho** são transversais: avaliam o projeto todo, cada uma pela sua
ótica, e consertam pontos específicos. As outras áreas são construtoras: entregam a fila e são donas dos arquivos.

1. **Quando avaliar:** a cada PR mergeado na `main`, as duas revisam o que mudou. Não há rotina agendada; uma
   varredura geral só quando o usuário pedir.
2. **O que fazer com o achado:**
   - PR da entrega ainda aberto: comentário no PR, e o dono da área corrige no mesmo PR.
   - PR já mergeado e conserto pequeno (um ou dois arquivos, sem migração, sem mudar a API e sem mudança visível na
     tela): o sinalizador corrige.
   - Conserto maior: vira item da fila, com o dono da área.
3. **Urgência:**
   - Crítico (cálculo errado, dado de cliente exposto, falha de segurança): para a fila e avisa o usuário na hora,
     pela gerente.
   - Médio: entra no topo da fila da área.
   - Baixo: fica em "Registrado, sem urgência".
4. **Revisão cruzada:** o conserto feito por um sinalizador é revisado pelo dono da área do arquivo, ou pelo outro
   sinalizador quando a área não tiver dono. Quem achou não é o único a conferir.
5. **Um PR por rodada:** os consertos pequenos de uma mesma avaliação vão num único PR, "Correções após o PR #X".
6. **Mesmo arquivo:** se os dois sinalizadores forem mexer no mesmo arquivo, a gerente define a ordem.
7. **Trabalho planejado primeiro:** quando a área de Desempenho estiver com um item da fila (6 ou 7), a avaliação
   de desempenho dos merges espera, porque a prioridade é bug > segurança > função > desempenho.

## Fila

Ordem de execução. "Aguarda" significa que espera o usuário liberar ou outro item terminar.

| # | Item | Área | Situação |
|---|---|---|---|
| 1 | Troca de planejamento mantém o estado da tela anterior: o motivo de devolução pode ir para o planejamento errado. Recriar as abas ao trocar de planejamento (`key={p.id}` no contêiner das abas de `frontend/src/pages/Planejamento.tsx`, tirando a do `<Despesas>`). Conferir Bens, Documentos, Premissas e Revisao. | Tela | Aguarda liberação |
| 2 | Segurança, etapa 4: arquivos dos clientes cifrados. Inclui centralizar a marca `PTC1` (hoje em `pgdas.py`) em `cripto.py` e pôr na especificação o que os PRs #1 e #20 não registraram (sessões e refresh, auditoria, limite de login, PGDAS gravado no envio). | Segurança | Aguarda liberação |
| 3 | Segurança, etapas 5 a 8: segundo fator obrigatório, escopo por empresa, fila de tarefas (6b: a tabela `tarefa` e a importação de NF-e, o relatório contábil, o PDF, o PPTX e o Excel passando pela fila), telas de gestão. Ver `docs/PLANO_Autenticacao_JWT_Refresh_Redis.md`. | Segurança | Aguarda o item 2 |
| 4 | Deploy (etapa 9): tela na Vercel, API no Render. Já existem `render.yaml`, `frontend/vercel.json` e a criação do primeiro usuário por `ADMIN_USUARIO`/`ADMIN_SENHA`. Avaliar a região dos dados (LGPD). | Segurança | Aguarda o item 3 e a escolha do usuário |
| 5 | Validar o leitor do extrato do PGDAS-D com um extrato real. | Bugs e revisão | Aguarda o arquivo do usuário |
| 6 | Tirar a memória de cálculo do `resultado_json` da simulação, que hoje é gravada duas vezes. Mexe no relatório, na apresentação e no Excel, e lê o dashboard (item 7): avisar a gerente antes. | Desempenho | Aguarda liberação |
| 7 | Tela inicial e lista de planejamentos sem consultas repetidas (N+1), junto com o escopo por empresa. | Desempenho | Aguarda a etapa 6 da segurança |
| 8 | Tornar obrigatório o job de testes no Postgres, que já está verde na `main`: um PR que tira o `continue-on-error`. Depois, o usuário marca o job como obrigatório na proteção da `main`, no GitHub. | CI e dependências | Em andamento (liberado em 06/11/2026) |

## Registrado, sem urgência

- Despesas: um salvamento antigo pode chegar depois do mais novo e sobrescrevê-lo, num caso raro. Só se resolve
  com versão por item no servidor (PR #4).
- O registro de auditoria do Postgres (migração 0013) não tem teste: o `create_all` da suíte não cria o trigger.
- A tela carrega um arquivo de cerca de 877 kB; dá para dividir por página com `import()` nas rotas.
- Simples Nacional, etapa 2: serviços (Anexos III a V, Fator R, ISS e NFS-e), quando o escritório atender
  serviços.
- IPI no Lucro Presumido e no Lucro Real, para a indústria.

## Decisões

| Data | Decisão |
|---|---|
| 06/11/2026 | Um PR por entrega; o Dependabot abre um PR agrupado por mês por ecossistema. |
| 06/11/2026 | Donos por área fixa; prioridade bug > segurança > função > desempenho. |
| 06/11/2026 | Bugs e Desempenho são sinalizadores: avaliam cada merge e consertam pontos pequenos, com revisão cruzada (seção "Rotina dos sinalizadores"). |
| 06/11/2026 | Tarefas em segundo plano têm um dono só: a área de segurança, na etapa 6b. A área de desempenho não repete esse trabalho. |
| 06/11/2026 | Deploy fica com a área de segurança, porque depende das etapas 4 a 8 para ir ao ar com dados de clientes. |
| 06/11/2026 | O cálculo do Simples usa o anexo do cadastro (Anexos I e II), com sugestão pelo CNAE e conferência pelo extrato do PGDAS-D. |
