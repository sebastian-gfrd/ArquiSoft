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

# 4. AQUÍ ESTÁ EL TRUCO: 
# Copiamos solo el contenido de la carpeta App_Web directamente a /app
COPY App_Web/ .

# 5. Verificamos que App_Web.wsgi esté bien direccionado.
# Como ya estamos dentro de lo que era "App_Web", el archivo wsgi.py 
# debería estar en la subcarpeta interna llamada también App_Web.
CMD ["gunicorn", "App_Web.wsgi:application", "--bind", "0.0.0.0:8080", "--timeout", "90", "--workers", "3"]