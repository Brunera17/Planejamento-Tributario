# Planejador Tributário

Sistema web que compara **Simples Nacional × Lucro Presumido × Lucro Real** a partir das notas fiscais, compras,
despesas e folha de uma empresa, recomenda o regime de menor carga, projeta a **Reforma Tributária (2027–2033)** e
aponta oportunidades de economia e recuperação — com memória de cálculo auditável.

Especificação completa: [docs/ESPECIFICACAO_Planejador_Tributario.md](docs/ESPECIFICACAO_Planejador_Tributario.md).

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

O planejamento de demonstração (*Autopeças Demonstração Ltda*, jun–ago/2026) usa os dados agregados e anonimizados
do caso de referência. Abra **Planejamentos → Simulações → Simular agora**.

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
| Planejamento, status e histórico | ✅ |
| Coleta: compras, devoluções, folha, composição das compras, premissas | ✅ |
| Levantamento de despesas por competência (catálogo com classificação tributária) | ✅ (API e tela de valores; "outras despesas" e envio para conferência só pela API) |
| Importação de NF-e XML (avulso ou .zip), saídas e entradas | ✅ (processamento síncrono) |
| Importação do relatório de movimentação do sistema contábil (.xlsx) | ⏳ precisa de um arquivo-modelo do relatório |
| Motor: Simples, LP, LR, Reforma, comparativo, equilíbrio, crescimento, 11 oportunidades, pontos críticos | ✅ |
| Memória de cálculo e simulações versionadas/desatualizadas | ✅ |
| Progresso e pendências por bloco | ✅ |
| Exportação Excel | ✅ |
| Relatório PDF (ReportLab): veredito, composição da carga, Reforma, oportunidades, recomendação editável, anexos, marca PRELIMINAR, arquivamento com SHA-256 | ✅ |
| Bens, documentos (upload) e tela de tabelas legais | ⏳ modelos prontos, rotas/telas pendentes |
| Processamento em segundo plano para importações grandes | ⏳ |

### Fonte do relatório PDF

O PDF usa a mesma fonte da aplicação (Archivo) quando os arquivos `Archivo-Regular.ttf` e `Archivo-SemiBold.ttf`
estão em `backend/app/assets/fonts/` (licença SIL Open Font License, disponível no Google Fonts). Sem eles, usa
Helvetica.
