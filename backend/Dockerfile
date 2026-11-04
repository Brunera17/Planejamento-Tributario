FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# FORWARDED_ALLOW_IPS="*" só serve para o esquema (https) atrás do proxy do Render. O IP do cliente (limite de
# login e auditoria) NÃO vem do uvicorn: a API lê o X-Forwarded-For com IP_POR_X_FORWARDED_FOR e PROXIES_CONFIAVEIS
# (app/core/contexto.py). Conferir no primeiro deploy se o IP gravado na auditoria é o do cliente.
# produção: sem dados de demonstração; o primeiro usuário vem de ADMIN_USUARIO e ADMIN_SENHA (veja app/seeds/carga.py)
CMD ["sh", "-c", "alembic upgrade head && python -m app.seeds.carga && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-*}\""]
