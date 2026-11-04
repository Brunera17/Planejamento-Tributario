FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# FORWARDED_ALLOW_IPS: "*" confia no X-Forwarded-For de qualquer origem (o IP do cliente pode ser forjado).
# Nada usa o IP ainda; o limite de login e a auditoria vão resolver o IP com PROXIES_CONFIAVEIS — conferir no deploy.
# produção: sem dados de demonstração; o primeiro usuário vem de ADMIN_USUARIO e ADMIN_SENHA (veja app/seeds/carga.py)
CMD ["sh", "-c", "alembic upgrade head && python -m app.seeds.carga && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-*}\""]
