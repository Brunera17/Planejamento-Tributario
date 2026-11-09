# Plano de segurança — sessões, MFA, auditoria, escopo por empresa e criptografia

> Status: **aprovado, incluindo a seção 8 e a fila no Postgres (8.1)** (nada implementado). Revisão 6 — 04/11/2026.
> Todas as recomendações da seção 6 foram aceitas pelo usuário em 04/11/2026. A seção 8 incorpora os 11 achados da sessão "Gargalos e escalabilidade" (conferidos no código).
> Objetivo: proteger os dados e documentos das empresas clientes com sessões revogáveis, segundo fator, rastro de quem acessou o quê, acesso restrito por carteira e arquivos cifrados no disco.

**Decisões já tomadas**

| | Decisão | Consequência no plano |
|---|---|---|
| D1 | **Domínio próprio com proxy**: `https://planejamento-tributario.domingosassessoria.com.br` | Tela na Vercel nesse endereço; `/api/*` repassado pela Vercel ao Render. Tudo na **mesma origem**: cookie `SameSite=Strict`, sem CORS no navegador (ver 1.8) |
| D2 | **Expiração absoluta** | Sessão vale **12 h a partir do login**, sem expiração por inatividade (ver nota em 1.2) |
| D3 | **Redis gratuito** | Sem persistência: reinício do Redis desloga todos e zera os contadores de tentativas — aceito |
| D4 | **MFA agora** | Parte 2 deste plano |
| E2 | **Analistas veem todas as empresas por enquanto** | Escopo por carteira fica construído e **desligado** (`ESCOPO_POR_EMPRESA=false`) — Parte 4 |

