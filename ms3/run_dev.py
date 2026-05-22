import os
import sys
import uvicorn

# Asegurar que el directorio raíz de ms3/ está en el PATH para importaciones limpias de app.*
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Configurar variables de entorno por defecto para desarrollo local
os.environ.setdefault("DEV_MODE", "True")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("PORT", "8003")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8003))
    print(f"--- Levantando BITE.co Microservicio 3 en Modo Desarrollo Local ---")
    print(f"Dirección: http://127.0.0.1:{port}")
    print(f"Documentación Swagger: http://127.0.0.1:{port}/docs")
    print(f"Endpoint de Salud: http://127.0.0.1:{port}/health/")
    print(f"------------------------------------------------------------------")
    
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        reload=True
    )
