from datetime import datetime, timezone
from typing import Any, Dict
from pydantic import BaseModel, Field, model_validator

class IntegrationRequest(BaseModel):
    """
    Esquema de entrada para las solicitudes de integración de nube.
    Utiliza validadores estrictos de Pydantic v2 para corroborar sintácticamente
    las credenciales según el proveedor seleccionado antes de admitir el Job.
    """
    tenant_id: int = Field(
        ..., 
        description="Identificador único del inquilino (Tenant) dueño de la cuenta", 
        json_schema_extra={"example": 123}
    )
    project_id: int = Field(
        ..., 
        description="Identificador único del proyecto dentro de la organización", 
        json_schema_extra={"example": 456}
    )
    provider: str = Field(
        ..., 
        description="Proveedor de nube para la ingesta. Debe ser 'AWS' o 'GCP' (insensible a mayúsculas)",
        json_schema_extra={"example": "AWS"}
    )
    credentials: Dict[str, Any] = Field(
        ..., 
        description="Diccionario de credenciales dinámicas específicas del proveedor",
        json_schema_extra={"example": {
            "role_arn": "arn:aws:iam::123456789012:role/BiteIntegrationRole",
            "s3_bucket": "bite-billing-bucket",
            "external_id": "optional-external-id-uuid"
        }}
    )

    @model_validator(mode="after")
    def validate_provider_credentials(self) -> 'IntegrationRequest':
        """
        Validador de modelo (Pydantic v2) para asegurar que el diccionario 'credentials'
        contenga los campos obligatorios correspondientes al proveedor seleccionado.
        """
        # Normalizar a mayúsculas
        provider_upper = self.provider.upper()
        if provider_upper not in ("AWS", "GCP"):
            raise ValueError("El proveedor ('provider') debe ser únicamente 'AWS' o 'GCP'")
        
        # Guardar normalizado
        self.provider = provider_upper

        if provider_upper == "AWS":
            role_arn = self.credentials.get("role_arn")
            s3_bucket = self.credentials.get("s3_bucket")
            
            if not role_arn:
                raise ValueError("Para el proveedor AWS, las credenciales deben incluir obligatoriamente el campo 'role_arn'")
            if not s3_bucket:
                raise ValueError("Para el proveedor AWS, las credenciales deben incluir obligatoriamente el campo 's3_bucket'")
                
            if not role_arn.startswith("arn:aws:iam::"):
                raise ValueError("El campo 'role_arn' debe tener un formato válido de AWS IAM (comenzar con 'arn:aws:iam::')")
                
        elif provider_upper == "GCP":
            project_id_gcp = self.credentials.get("project_id_gcp")
            service_account_key = self.credentials.get("service_account_key")
            
            if not project_id_gcp:
                raise ValueError("Para el proveedor GCP, las credenciales deben incluir obligatoriamente el campo 'project_id_gcp'")
            if not service_account_key:
                raise ValueError("Para el proveedor GCP, las credenciales deben incluir obligatoriamente el campo 'service_account_key'")
                
        return self

class JobAcceptedResponse(BaseModel):
    """
    Esquema de respuesta inmediata enviado al cliente HTTP (HTTP 202 Accepted).
    """
    task_id: str = Field(
        ..., 
        description="Identificador único del Job registrado (SQS MessageId o UUID en desarrollo)",
        json_schema_extra={"example": "550e8400-e29b-41d4-a716-446655440000"}
    )
    status: str = Field(
        "queued", 
        description="Estado inicial de la tarea asíncrona. Siempre será 'queued'",
        json_schema_extra={"example": "queued"}
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        description="Estampa de tiempo UTC del momento de aceptación de la tarea"
    )
