FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# requirements.txt é o lock (versões exatas, gerado de requirements.in): o build não muda de um dia para o outro
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# FORWARDED_ALLOW_IPS="*" só serve para o esquema (https) atrás do proxy do Render. O IP do cliente (limite de
# login e auditoria) NÃO vem do uvicorn: a API lê o X-Forwarded-For com IP_POR_X_FORWARDED_FOR e PROXIES_CONFIAVEIS
# (app/core/contexto.py). Conferir no primeiro deploy se o IP gravado na auditoria é o do cliente.
# app.services.pgdas: grava a leitura dos extratos do PGDAS-D enviados antes da leitura no upload (idempotente;
# precisa rodar antes da criptografia dos arquivos). Se falhar, só avisa: não impede a API de subir.
# produção: sem dados de demonstração; o primeiro usuário vem de ADMIN_USUARIO e ADMIN_SENHA (veja app/seeds/carga.py)
# app.implantacao: no Render grátis a API acorda num contêiner novo; se esta versão já foi preparada no banco,
# pula migrações e cargas (sobe mais rápido). Fora do Render (sem RENDER_GIT_COMMIT) o preparo roda sempre.
CMD ["sh", "-c", "{ python -m app.implantacao pronta || { alembic upgrade head && python -m app.seeds.carga && (python -m app.services.pgdas || echo \"aviso: leitura dos extratos do PGDAS-D antigos falhou; a API sobe assim mesmo\") && python -m app.implantacao marcar; }; } && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
