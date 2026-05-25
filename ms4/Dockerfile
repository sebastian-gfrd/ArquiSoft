# Imagen base ligera
FROM python:3.11-slim

# Variables de entorno críticas
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias del sistema (asyncpg compila más rápido con dependencias C)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copia de dependencias
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia del código fuente del worker
COPY . /app/

# El comando arranca Celery. 
# --concurrency=2 se alinea con las 2 vCPUs del perfil c5.large que definimos en Terraform
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "--concurrency=2", "--without-gossip", "--without-mingle", "--without-heartbeat"]