**Sumário**
1. [Sessões: JWT + refresh + Redis](#parte-1--sessões-jwt--refresh--redis)
2. [MFA (TOTP)](#parte-2--mfa-totp)
3. [Trilha de auditoria](#parte-3--trilha-de-auditoria)
4. [Escopo por empresa (carteira)](#parte-4--escopo-por-empresa-carteira)
5. [Criptografia dos arquivos em repouso](#parte-5--criptografia-dos-arquivos-em-repouso)
6. [Decisões pendentes](#6-decisões-pendentes)
7. [Ordem de execução](#7-ordem-de-execução)
8. [Ajustes de desempenho (análise de gargalos)](#8-ajustes-de-desempenho-análise-de-gargalos)

---

## Como está hoje

| Ponto | Situação atual | Risco |
|---|---|---|
| Token | JWT HS256 único, válido por **8 h** — [seguranca.py](../backend/app/core/seguranca.py) | Token vazado vale o expediente inteiro |
| Armazenamento | `localStorage` — [cliente.ts](../frontend/src/api/cliente.ts) | Qualquer XSS lê o token |
| Logout | Não faz nada no servidor — [auth.py](../backend/app/api/routes/auth.py) | Token continua válido após "Sair" |
| Revogação | Só desativando o usuário — [deps.py](../backend/app/api/deps.py) | Troca de senha não derruba sessões |
| Login | Sem limite de tentativas; usuário inexistente responde mais rápido | Força bruta e descoberta de logins |
| Segundo fator | Não existe | Senha vazada basta |
| Auditoria | Só `HistoricoStatus` (mudança de status do planejamento) e `gerado_por` do relatório | Ninguém sabe quem baixou o quê |
| Autorização | Rotas só pedem `UsuarioAtual`/`Contador`; **48 pontos** buscam planejamento/simulação por id sem checar empresa | Analista vê qualquer empresa digitando o id |
| Arquivos | `uploads/documentos` e `uploads/relatorios` em texto puro — [documentos.py](../backend/app/services/documentos.py), [relatorio_pdf.py](../backend/app/services/relatorio_pdf.py) | Snapshot/backup do disco expõe os documentos |

Fica como está: bcrypt, segredo ≥ 32 caracteres obrigatório em produção, downloads via `baixarArquivo` (axios), checagem de usuário ativo, validação de assinatura dos arquivos enviados, hash SHA-256 dos relatórios PDF.

---

## Parte 1 — Sessões: JWT + refresh + Redis

### 1.1 Fluxo

```
 navegador ── https://planejamento-tributario.domingosassessoria.com.br/api/* ── (proxy Vercel) ──▶ Render

 Tela                                        API                                Redis
 POST /auth/login {usuario, senha} ───────▶  limite de tentativas ───────────▶ login_falhas:*
                                             bcrypt (tempo constante)
                     (MFA ativo? ver Parte 2: devolve desafio em vez de sessão)
                                             cria sessão (sid) ───────────────▶ sessao:{sid}
 ◀── body: { access, expira_em, usuario }    cria refresh opaco ──────────────▶ refresh:{hash}
 ◀── Set-Cookie: __Secure-rt=…; HttpOnly; Secure; SameSite=Strict; Path=/api/auth

 GET /empresas  Authorization: Bearer access ▶ JWT válido + sessao:{sid} existe? (1 GET)

 401 ──▶ POST /auth/refresh (cookie) ──────▶ consome refresh (Lua atômico) ───▶ rotaciona
 ◀── novo access + novo cookie               refresh já consumido? ───────────▶ derruba a sessão

 POST /auth/logout ─────────────────────────▶ apaga sessão e refresh ─────────▶ access morre na hora
```

### 1.2 Tokens

**Access (JWT)** — 15 min, HS256 (PyJWT, já instalado). Claims `sub`, `perfil`, `sid`, `jti`, `iat`, `exp`, `iss="planejador-api"`, `aud="planejador-web"`, `typ="access"`; cabeçalho `kid` para rotação do segredo (`JWT_SECRET` + `JWT_SECRET_ANTERIOR`). Vai no corpo da resposta e fica **só em memória** no front.

**Refresh (opaco)** — 256 bits (`secrets.token_urlsafe(32)`); no Redis vai só o SHA-256.
- Cookie `__Secure-rt`: `HttpOnly; Secure; SameSite=Strict; Path=/api/auth`, **sem `Domain`** (fica preso a `planejamento-tributario.domingosassessoria.com.br`; o domínio-pai e os outros subdomínios da Domingos Assessoria não recebem o cookie).
- Rotação a cada uso; reuso de token consumido derruba a sessão; tolerância de ~20 s para corrida entre abas.
- **Expiração absoluta de 12 h (D2)**: o TTL de todas as chaves da sessão é a hora fixa de fim; renovar não estende.

> **Nota sobre D2**: sem expiração por inatividade, um computador deixado aberto continua logado até completar as 12 h. Proponho uma mitigação só no front, sem custo: **bloqueio de tela após 30 min sem interação** (pede a senha de novo, ou só o código MFA). Incluo? (decisão S1 na seção 6)

### 1.3 Chaves no Redis

| Chave | Conteúdo | TTL |
|---|---|---|
| `sessao:{sid}` | hash: `usuario_id`, `criada_em`, `expira_em`, `ip`, `user_agent`, `refresh_atual`, `nivel` (`senha`/`mfa`) | até `expira_em` |
| `refresh:{sha256}` | `sid` | até `expira_em` |
| `refresh_usado:{sha256}` | `sid` + instante do uso | até `expira_em` |
| `usuario_sessoes:{usuario_id}` | set de `sid` | 12 h |
| `login_falhas:usuario:{login}` / `login_falhas:ip:{ip}` | contador | 15 min |
| `mfa_falhas:{usuario_id}` | contador | 15 min |
| `totp_usado:{usuario_id}:{passo}` | marca de código já usado (anti-replay) | 90 s |

Configuração: `maxmemory-policy noeviction`. No plano gratuito do Render o limite de memória é pequeno, mas cada sessão ocupa < 1 KB — sobra com folga.

### 1.4 Revogação
- **Logout**: apaga sessão, refresh e cookie.
- **Sair de todos os dispositivos**: apaga todas as sessões de `usuario_sessoes:{id}`.
- **Troca de senha, desativação, mudança de perfil, mudança de carteira, reset de MFA**: derruba as sessões do usuário afetado.

### 1.5 Proteção do login
- **5 falhas por login / 20 por IP em 15 min** → `429` com `Retry-After`.
- Mensagem genérica; **tempo constante** (bcrypt contra hash fictício quando o login não existe).
- IP real: com o proxy, a requisição passa por **navegador → Vercel → Render**, e o `X-Forwarded-For` chega com mais de um endereço. O IP do cliente é o primeiro que não pertence a um proxy confiável, contando da direita (`PROXIES_CONFIAVEIS` = saltos do Render e da Vercel). Hoje o [Dockerfile](../backend/Dockerfile) sobe o Uvicorn com `--forwarded-allow-ips='*'`, o que faz o Uvicorn aceitar `X-Forwarded-For` de **qualquer origem** — quem chamar `planejador-api.onrender.com` direto forja o IP e escapa do limite por IP. Trocar por resolução própria do IP (ignorando `request.client.host` reescrito) com a lista de proxies confiáveis. **Conferir no primeiro deploy** registrando os cabeçalhos recebidos — o limite de tentativas e a auditoria dependem disso; se errar, todo mundo aparece com o IP da Vercel e o limite por IP bloqueia o escritório inteiro.

### 1.6 CSRF e CORS
- Rotas de dados usam `Authorization: Bearer` → imunes a CSRF.
- `/auth/refresh` e `/auth/logout`: `SameSite=Strict` + `Origin` conferido contra `https://planejamento-tributario.domingosassessoria.com.br` + cabeçalho obrigatório `X-Requested-With: planejador`.
- Com o proxy, tela e API ficam na **mesma origem**: o navegador não faz CORS e o cookie vai sem `withCredentials`. O `CORSMiddleware` de [main.py](../backend/app/main.py) fica só para desenvolvimento (`CORS_ORIGINS` vazio em produção) — assim nenhum outro site consegue chamar a API pelo navegador do usuário.

### 1.7 Falha do Redis
Falha fechada: sem Redis, autenticação responde `503`. `/api/saude` informa o Redis.
Cliente **síncrono** com `ConnectionPool`, `socket_timeout=0.5`, `socket_connect_timeout=0.5`, `retry_on_timeout=False` e disjuntor (após N falhas seguidas, responde 503 direto por 5 s) — um Redis lento não pode prender as threads da API (achado 3).

### 1.8 Domínio próprio e proxy (D1)

**Endereço**: `https://planejamento-tributario.domingosassessoria.com.br` — sempre **HTTPS** (o `http://` só redireciona). Cookie `Secure` e HSTS não funcionam em HTTP.

**DNS** (no provedor do `domingosassessoria.com.br`): `CNAME planejamento-tributario → cname.vercel-dns.com`; adicionar o domínio no projeto da Vercel (certificado automático). O Render não precisa de domínio próprio — a Vercel fala com `planejador-api.onrender.com` por trás.

**Proxy** em [vercel.json](../frontend/vercel.json) — a regra de `/api` precisa vir **antes** da regra que manda tudo para `index.html`:
```json
{
  "rewrites": [
    { "source": "/api/:caminho*", "destination": "https://planejador-api.onrender.com/api/:caminho*" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```
- Front: `VITE_API_URL=/api` (relativo). Local: `server.proxy` do Vite para `/api` → `http://localhost:8000` — mesmo comportamento de produção.
- API: `CORS_ORIGINS` vazio em produção; `ORIGEM_PUBLICA=https://planejamento-tributario.domingosassessoria.com.br` (usada na conferência de `Origin` e em links).

**Cabeçalhos** em `vercel.json`: `Content-Security-Policy` com `connect-src 'self'` (a API é a própria origem), `Strict-Transport-Security: max-age=31536000` (**sem** `includeSubDomains` — não cabe a este sistema forçar HTTPS nos outros subdomínios da Domingos Assessoria), `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`. Nas respostas de `/api`, `Cache-Control: no-store` vindo da API (a CDN da Vercel não pode guardar resposta com dado de empresa).

**Limites do proxy — testar antes de virar** (a documentação da Vercel não é clara para destinos externos):
| Item | Risco | Teste no deploy | Plano B |
|---|---|---|---|
| Tamanho do upload | Documentos vão até 10 MB; funções da Vercel limitam corpo a 4,5 MB e não há número publicado para rewrite externo | Enviar documento de 9–10 MB pela tela | Só o upload vai direto a um subdomínio da API (`api-planejamento-tributario…`, com CORS restrito à tela) |
| Tempo de resposta | Tempo máximo do proxy: 30 s numa página da Vercel, 120 s num anúncio mais recente; geração de PDF/apresentação e importação de ZIP de NF-e grandes | Gerar o maior relatório e importar o maior ZIP | Mesma rota direta, ou geração em segundo plano com aviso quando pronta |
| IP do cliente | Ver 1.5 | Conferir IP gravado na auditoria | Ajustar `PROXIES_CONFIAVEIS` |

**Endereço direto do Render**: `planejador-api.onrender.com` continua acessível. Sem CORS e com cookie preso ao domínio da tela, um navegador não consegue usar a sessão por ali; um token roubado funcionaria lá como em qualquer lugar — a defesa é a mesma (15 min, sessão revogável). Desligar o `*.vercel.app` do projeto (ou redirecionar para o domínio próprio).

---

## Parte 2 — MFA (TOTP)

### 2.1 Escolhas
- **TOTP (RFC 6238)**, 6 dígitos, passo de 30 s, tolerância de ±1 passo — funciona com Google Authenticator, Microsoft Authenticator, 1Password, Authy. Biblioteca `pyotp`.
- QR code gerado **no servidor** como SVG (`segno`, Python puro) — o segredo nunca passa por serviço externo de QR.
- Segredo TOTP gravado **cifrado** no banco com a mesma chave mestra da Parte 5.
- **10 códigos de recuperação** de uso único, mostrados uma única vez, gravados como **HMAC-SHA256** com segredo do servidor (são aleatórios de alta entropia; bcrypt custaria até ~2,5 s por tentativa comparando com 10 hashes — achado 8).
- Proposta: **obrigatório para todos os usuários** (decisão M1).

### 2.2 Fluxo de login com MFA
```
POST /auth/login {usuario, senha}
  ├─ MFA ativo     → 200 { mfa: "pendente", desafio: <JWT 5 min, typ=mfa_desafio> }   (sem sessão, sem cookie)
  │                  POST /auth/mfa {desafio, codigo}  → sessão completa (Parte 1), nivel=mfa
  └─ MFA não ativo → sessão com nivel=senha: só libera /auth/mfa/configurar e /auth/logout
                     (cadastro obrigatório no primeiro acesso; demais rotas → 403 "configure o segundo fator")
```
- `codigo` aceita TOTP **ou** código de recuperação.
- Anti-replay: o mesmo código TOTP não vale duas vezes (`totp_usado:*`).
- Limite: 5 erros de código por usuário em 15 min → desafio invalidado e `429`.

### 2.3 Rotas
| Rota | Quem | Faz |
|---|---|---|
| `POST /auth/mfa/configurar` | próprio usuário (nivel=senha ou mfa) | Gera segredo provisório (Redis, 10 min) e devolve SVG do QR + chave em texto |
| `POST /auth/mfa/confirmar` | próprio usuário | Confere um código, ativa o MFA, devolve os códigos de recuperação, eleva a sessão para nivel=mfa |
| `POST /auth/mfa` | anônimo com desafio | Segunda etapa do login |
| `POST /auth/mfa/recuperacao/regerar` | próprio usuário (exige código atual) | Invalida e gera novos 10 códigos |
| `POST /usuarios/{id}/mfa/resetar` | Contador | Desativa o MFA de outro usuário (que recadastra no próximo login) e derruba as sessões dele |
| `python -m app.seeds.carga --resetar-mfa <login>` | shell do Render | Saída de emergência se o único contador perder o celular e os códigos |

### 2.4 Banco (migração `0016`)
- `usuario`: + `mfa_segredo` (bytes, cifrado), `mfa_ativo` (bool, padrão falso), `mfa_ativado_em`.
- Nova tabela `codigo_recuperacao`: `id`, `usuario_id`, `hash`, `usado_em`.

### 2.5 Front
- `Login.tsx` vira duas etapas: senha → campo de 6 dígitos (`inputmode="numeric"`, `autocomplete="one-time-code"`) com link "usar código de recuperação".
- Nova tela **Configurar segundo fator**: QR, chave para digitar, campo de confirmação, exibição dos códigos de recuperação com botão de baixar `.txt` e checkbox "guardei os códigos".
- `Usuarios.tsx`: coluna "2º fator" (ativo/pendente) e ação "Resetar 2º fator".

---

## Parte 3 — Trilha de auditoria

### 3.1 O que registrar

| Grupo | Ações |
|---|---|
| Acesso | `LOGIN_OK`, `LOGIN_FALHA`, `LOGIN_BLOQUEADO`, `MFA_OK`, `MFA_FALHA`, `MFA_ATIVADO`, `MFA_RESETADO`, `RECUPERACAO_USADA`, `LOGOUT`, `LOGOUT_TODOS`, `REFRESH_REUSO` (suspeita de roubo), `SESSAO_EXPIRADA` |
| Usuários | `USUARIO_CRIADO`, `SENHA_ALTERADA`, `PERFIL_ALTERADO`, `USUARIO_DESATIVADO`, `CARTEIRA_ALTERADA` |
| Documentos | `DOCUMENTO_ENVIADO`, `DOCUMENTO_BAIXADO`, `DOCUMENTO_EXCLUIDO`, `NFE_IMPORTADA`, `RELATORIO_CONTABIL_IMPORTADO` |
| Saídas | `RELATORIO_GERADO`, `RELATORIO_BAIXADO`, `EXCEL_EXPORTADO`, `APRESENTACAO_EXPORTADA`, `REVISAO_EXPORTADA` |
| Leitura | `PLANEJAMENTO_ABERTO` (uma vez por sessão e planejamento, não a cada requisição — decisão A2) |
| Empresas | `EMPRESA_CRIADA`, `EMPRESA_EDITADA`, `EMPRESA_EXCLUIDA`, `EMPRESAS_IMPORTADAS` |
| Negações | `ACESSO_NEGADO` (tentativa de abrir planejamento/documento fora da carteira) |

### 3.2 Tabela `evento_auditoria` (migração `0013`)

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | bigint | |
| `momento` | timestamptz | servidor, UTC |
| `acao` | varchar(40) | lista acima |
| `resultado` | varchar(10) | `OK` / `FALHA` / `NEGADO` |
| `usuario_id` | int, nulo | nulo em login com usuário inexistente |
| `usuario_login` | varchar(60) | cópia do login no momento (sobrevive a renomeação/exclusão) |
| `sessao_id` | varchar(40), nulo | `sid` do Redis — liga todas as ações de uma sessão |
| `ip` | inet / varchar(45) | IPv4 ou IPv6 |
| `user_agent` | varchar(300) | truncado |
| `empresa_id` | int, nulo | sem FK (empresa excluída não apaga o rastro); + `empresa_cnpj` cópia |
| `planejamento_id` | int, nulo | sem FK |
| `recurso_tipo` / `recurso_id` | varchar / int | ex.: `documento` / 812 |
| `detalhes` | JSON | ex.: nome do arquivo, tamanho, hash, motivo da falha |
| `hash_anterior` / `hash` | char(64) | encadeamento (3.3) |

Índices: `(momento)`, `(usuario_id, momento)`, `(empresa_id, momento)`, `(acao, momento)`.

### 3.3 Integridade
- **Só inserção**: no Postgres, trigger que rejeita `UPDATE`/`DELETE` na tabela (exceto a rotina de retenção, que roda com papel próprio). Nenhuma rota de edição.
- **Encadeamento por hash**: cada linha guarda `hash = SHA-256(hash_anterior + conteúdo)`. Apagar ou alterar uma linha direto no banco quebra a corrente, e a verificação (`GET /auditoria/verificar`, Contador) aponta onde. Inserção serializada por `pg_advisory_xact_lock` para a corrente não bifurcar — o volume (dezenas de eventos por hora) não sente.
- **Gravação independente da requisição**: o serviço `auditar()` usa sessão de banco própria e faz commit imediato — um `LOGIN_FALHA` ou `ACESSO_NEGADO` fica registrado mesmo quando a requisição termina em erro. Transação mínima: lock → último hash por PK (`ORDER BY id DESC LIMIT 1`) → INSERT → commit, sem lógica dentro do lock; pool do SQLAlchemy dimensionado para a conexão extra (achado 6).
- **Sem enxurrada de eventos**: `PLANEJAMENTO_ABERTO` deduplicado por `SET aud_aberto:{sid}:{pid} NX EXAT {expira_em}` no Redis (a tela dispara 4–6 GETs do mesmo planejamento); `LOGIN_BLOQUEADO` um por janela de bloqueio, não um por tentativa (achado 5).
- **Verificação incremental**: tabela `auditoria_checkpoint`; a rota verifica só depois do último checkpoint; verificação completa vira comando de shell; o expurgo grava a âncora (`hash_anterior` da primeira linha restante) no próprio evento de expurgo; exportação CSV por streaming com período limitado (achado 7).
- Em SQLite (desenvolvimento) não há trigger; o encadeamento funciona igual.

### 3.4 Retenção (decisão A1)
Proposta: **5 anos**, alinhado ao prazo decadencial dos documentos fiscais que o sistema guarda; mínimo legal de 6 meses para registros de acesso (Marco Civil, art. 15). Rotina mensal `python -m app.services.auditoria --expurgar` remove o que passou do prazo e registra o próprio expurgo. IP e user agent são dados pessoais: a base legal é o legítimo interesse/segurança (LGPD art. 7º, IX) — vale citar na política de privacidade do escritório.

### 3.5 Tela "Auditoria" (só Contador)
- Filtros: período, usuário, empresa, ação, resultado, IP.
- Atalhos: "quem acessou esta empresa" (a partir da tela da empresa) e "o que este usuário fez" (a partir de Usuários).
- Destaques: `REFRESH_REUSO`, `LOGIN_BLOQUEADO`, `ACESSO_NEGADO` em vermelho.
- Exportar CSV (a própria exportação gera evento).
- Na tela de Documentos: "baixado por Fulano em 03/11 14:22" ao lado de cada arquivo.

---

## Parte 4 — Escopo por empresa (carteira)

### 4.0 Situação decidida (E2): pronto e desligado
Por enquanto **todos os analistas continuam vendo todas as empresas**. A estrutura é construída agora e fica atrás de `ESCOPO_POR_EMPRESA=false`:

| Construído agora | Fica para quando ligar |
|---|---|
| Tabela `usuario_empresa` (vazia) e migração `0017` | Carga inicial das carteiras (4.2) |
| Dependências `…Autorizado` em `deps.py` e as 48 buscas por id trocadas por elas — com a chave desligada, `empresas_visiveis()` devolve "todas" para todo mundo e o comportamento é idêntico ao de hoje | — |
| Filtro nas listagens e no dashboard (inofensivo com a chave desligada) | — |
| Teste de cobertura de rotas e testes rodando **com a chave ligada e desligada** | — |
| Rotas `GET/PUT /usuarios/{id}/empresas` (só Contador) | Tela "Carteira" em Usuários e coluna em Empresas (4.5) |

Vale fazer a troca das 48 buscas já: centraliza num lugar só a resposta "não encontrado", a auditoria de `ACESSO_NEGADO` e a futura regra. Para ligar depois: carregar as carteiras, mudar a variável, reiniciar — sem código novo.

### 4.1 Regra quando ligada (decisões E1–E3)
- **Contador**: vê e opera todas as empresas (como hoje).
- **Analista**: só as empresas da **sua carteira**; tudo que pende de uma empresa (planejamentos, levantamentos, documentos, notas, simulações, relatórios, exportações) segue a mesma regra.
- Cadastro e edição de empresas continuam só do Contador; quem monta a carteira é o Contador.
- Tabelas de regras globais (`tabelas.py`: alíquotas, NCM, normas, ST) não pertencem a empresa — continuam visíveis a todos.
- Fora da carteira a API responde **404**, não 403 (não confirma que o id existe) e grava `ACESSO_NEGADO`.

### 4.2 Banco (migração `0017`)
Tabela `usuario_empresa`: `usuario_id`, `empresa_id`, `concedido_por`, `concedido_em` — PK `(usuario_id, empresa_id)`.

**Carga inicial (E3)**: cada analista recebe as empresas em que já criou planejamento ou levantamento; o Contador revisa na tela antes de ativar a regra. A regra liga por variável (`ESCOPO_POR_EMPRESA=true`) para dar esse tempo de revisão.

### 4.3 Onde a regra entra (um ponto só)
Hoje há 48 buscas por id espalhadas (`obter_planejamento`, `_simulacao`, `db.get(RelatorioPdf…)`, `_doc_do_planejamento`). Em vez de remendar cada uma:

| Peça | Em [deps.py](../backend/app/api/deps.py) |
|---|---|
| `empresas_visiveis(u)` | `None` para Contador (= todas) ou `set[int]` para Analista, carregado uma vez por requisição |
| `PlanejamentoAutorizado` | dependência que lê `pid` da rota, carrega o planejamento e confere a empresa |
| `SimulacaoAutorizada`, `RelatorioAutorizado`, `EmpresaAutorizada` | idem, subindo até a empresa (`simulação → planejamento → empresa`) |
| `filtrar_por_escopo(query, u)` | aplicado nas listagens: `GET /empresas`, `GET /planejamentos`, `GET /dashboard` |

As rotas passam a receber o objeto já autorizado (`p: PlanejamentoAutorizado`) no lugar de `pid: int` + `obter_planejamento(db, pid)` — fica mais curto do que hoje.

Pontos que merecem atenção especial:
- **Dashboard** ([dashboard.py](../backend/app/api/routes/dashboard.py)): todos os totais precisam passar pelo filtro, senão vazam números de empresas fora da carteira.
- **Criação de planejamento**: analista só para empresa da carteira.
- **Busca de empresas** no formulário de planejamento: mesma filtragem.
- **Importação de empresas** (Contador): sem mudança.

### 4.4 Rede de segurança contra rota nova esquecida
Teste que percorre `app.routes`: toda rota com `{pid}`, `{sid}`, `{rid}`, `{empresa_id}` ou `{doc_id}` **precisa** depender de uma das dependências `…Autorizado`; senão o teste falha com o nome da rota. Mais um teste parametrizado que chama cada uma dessas rotas como analista sem carteira e exige 404.

### 4.5 Front
- `Usuarios.tsx`: para analistas, botão "Carteira" abre lista de empresas com marcação (busca por razão social/CNPJ, "marcar todas do filtro").
- `Empresas.tsx`: coluna/filtro "Analistas responsáveis" para o Contador.
- Nada muda para o analista além de ver menos empresas; links antigos para fora da carteira mostram "não encontrado".

---

## Parte 5 — Criptografia dos arquivos em repouso

### 5.1 Ameaça coberta
Cópia do disco, snapshot, backup ou acesso indevido ao volume do Render: sem a chave, os arquivos são ilegíveis. **Não** protege contra quem tem acesso ao servidor em execução com a chave carregada — isso continua dependendo das Partes 1–4.

### 5.2 Esquema (envelope)
- **Chave mestra (KEK)**: 32 bytes aleatórios em `CHAVE_ARQUIVOS` (base64), variável secreta do Render. Com identificador (`CHAVE_ARQUIVOS_ID`) para rotação; `CHAVES_ARQUIVOS_ANTIGAS` para leitura durante a troca.
- **Chave por arquivo (DEK)**: 32 bytes aleatórios para cada arquivo, cifrada com a KEK.
- **Algoritmo**: AES-256-GCM (biblioteca `cryptography`) — cifra e autentica: arquivo adulterado falha na leitura em vez de devolver lixo.
- **Dado associado (AAD)**: o nome gerado do arquivo — trocar um arquivo cifrado pelo de outro documento também falha.
- Arquivos têm no máximo 10 MB: cifra em memória, de uma vez, sem streaming.

Formato do arquivo:
```
"PTC1" | versão (1 byte) | id da KEK | nonce da DEK (12) | DEK cifrada (48) | nonce (12) | conteúdo cifrado + tag (16)
```

### 5.3 Onde muda
| Arquivo | Mudança |
|---|---|
| `app/services/cripto.py` *(novo)* | `cifrar(bytes, aad) -> bytes`, `decifrar(bytes, aad) -> bytes`, `cifrar_campo`/`decifrar_campo` (usado também pelo segredo TOTP da Parte 2) |
| [documentos.py](../backend/app/services/documentos.py) | `gravar` cifra; `caminho()` dá lugar a `ler(arquivo) -> bytes` |
| [bens_documentos.py](../backend/app/api/routes/bens_documentos.py) `baixar_documento` | `FileResponse` → `Response` com os bytes decifrados e o mesmo `Content-Disposition` |
| [pgdas.py](../backend/app/services/pgdas.py) | lê via `documentos.ler()` em vez de `caminho().read_bytes()` |
| [relatorio_pdf.py](../backend/app/services/relatorio_pdf.py) | grava cifrado; hash SHA-256 continua sendo **do PDF original** (a conferência de integridade não muda) |
| [simulacoes.py](../backend/app/api/routes/simulacoes.py) `baixar_relatorio` | decifra, confere o hash, devolve |

Excel, apresentação e exportação da revisão são gerados na hora e não tocam o disco — nada a fazer. XML de NF-e é lido em memória e vira linhas no banco — nada a fazer.

### 5.4 Migração dos arquivos existentes
Comando `python -m app.services.cripto --cifrar-existentes`: percorre `documentos/` e `relatorios/`, cifra o que ainda não começa com `PTC1` (idempotente, pode rodar de novo), grava em arquivo temporário e troca atomicamente. Depois de rodar, `ACEITAR_ARQUIVO_SEM_CIFRA=false` faz a leitura recusar arquivo em texto puro.

### 5.5 Rotação da chave
Comando `--recifrar-chaves`: com a KEK nova configurada, reescreve **só o cabeçalho** de cada arquivo (DEK recifrada) — rápido, o conteúdo não é tocado. Recomendação: anual ou imediatamente em suspeita de vazamento.

### 5.6 ⚠️ Guarda da chave
**Perder a `CHAVE_ARQUIVOS` = perder todos os documentos e os segredos de MFA.** A chave precisa ter cópia fora do Render (gerenciador de senhas do escritório, com acesso de duas pessoas). A API se recusa a subir em produção sem a chave, e a chave local do docker-compose é fixa e marcada como só para desenvolvimento.

Evolução futura possível: KEK em serviço de chaves gerenciado (AWS KMS / GCP KMS) em vez de variável de ambiente.

---

## 6. Decisões (todas aceitas conforme a recomendação)

| # | Pergunta | Decidido |
|---|---|---|
| S1 | Bloqueio de tela no front após 30 min sem interação (compensa a ausência de expiração por inatividade)? | **Sim** — pede só o código MFA para voltar |
| M1 | MFA obrigatório para todos, ou só para Contador? | **Todos** — analista também abre documentos |
| A1 | Retenção da auditoria | **5 anos** |
| A2 | Registrar abertura de planejamento (leitura), além de downloads e alterações? | **Sim**, uma vez por sessão e planejamento |
| E1 | Quando o escopo for ligado: Contador vê todas as empresas? | **Sim** (pode ficar para quando ligar) |
| E3 | Quando o escopo for ligado: carteira inicial dos analistas | **Empresas em que já trabalharam**, revisadas pelo Contador (pode ficar para quando ligar) |

Resolvidas nesta revisão: domínio `planejamento-tributario.domingosassessoria.com.br` com proxy da Vercel; E2 — analistas veem tudo, escopo pronto e desligado.

---

## 7. Ordem de execução

Cada etapa termina com testes passando e pode ir para produção sozinha.

| # | Etapa | Depende de | Visível para o usuário |
|---|---|---|---|
| 0 ✅ | **Base de desempenho** (achados 2, 6, 9) — *feito em 04/11/2026, sem commit; `FORWARDED_ALLOW_IPS` ficou configurável com padrão `*` até a etapa 3*: rotas de upload `async def` → `def`; `--workers 2`; `pool_size`/`max_overflow`/`pool_pre_ping` em `session.py`; limite de tamanho e de quantidade de arquivos no ZIP de NF-e (inclusive tamanho descompactado); trocar `--forwarded-allow-ips='*'` | — | Não |
| 1 ✅ | *feito em 04/11/2026, sem commit; `/api/saude` sempre 200 com o estado do Redis no corpo* — Redis no docker-compose, `fakeredis` nos testes, config nova; cliente síncrono com timeouts e disjuntor (achado 3); `noeviction` no `render.yaml` (achado 11) | 0 | Não |
| 2 ✅ | *feito em 04/11/2026, sem commit; migração 0013; eventos gravados pelo middleware depois do commit da rota, 503 se não gravar; trigger do Postgres não testado (sem Postgres local)* — **Auditoria**: tabela, serviço `auditar()`, encadeamento, eventos de documentos/exportações; deduplicação no Redis e checkpoint (achados 5, 7) | 1 | Não (tela vem na 8) |
| 3 ✅ | *feito em 04/11/2026, sem commit; inclui o front mínimo (access em memória, refresh automático, proxy do Vite, rewrite /api no vercel.json) e a contingência da auditoria; `db.get(Usuario)` mantido (combinado com a sessão Gargalos)* — **Sessões**: access/refresh, rotação, logout real, revogação, limite de login + eventos de acesso; `perfil`/`ativo` no hash da sessão, sem `db.get(Usuario)` por requisição (achado 4) | 1, 2 | Login de novo uma vez |
| 3b ✅ | *feito em 06/11/2026 na branch `pgdas-no-banco`, migração 0015; extratos antigos: `python -m app.services.pgdas`* — **PGDAS no banco** (achado 1): extrair RBT12/PA/anexos no upload e gravar no `Documento`; `pgdas.do_planejamento` lê a leitura gravada e só abre o PDF de documento antigo ainda sem ela (sem gravar); o start do container roda `python -m app.services.pgdas`, que grava a leitura dos antigos (só leitura bem-sucedida; falha não impede a API de subir) | — | Não (fica mais rápido) |
| 4 ✅ | *feito em 09/11/2026, branch `cripto-arquivos`; sem migração; o start do container ainda não roda `--cifrar-existentes` (entra na etapa 9, deploy, depois do preenchimento do PGDAS)* — **Atenção da 3b (atendida):** `pgdas._ler_arquivo` passa a ler por `documentos.ler()` (decifrando) e o preenchimento do PGDAS roda antes de `--cifrar-existentes`. A marca `PTC1` vai para `cripto.py` e o `pgdas.MARCA_CIFRADO` passa a importá-la de lá. **Criptografia**: `cripto.py`, documentos e relatórios cifrados, comando de migração | 0, 3b | Não |
| 5 | **MFA**: rotas, tabelas, segredo cifrado, recuperação com HMAC (achado 8) | 3, 4 | Cadastro do 2º fator no próximo login |
| 6 | **Escopo por empresa (desligado)**: tabela, dependências `…Autorizado`, refatoração das 48 buscas, filtros, teste de cobertura de rotas; dashboard reescrito como consulta agregada (achado 10) | 2 | Não |
| 6b | **Fila no Postgres** (8.1): tabela `tarefa`, linha de execução por processo, recuperação de tarefa interrompida, ZIP em fluxo e por lotes, NF-e/relatório contábil/PDF/PPTX/Excel passando pela fila, tela de progresso | 0, 4 | Sim (barra de progresso) |
| 7 | **Front**: cliente com access em memória, `VITE_API_URL=/api`, proxy do Vite, refresh único em voo, multi-aba, login em 2 etapas, configuração do MFA | 3, 5 | Sim |
| 8 | **Telas de gestão**: Auditoria, 2º fator em Usuários, bloqueio de tela | 2, 5 | Sim |
| 9 | **Deploy**: DNS + domínio na Vercel, rewrite `/api` no `vercel.json`, Key Value gratuito no `render.yaml`, variáveis, cabeçalhos/CSP, **testes de limite do proxy (1.8)**, conferência do IP, `--cifrar-existentes` | tudo | Sim |
| depois | Ligar o escopo: carga das carteiras, tela de Carteira, `ESCOPO_POR_EMPRESA=true` | 6 | Sim |

O proxy na Vercel (etapa 9) pode ser configurado por você a qualquer momento antes — com o código atual ele já funciona se `VITE_API_URL=/api`; o cookie de refresh só depende dele a partir da etapa 7.

### Novas dependências
- Backend: `redis>=5.0`, `pyotp>=2.9`, `segno>=1.6`, `cryptography>=43`; dev: `fakeredis>=2.23`.
- Front: nenhuma.

### Migrações
`0013` auditoria (+ trigger no Postgres) · `0014` índices de desempenho (sessão Gargalos) · `0015` PGDAS no banco · `0016` MFA · `0017` carteira · `0018` tarefa. Sessões não usam banco.

### Novas variáveis de ambiente
`REDIS_URL`, `ACCESS_TTL_MIN=15`, `SESSAO_ABSOLUTA_H=12`, `COOKIE_SECURE`, `JWT_SECRET_ANTERIOR`, `PROXIES_CONFIAVEIS`, `ORIGEM_PUBLICA=https://planejamento-tributario.domingosassessoria.com.br`, `ESCOPO_POR_EMPRESA=false`, `CHAVE_ARQUIVOS`, `CHAVE_ARQUIVOS_ID`, `CHAVES_ARQUIVOS_ANTIGAS`, `ACEITAR_ARQUIVO_SEM_CIFRA`, `AUDITORIA_RETENCAO_ANOS=5`. Sai: `JWT_EXPIRA_MINUTOS`. Muda: `CORS_ORIGINS` vazio em produção; `VITE_API_URL=/api`.

### Testes (resumo)
- **Sessões**: cookie com atributos certos; rotação; reuso derruba sessão; corrida dentro da tolerância não derruba; logout e troca de senha valem na hora; expiração aos 12 h; JWT `alg=none`/`aud`/`typ` errados → 401; 6ª tentativa → 429; Redis fora → 503.
- **MFA**: sessão nivel=senha só acessa configuração; código errado/repetido recusado; recuperação de uso único; reset pelo Contador derruba sessões; segredo no banco não é legível.
- **Auditoria**: cada ação da tabela 3.1 gera evento; falha de login registrada mesmo com 401; `UPDATE`/`DELETE` bloqueados (Postgres); verificação detecta linha alterada.
- **Escopo**: teste de cobertura de rotas; analista sem carteira recebe 404 em todas as rotas de recurso; dashboard e listagens filtrados; Contador vê tudo.
- **Criptografia**: arquivo no disco não contém o conteúdo original; leitura com AAD trocado ou byte alterado falha; rotação de KEK mantém leitura; migração idempotente; hash do relatório confere após cifrar.

---

## 8. Ajustes de desempenho (análise de gargalos)

Achados da sessão "Gargalos e escalabilidade", conferidos no código em 04/11/2026: as rotas de upload são `async def` com SQLAlchemy síncrono (`bens_documentos.py:158`, `empresas.py:78/87`, `planejamentos.py:394/451`); o Uvicorn sobe com 1 worker; o `create_engine` usa o pool padrão; `pgdas.do_planejamento` é chamado por `premissas_auto` e `entrada`; o ZIP de NF-e é aberto inteiro em memória e sem limite de tamanho.

| # | Seção | Problema | Ajuste incorporado | Etapa |
|---|---|---|---|---|
| 1 | 5.3 | O PDF do PGDAS é lido e interpretado ~3× a cada gravação da tela; com a cifra, cada leitura também decifra até 10 MB | Extrair RBT12/PA/anexos no upload e guardar no `Documento`; o arquivo cifrado só é lido no download | 3b |
| 2 | 7 | Rotas `async def` com trabalho síncrono travam o event loop do único worker; cifrar 10 MB ali para todos os usuários | `async def` → `def` (threadpool), `--workers 2`, cliente Redis síncrono | 0 |
| 3 | 1.7 | Redis lento (não fora do ar) prende threads até o timeout padrão (infinito) | Timeouts de 0,5 s e disjuntor | 1 |
| 4 | 1.1, 4.3 | Redis + `db.get(Usuario)` + carteira a cada requisição | `perfil`/`ativo` no hash da sessão (revogação já cobre mudança); escopo desligado = zero consultas; carteira em `carteira:{uid}` no Redis quando ligar | 3, 6 |
| 5 | 3.1, 3.3 | `PLANEJAMENTO_ABERTO` sem deduplicação definida; tentativas bloqueadas enchendo a corrente | `SET … NX` no Redis; um `LOGIN_BLOQUEADO` por janela | 2 |
| 6 | 3.3 | `auditar()` com sessão própria dobra conexões por requisição | Pool dimensionado explicitamente; transação mínima dentro do lock. **Conferir o `max_connections` do Postgres basic-256mb** antes de fixar `pool_size × workers` | 0, 2 |
| 7 | 3.3, 3.5 | Verificar 5 anos de corrente numa requisição estoura o proxy; expurgo quebra o começo da corrente | Checkpoint incremental, verificação completa por comando, âncora no evento de expurgo, CSV por streaming | 2 |
| 8 | 2.1 | Códigos de recuperação com bcrypt: até ~2,5 s por tentativa | HMAC-SHA256 com segredo do servidor | 5 |
| 9 | 1.8 | ZIP de NF-e sem limite e síncrono; costuma ser maior que 10 MB | Limite de tamanho (compactado e descompactado — também evita "zip bomb") e de quantidade de arquivos. Ver 8.1 | 0 |
| 10 | 4.3 | Dashboard já é N+1 (carrega `resultado_json` inteiro e um `db.get` por simulação) | Reescrever como consulta agregada já com o filtro de escopo | 6 |
| 11 | 1.3 | Memória do Redis | Não é gargalo; `noeviction` declarado no `render.yaml`; fila (se adotada) guarda só ids | 1 |

Achado adicional desta revisão: `--forwarded-allow-ips='*'` no [Dockerfile](../backend/Dockerfile) deixa qualquer cliente forjar o IP chamando o Render direto — corrigido na etapa 0 (ver 1.5).

Sem gargalo relevante (confirmado pela análise): corrente serializada por `pg_advisory_xact_lock` nesse volume com lock curto; AES-GCM em si; `Response` com 10 MB no lugar de `FileResponse`; salto extra da Vercel nas requisições comuns.

### 8.1 Tarefas em segundo plano — decidido: fila no Postgres, processada dentro da API
Decisão do usuário (04/11/2026): **fila no próprio Postgres**, sem serviço novo, sem Redis e sem nada fora do Render. O usuário espera **volume grande de dados**, então o desenho abaixo já considera isso.

**Por que não fora do Render**: o disco persistente só é montado no serviço da API, então um processador externo precisaria de armazenamento de objetos, da `CHAVE_ARQUIVOS` e do Postgres aberto à internet. Seriam mais custo, mais superfície de ataque e mais um operador de dados (LGPD). Com a fila dentro da API, os documentos e a chave nunca saem do Render.

**Vai para a fila**: importação de NF-e (XML/ZIP), importação do relatório contábil, geração do relatório PDF, da apresentação PPTX e do Excel da simulação. Fica síncrono: envio de documento avulso, que é só validar, cifrar e gravar.

**Tabela `tarefa`** (migração `0018`):
| Coluna | Observação |
|---|---|
| `id`, `tipo`, `situacao` | `PENDENTE` → `EXECUTANDO` → `CONCLUIDA` / `FALHOU` / `CANCELADA` |
| `planejamento_id`, `empresa_id`, `usuario_id` | para escopo, auditoria e "minhas tarefas" |
| `parametros` (JSON), `arquivo_entrada` | referência ao arquivo já gravado **cifrado** no disco (nunca o conteúdo no banco) |
| `progresso_atual`, `progresso_total`, `mensagem` | "Importando 340 de 1.200 notas" |
| `resultado` (JSON), `arquivo_saida`, `erro` | resumo, arquivo gerado (cifrado) ou mensagem de erro |
| `tentativas`, `executando_desde`, `pulso_em` | recuperação de tarefa interrompida |
| `criada_em`, `concluida_em` | |

**Funcionamento**
- A rota grava o arquivo, cria a tarefa e responde `202 {tarefa_id}` em milissegundos. O proxy da Vercel deixa de ser limite.
- Cada processo do Uvicorn sobe **1 linha de execução** que busca a próxima tarefa com `SELECT … FOR UPDATE SKIP LOCKED` (ou é acordada por `LISTEN/NOTIFY`, com varredura de segurança a cada 5 s). Com 2 processos são no máximo 2 tarefas ao mesmo tempo, sem disputa entre elas.
- Durante a execução a tarefa atualiza `pulso_em` a cada lote. Na subida da API, e a cada minuto, tarefa `EXECUTANDO` sem pulso há mais de 2 min volta para `PENDENTE` (até 3 tentativas, depois `FALHOU`). Deploy e reinício não perdem trabalho.
- **Idempotência**: a importação de NF-e já ignora notas com chave repetida, então reprocessar após uma interrupção não duplica nada. O PDF e o PPTX são regerados do zero.
- Front: `GET /tarefas/{id}` consultado a cada 1–2 s, com barra de progresso. A lista "Tarefas em andamento" fica no Layout, então dá para sair da tela e voltar. Os downloads de saída passam pelo `baixarArquivo` com auditoria.
- Auditoria: `TAREFA_CRIADA` e `TAREFA_FALHOU`, mais os eventos do próprio tipo (`NFE_IMPORTADA`, `RELATORIO_GERADO` etc.) gravados na conclusão.
- Uma tarefa também passa pelas dependências `…Autorizado`: ninguém consulta tarefa de empresa fora do escopo.

**Volume grande: cuidados obrigatórios**
- **Memória**: o plano Starter do Render tem **512 MB de RAM**, divididos entre os 2 processos. O ZIP é lido **entrada por entrada** (`zipfile.open` em fluxo), nunca descompactado inteiro em memória. Há limite de tamanho descompactado total e por XML, contra "zip bomb".
- **Lotes**: commit a cada ~200 notas, com progresso e pulso. Uma falha no meio não desfaz o que já entrou.
- **Recálculo uma vez só**: `_alterou` (o recálculo de progresso e premissas) roda **uma vez no fim** da tarefa, não por nota nem por lote.
- **Limites configuráveis**: `TAREFA_ZIP_MAX_MB`, `TAREFA_ZIP_MAX_ARQUIVOS`, `TAREFA_MAX_POR_USUARIO` (por exemplo, 3 pendentes), para que um envio enorme não segure a fila dos outros.
- **Medir antes do deploy** com o maior ZIP real que o escritório tiver: tempo, pico de memória (`tracemalloc`/métrica do Render) e tamanho final no banco. Se a memória ficar apertada, o próximo passo é o plano Standard (2 GB), não um serviço separado.
- **Quando separar**: se o processamento começar a deixar a tela lenta para quem está usando, a tarefa passa para um Background Worker do Render. Para isso, os arquivos precisam antes ir para armazenamento compartilhado. O desenho da tabela não muda.
