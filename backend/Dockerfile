FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# produção: sem dados de demonstração; o primeiro usuário vem de ADMIN_USUARIO e ADMIN_SENHA (veja app/seeds/carga.py)
CMD ["sh", "-c", "alembic upgrade head && python -m app.seeds.carga && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
