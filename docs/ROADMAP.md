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
- **Pasta de trabalho própria:** cada agente trabalha só numa pasta de trabalho (`git worktree`) dele, criada a
  partir da `main`, em local fora da pasta do projeto (por exemplo, `C:/dev/planejador-<área>` ou uma pasta
  temporária). A pasta principal do projeto fica sempre na `main`. Terminada a entrega, quem criou a pasta
  remove a pasta e a branch.
- **Quem fez o quê:** todos os commits saem com o mesmo autor, então cada commit termina com a linha
  `Sessão: <nome da sessão>`. O que cada agente entregou fica em `docs/HISTORICO.md`.
- **Dúvidas para o usuário:** os agentes não fazem perguntas ao usuário no próprio chat, porque o cartão de
  pergunta trava a sessão até alguém responder. Mande a dúvida à gerente por mensagem, com a pergunta, as opções
  e a sua recomendação. A gerente leva ao usuário, junta as dúvidas de vários agentes numa pergunta só quando der e
  devolve a resposta. Enquanto espera, o agente segue com o que não depende da resposta ou fica parado, sem
  bloquear a sessão.
- **Mensagens entre agentes:** cada mensagem acorda uma sessão e custa uma resposta inteira. Escreva à gerente só
  para: PR aberto (com o número), bloqueio, dúvida para o usuário, achado crítico (na hora) ou entrega concluída
  (numa mensagem só). Sem "recebido" nem "ciente": quem recebe uma instrução a cumpre. Detalhes em
  `docs/GERENTE.md`.
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
| 1 | Troca de planejamento mantém o estado da tela anterior: o motivo de devolução pode ir para o planejamento errado. Recriar as abas ao trocar de planejamento (`key={p.id}` no contêiner das abas de `frontend/src/pages/Planejamento.tsx`, tirando a do `<Despesas>`). Conferir Bens, Documentos, Premissas e Revisao. | Tela | Feito (#38, 09/11/2026) |
| 2 | Segurança, etapa 4: arquivos dos clientes cifrados. Inclui centralizar a marca `PTC1` (hoje em `pgdas.py`) em `cripto.py` e pôr na especificação o que os PRs #1 e #20 não registraram (sessões e refresh, auditoria, limite de login, PGDAS gravado no envio). | Segurança | Feito (#44, 09/11/2026). |
| 3 | Segurança, etapas 5 a 8: segundo fator obrigatório, escopo por empresa, fila de tarefas (6b: a tabela `tarefa` e a importação de NF-e, o relatório contábil, o PDF, o PPTX e o Excel passando pela fila), telas de gestão. Ver `docs/PLANO_Autenticacao_JWT_Refresh_Redis.md`. | Segurança | Aguarda o item 2 |
| 4 | Deploy (etapa 9): tela na Vercel, API no Render. Já existem `render.yaml`, `frontend/vercel.json` e a criação do primeiro usuário por `ADMIN_USUARIO`/`ADMIN_SENHA`. Avaliar a região dos dados (LGPD). Antes de subir, guardar uma cópia da `CHAVE_ARQUIVOS` fora do Render: se ela se perder, os documentos cifrados se perdem. | Segurança | Aguarda o item 3 e a escolha do usuário |
| 5 | Validar o leitor do extrato do PGDAS-D com um extrato real. | Bugs e revisão | Aguarda o arquivo do usuário |
| 6 | Tirar a memória de cálculo do `resultado_json` da simulação, que hoje é gravada duas vezes. Mexe no relatório, na apresentação e no Excel, e lê o dashboard (item 7): avisar a gerente antes. | Desempenho | Feito (#42, 09/11/2026): sem migração; a memória fica com 8 casas nas simulações novas. |
| 7 | Tela inicial e lista de planejamentos sem consultas repetidas (N+1), junto com o escopo por empresa. | Desempenho | Aguarda a etapa 6 da segurança |
| 8 | Tornar obrigatório o job de testes no Postgres, que já está verde na `main`: um PR que tira o `continue-on-error`. Depois, o usuário marca o job como obrigatório na proteção da `main`, no GitHub. | CI e dependências | Feito no código (PR #36). Sem proteção da `main`: o usuário não vai assinar o GitHub Pro. O merge depende de não aceitar PR vermelho; o deploy só sobe com o CI verde. |
| 9 | Travar as versões do backend: hoje o `requirements.txt` só tem pisos (`>=`), e o build do Docker instala o mais novo do dia, então uma versão nova pode quebrar o deploy sem passar pelo CI. Usar um lock (pip-compile ou uv) no Dockerfile, com o Dependabot atualizando o lock. Precisa estar pronto antes do deploy (item 4). No mesmo PR: o `concurrency` do CI passa a cancelar só os runs de PR (`cancel-in-progress: ${{ github.event_name == 'pull_request' }}`), para que cada commit da `main` seja verificado; hoje, com merges em sequência, um run intermediário é cancelado e esconde a quebra (caso dos PRs #13 e #14). | CI e dependências | Feito (#37, 09/11/2026) |

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
| 09/11/2026 | Sem GitHub Pro: a `main` não tem proteção de branch. Regra do processo: nenhum PR é aceito com o CI vermelho. A sessão de CI ajusta a especificação. |
| 09/11/2026 | Organização: pasta de trabalho própria por agente, linha `Sessão:` nos commits, `docs/HISTORICO.md` como histórico das entregas, limpeza de branches mergeadas pela gerente. |
| 09/11/2026 | Regra de mensagens para gastar menos: agentes escrevem à gerente só quando precisam de decisão ou ação, sem confirmações. A gerente passa para uma sessão nova com o briefing `docs/GERENTE.md`. |
| 09/11/2026 | Dúvidas dos agentes ao usuário passam pela gerente, para nenhuma sessão ficar travada num cartão de pergunta. A pasta de trabalho de cada agente fica fora da pasta do projeto. |
| 09/11/2026 | Item 6 aceito sem migração, com a memória das simulações novas em 8 casas decimais. A migração 0016 fica livre para a segurança. |
| 06/11/2026 | Liberados juntos os itens 1, 2, 6 e 9. Ordem de merge para quem mexe na especificação: 9, 1, 6 e 2; quem entra depois atualiza a branch com a `main` antes. O item 6 não muda o contrato da API usado pela tela. |
| 06/11/2026 | Tarefas em segundo plano têm um dono só: a área de segurança, na etapa 6b. A área de desempenho não repete esse trabalho. |
| 06/11/2026 | Deploy fica com a área de segurança, porque depende das etapas 4 a 8 para ir ao ar com dados de clientes. |
| 06/11/2026 | O cálculo do Simples usa o anexo do cadastro (Anexos I e II), com sugestão pelo CNAE e conferência pelo extrato do PGDAS-D. |
