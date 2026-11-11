# Plano de execução: produção grátis (Vercel, Render, Neon e Google Drive)

Decidido em 11/11/2026. Custo previsto: **US$ 0 por mês**.

## Como fica

| Peça | Onde | Custo |
|---|---|---|
| Tela (React) | Vercel (sem mudança) | grátis |
| API (FastAPI, Docker) | Render, **plano grátis** | grátis |
| Banco | **Neon** (Postgres), plano grátis, 0,5 GB | grátis |
| Sessões (Redis) | Key Value do Render, plano grátis (sem mudança) | grátis |
| Arquivos | **Google Drive** da conta do escritório, cifrados | o espaço da conta |

**Por que não tudo no Vercel:** o plano grátis do Vercel não permite uso comercial (o Pro custa US$ 20 por mês) e limita cada envio a 4,5 MB. O Render grátis não tem nenhum dos dois problemas. Também não tem disco permanente, mas com os arquivos indo para o Drive a API não precisa de disco.

**O preço:** a API dorme depois de 15 minutos sem acesso, e o primeiro acesso depois disso leva cerca de 1 minuto.

**Conferir antes de publicar:** se os termos do plano grátis do Render permitem uso comercial.

## Fase 0: preparação (usuário)

1. **Neon:** criar a conta e o projeto (região São Paulo, se houver; senão, a mais próxima). Copiar a URL de conexão **direta**, a que não tem `-pooler` no endereço e termina em `sslmode=require`.
2. **Google Cloud**, na conta do Google que vai guardar os arquivos:
   1. Criar um projeto e ativar a **Google Drive API**.
   2. Na **tela de consentimento OAuth**, escolher o tipo "Externo" e adicionar o escopo `.../auth/drive.file`. Depois, **publicar o app como "Em produção"**. No modo "Teste", a autorização expira a cada 7 dias e os uploads param.
   3. Em **Credenciais**, criar um ID do cliente OAuth do tipo "App para computador" e copiar o ID e a chave secreta.
3. Gerar a chave dos arquivos: `python -m app.services.cripto --gerar-chave`.
4. No computador, com `DRIVE_CLIENT_ID` e `DRIVE_CLIENT_SECRET` no `backend/.env`, rodar:
   ```
   python -m app.services.armazenamento --autorizar
   ```
   - O navegador abre, você entra com a conta do Google e autoriza.
   - O comando cria a pasta `Planejador` no Drive, com as subpastas `documentos` e `relatorios`.
   - No fim, ele imprime o `DRIVE_REFRESH_TOKEN` e o `DRIVE_PASTA_ID`.
5. **Guardar no gerenciador de senhas:** `CHAVE_ARQUIVOS`, `DRIVE_CLIENT_ID`, `DRIVE_CLIENT_SECRET`, `DRIVE_REFRESH_TOKEN` e a URL do Neon. Perder a `CHAVE_ARQUIVOS` é perder todos os documentos.

## Fase 1: código (PR "Produção grátis")

- `services/armazenamento.py`: arquivos no disco ou no Drive, com a mesma interface, além dos comandos `--autorizar` e `--importar-pasta`.
- Documentos, relatórios e os comandos do `cripto` passam pelo armazenamento. A cifra não muda: o Drive só recebe arquivos já cifrados.
- `render.yaml` no plano grátis:
  - sem disco e sem o Postgres do Render;
  - um processo só (512 MB de memória);
  - `ARMAZENAMENTO=drive`.
- Testes do Drive contra um Drive falso, sem rede. A especificação foi atualizada.

Banco: o código não muda. Com a URL direta do Neon, a trava de linha da aprovação e a trava da auditoria funcionam como no Postgres do CI. Quando o Neon "dorme" (5 minutos sem uso), o `pool_pre_ping` descarta a conexão velha.

## Fase 2: publicar (usuário, com o passo a passo)

1. **Render:** New > Blueprint > este repositório. Preencher as variáveis marcadas com `sync: false`:
   - `DATABASE_URL`: a URL do Neon;
   - `CHAVE_ARQUIVOS`;
   - `DRIVE_*`;
   - `ADMIN_USUARIO`, `ADMIN_SENHA` e `ADMIN_NOME`;
   - `PROXIES_CONFIAVEIS`;
   - `CORS_ORIGINS`: vazio.
2. A API sobe e roda sozinha `alembic upgrade head` e a carga (tabelas legais e o primeiro usuário).
3. **Vercel:** conferir se o `frontend/vercel.json` aponta `/api` para a URL do Render. Hoje aponta para `https://planejador-api.onrender.com`; se o Render der outro nome, ajustar.
4. **Teste de aceite no endereço público:**
   1. Login.
   2. Cadastrar uma empresa.
   3. Importar um zip de NF-e real.
   4. Enviar um documento e baixá-lo de volta.
   5. Simular e aprovar.
   6. Gerar o PDF e baixá-lo.
   7. Abrir a pasta no Drive e ver que os arquivos estão lá, ilegíveis (cifrados).
   8. Na auditoria, conferir se o IP gravado é o seu, e não o do proxy.

## Fase 3: migração (só se já houver dados num Render pago)

1. `pg_dump` do banco antigo e `pg_restore` no Neon.
2. `python -m app.services.armazenamento --importar-pasta /data/uploads`, no shell do serviço antigo e com as variáveis `DRIVE_*`. Os arquivos sobem como estão, já cifrados. Repetir o comando não duplica nada.
3. Conferir se o número de documentos no banco bate com o número de arquivos no Drive, e só então desligar o serviço antigo.

## Riscos que ficam

- **Acesso ao Drive revogado ou token expirado:** os envios respondem 503. A correção é rodar `--autorizar` de novo e trocar o `DRIVE_REFRESH_TOKEN` no Render. Esse comando cria uma pasta nova: para continuar na pasta antiga, use o `DRIVE_PASTA_ID` antigo, desde que tenha sido criada pelo mesmo cliente OAuth.
- **Limites do Neon grátis:** acima de 0,5 GB ou de 100 horas de computação no mês, o banco para até o mês seguinte. Com a retenção (notas apagadas na aprovação), a medição deu de 7 a 11 MB por planejamento em andamento. Olhar o painel no primeiro mês.
- **Reinício do Render grátis:**
  - o disco local se perde. A contingência da auditoria (eventos que não gravaram no banco) fica só no log nesse caso;
  - todos os usuários são deslogados, porque o Key Value grátis não guarda nada (decisão D3 da segurança).
- **Primeiro acesso do dia:** cerca de 1 minuto. Se incomodar, o Render Starter custa US$ 7 por mês e não dorme. Mesmo assim, não precisa mais do disco pago.
