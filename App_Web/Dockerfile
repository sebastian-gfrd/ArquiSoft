# Usamos una imagen base ligera de Python para reducir el tamaño final
FROM python:3.11-slim

# Evita que Python escriba archivos .pyc y fuerza a que la salida estándar no se bloquee (logs limpios)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instalamos dependencias del sistema necesarias para compilar paquetes (ej. psycopg2)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiamos solo el archivo de requerimientos primero para aprovechar la caché de Docker
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Instalamos gunicorn explícitamente para el entorno de producción
RUN pip install gunicorn

# Copiamos el resto del código fuente del microservicio
COPY . /app/

# Exponemos el puerto que el Load Balancer va a consultar
EXPOSE 8000

# Comando de arranque (4 workers para aprovechar la CPU asignada por Fargate)
CMD ["gunicorn", "App_Web.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
