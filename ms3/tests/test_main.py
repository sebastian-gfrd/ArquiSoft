import os
import sys
import jwt
import pytest
from fastapi.testclient import TestClient

# Asegurar que el directorio raíz de ms3/ está en el PATH de pruebas
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Forzar DEV_MODE=True para que las pruebas simulen firmas de ALB y conexión SQS sin red real
os.environ["DEV_MODE"] = "True"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["SQS_QUEUE_URL"] = ""  # Forzar simulación de SQS local

from app.main import app

client = TestClient(app)

def generate_mock_jwt(tenant_id: int, email: str = "test_user@bite.co") -> str:
    """Genera un token JWT simulado para saltar la validación ALB en DEV_MODE."""
    payload = {
        "https://bite.co/tenant_id": tenant_id,
        "email": email,
        "sub": "user-sub-12345"
    }
    # En DEV_MODE no se verifica firma, por lo que podemos usar cualquier llave/algoritmo
    return jwt.encode(payload, "secret-dev", algorithm="HS256")

def test_health_check():
    """
    Verifica que el endpoint público de salud /health/ funcione correctamente
    y retorne la estructura esperada con latencia y estado saludable en DEV_MODE.
    """
    response = client.get("/health/")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "healthy"
    assert "sqs_queue" in data["services"]
    assert "latency_ms" in data["services"]["sqs_queue"]
    assert data["services"]["sqs_queue"]["latency_ms"] > 0

def test_ingest_success():
    """
    Verifica el flujo exitoso (POST /api/v1/integration/ingest):
    Un inquilino autenticado envía credenciales de AWS sintácticamente correctas.
    Debe retornar 202 Accepted de inmediato con un identificador de tarea (task_id).
    """
    tenant_id = 123
    project_id = 999
    
    # Generar token del tenant 123
    mock_token = generate_mock_jwt(tenant_id=tenant_id)
    headers = {"x-amzn-oidc-data": mock_token}
    
    payload = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "provider": "AWS",
        "credentials": {
            "role_arn": "arn:aws:iam::123456789012:role/BiteIntegrationRole",
            "s3_bucket": "bite-billing-bucket",
            "external_id": "84d5df33-31f4-4113-911b-851f8b1d7dcd"
        }
    }
    
    response = client.post("/api/v1/integration/ingest", json=payload, headers=headers)
    assert response.status_code == 202
    
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "queued"
    assert "timestamp" in data

def test_ingest_invalid_credentials_format():
    """
    Verifica que si las credenciales fallan sintácticamente (Role ARN mal formado),
    el API rechaza inmediatamente la petición con un HTTP 400 Bad Request
    sin interactuar con colas ni persistencias.
    """
    tenant_id = 123
    mock_token = generate_mock_jwt(tenant_id=tenant_id)
    headers = {"x-amzn-oidc-data": mock_token}
    
    payload = {
        "tenant_id": tenant_id,
        "project_id": 999,
        "provider": "AWS",
        "credentials": {
            # ARN inválido (no tiene los 12 dígitos de la cuenta AWS)
            "role_arn": "arn:aws:iam::invalid-account:role/BiteRole",
            "s3_bucket": "bite-bucket"
        }
    }
    
    response = client.post("/api/v1/integration/ingest", json=payload, headers=headers)
    assert response.status_code == 400
    assert "Estructura o formato de credenciales inválido" in response.json()["detail"]

def test_ingest_missing_credentials_fields():
    """
    Verifica que si faltan campos obligatorios para el proveedor (ej. s3_bucket en AWS),
    el validador de modelo de Pydantic v2 actúe en primera línea arrojando un HTTP 422.
    """
    tenant_id = 123
    mock_token = generate_mock_jwt(tenant_id=tenant_id)
    headers = {"x-amzn-oidc-data": mock_token}
    
    payload = {
        "tenant_id": tenant_id,
        "project_id": 999,
        "provider": "AWS",
        "credentials": {
            "role_arn": "arn:aws:iam::123456789012:role/BiteRole"
            # Falta s3_bucket de forma obligatoria
        }
    }
    
    response = client.post("/api/v1/integration/ingest", json=payload, headers=headers)
    assert response.status_code == 422
    # En validaciones de modelo general de Pydantic v2 (model_validator),
    # el error se reporta a nivel de raíz del body con el mensaje correspondiente.
    error_detail = response.json()["detail"][0]
    assert "body" in error_detail["loc"]
    assert "s3_bucket" in error_detail["msg"]

def test_ingest_tenant_intrusion_forbidden():
    """
    Verifica el aislamiento multi-inquilino de seguridad:
    Si un usuario autenticado como tenant 123 intenta enviar un Job de ingesta
    para el tenant 999, el sistema detecta la discrepancia y deniega el acceso
    retornando un HTTP 403 Forbidden.
    """
    # Token para tenant 123
    mock_token_tenant_123 = generate_mock_jwt(tenant_id=123)
    headers = {"x-amzn-oidc-data": mock_token_tenant_123}
    
    # Petición intentando inyectar datos del tenant 999
    payload = {
        "tenant_id": 999,
        "project_id": 999,
        "provider": "AWS",
        "credentials": {
            "role_arn": "arn:aws:iam::123456789012:role/BiteIntegrationRole",
            "s3_bucket": "bite-billing-bucket"
        }
    }
    
    response = client.post("/api/v1/integration/ingest", json=payload, headers=headers)
    assert response.status_code == 403
    assert "El token no pertenece al tenant solicitado" in response.json()["detail"]

def test_ingest_gcp_success():
    """
    Verifica que el proveedor esquelético GCP funcione de forma análoga bajo el
    patrón Adapter, demostrando que la API está abierta a extensiones (Principio Open/Closed).
    """
    tenant_id = 123
    mock_token = generate_mock_jwt(tenant_id=tenant_id)
    headers = {"x-amzn-oidc-data": mock_token}
    
    payload = {
        "tenant_id": tenant_id,
        "project_id": 456,
        "provider": "GCP",
        "credentials": {
            "project_id_gcp": "bite-gcp-project-123",
            "service_account_key": "{\n  \"type\": \"service_account\"\n}"
        }
    }
    
    response = client.post("/api/v1/integration/ingest", json=payload, headers=headers)
    assert response.status_code == 202
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "queued"
