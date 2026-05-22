FROM python:3.13.5

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 1. Nos paramos en /app
WORKDIR /app

# 2. Instalamos dependencias del sistema
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# 3. Copiamos requirements y los instalamos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiamos el resto del código del microservicio
COPY . .

# 5. Verificamos que App_Web.wsgi esté bien direccionado
CMD ["gunicorn", "App_Web.wsgi:application", "--bind", "0.0.0.0:8080", "--timeout", "90", "--workers", "3"]
