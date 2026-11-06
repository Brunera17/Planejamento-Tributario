# Planejador Tributário

Sistema web que compara **Simples Nacional × Lucro Presumido × Lucro Real** a partir das notas fiscais, compras,
despesas e folha de uma empresa, recomenda o regime de menor carga, projeta a **Reforma Tributária (2027–2033)** e
aponta oportunidades de economia e recuperação — com memória de cálculo auditável.

Especificação completa: [docs/ESPECIFICACAO_Planejador_Tributario.md](docs/ESPECIFICACAO_Planejador_Tributario.md) ·
[Evidências (capturas de tela)](docs/evidencias/README.md).

## Estrutura

```
backend/                 API FastAPI + motor de cálculo
  app/motor/             funções puras (sem banco): base, ICMS, Simples, LP, LR, Reforma, comparativo, oportunidades
  app/services/          montagem da entrada a partir do banco, simulação, progresso, NF-e XML, importação, Excel
  app/api/routes/        rotas REST (permissões verificadas no backend)
  app/models/            SQLAlchemy 2 (33 tabelas)
  app/seeds/dados/       tabelas legais da carga inicial (Anexo I, parâmetros, Reforma, CFOP, NCM, catálogo)
  alembic/               migrations
  tests/                 caso de referência (planilha) + API ponta a ponta
frontend/                React + TypeScript + Vite + Tailwind
exemplos/                empresas_exemplo.xlsx
docs/                    especificação
```

## Pré-requisitos

- **Com Docker:** apenas Docker e Docker Compose.
- **Sem Docker:** Python 3.12+ e Node 20+. O banco padrão local é SQLite; PostgreSQL 16 é o banco de produção.

## Execução com Docker

```bash
docker compose up --build
```

- Frontend: http://localhost:5173 · API: http://localhost:8000/api · Swagger: http://localhost:8000/docs
- A API aplica as migrations e a carga inicial (com o planejamento de demonstração) ao subir.

## Execução local (sem Docker)

Backend:

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.seeds.carga --demo
.venv/Scripts/uvicorn app.main:app --reload --port 8000
```

(No Linux/macOS, troque `.venv/Scripts/` por `.venv/bin/`.)

Dependências do backend: `requirements.in` tem os pisos (`>=`) e `requirements.txt` é o lock com as versões exatas,
usado pelo Docker, pelo CI e pela instalação acima. Ao mudar o `requirements.in`, gere o lock de novo (o CI falha se
os dois estiverem fora de sincronia):

```bash
cd backend
uv pip compile requirements.in -o requirements.txt --universal --python-version 3.12
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Configuração

Copie `.env.example` para `.env` na raiz e ajuste:

| Variável | Uso | Padrão local |
|---|---|---|
| `DATABASE_URL` | conexão SQLAlchemy | `sqlite:///backend/planejador.db` |
| `JWT_SECRET` | assinatura dos tokens (≥ 32 caracteres) | segredo de desenvolvimento |
| `UPLOAD_DIR` | arquivos enviados e PDFs arquivados | `backend/uploads` |
| `CORS_ORIGINS` | origens do frontend | `http://localhost:5173` |
| `ESCRITORIO_NOME` | nome no cabeçalho do relatório PDF | `Planejador Tributário` |
| `VITE_API_URL` | URL da API usada pelo frontend | `http://localhost:8000/api` |

## Acesso de demonstração

| Perfil | Usuário | Senha |
|---|---|---|
| Contador | `contador` | `demo123` |
| Analista | `analista` | `demo123` |

A carga `--demo` cria dois planejamentos:

- *Autopeças Demonstração Ltda*: dados agregados e anonimizados do caso de referência, em coleta. Abra **Planejamentos → Simulações → Nova simulação**.
- *Distribuidora Modelo de Autopeças Ltda*: exemplo fictício com 100% das informações, simulação aprovada e relatório final.

## Testes

```bash
cd backend && .venv/Scripts/python -m pytest
cd frontend && npm test
```

`tests/test_motor_referencia.py` garante que o motor reproduz, até o centavo, a planilha final de planejamento:

| Regime | Carga do trimestre | Alíquota efetiva |
|---|---|---|
| Simples Nacional | R$ 63.688,26 | 9,79% |
| Lucro Presumido | R$ 59.765,84 | 9,19% |
| Lucro Real | R$ 61.192,34 | 9,41% |

## Situação da implementação

| Item da especificação | Situação |
|---|---|
| Autenticação JWT, perfis, permissões no backend | ✅ |
| Empresas: cadastro, importação com prévia, CNPJ numérico e alfanumérico | ✅ |
| Usuários: criação, edição, troca de senha e desativação pela tela | ✅ |
| Planejamento, status e histórico, com envio, conferência e devolução pela tela | ✅ |
| Coleta pela tela: compras, devoluções, folha, origem das compras e premissas do cálculo | ✅ |
| Levantamento de despesas por competência (catálogo com classificação tributária) | ✅ |
| Importação de NF-e XML (avulso ou .zip), saídas e entradas | ✅ (processamento síncrono) |
| Importação do relatório "Movimentação de Produtos" do Domínio (.xls/.xlsx), saídas e entradas, com devoluções automáticas | ✅ |
| Motor: Simples, LP, LR, Reforma, comparativo, equilíbrio, crescimento, 11 oportunidades, pontos críticos | ✅ |
| Memória de cálculo e simulações versionadas/desatualizadas | ✅ |
| Progresso e pendências por bloco | ✅ |
| Exportação Excel | ✅ |
| Relatório PDF (ReportLab): veredito, composição da carga, Reforma, oportunidades, recomendação editável, anexos, marca PRELIMINAR, arquivamento com SHA-256 | ✅ |
| Bens próprios e documentos (envio de arquivos, "não se aplica" com justificativa) | ✅ |
| Base legal (Lei 10.485/2002) e regras de CFOP | ✅ |
| Revisão de produtos: confronto com a lei, inconsistências e correção pelo contador | ✅ |
| Tela das demais tabelas legais (Anexo I, parâmetros, Reforma) | ⏳ rotas prontas, tela pendente |
| Processamento em segundo plano para importações grandes | ⏳ |

### Fonte do relatório PDF

O PDF usa a mesma fonte da aplicação (Archivo) quando os arquivos `Archivo-Regular.ttf` e `Archivo-SemiBold.ttf`
estão em `backend/app/assets/fonts/` (licença SIL Open Font License, disponível no Google Fonts). Sem eles, usa
Helvetica.
