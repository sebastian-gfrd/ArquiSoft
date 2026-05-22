import abc
import re
from typing import Any, Dict

class CloudAdapter(abc.ABC):
    """
    Clase base abstracta (Patrón Adapter) para la integración con diferentes
    proveedores de nube. Todas las implementaciones específicas deben
    heredar de esta clase e implementar sus métodos abstractos.
    """
    
    @abc.abstractmethod
    def validate_credentials(self) -> bool:
        """
        Realiza una validación sintáctica estricta de las credenciales
        proporcionadas para este proveedor de nube.
        
        Para garantizar el ASR-02 (Latencia < 100ms) y evitar bloqueos en el
        hilo principal, este método NO realiza llamadas de red o autenticación real.
        """
        pass

    @abc.abstractmethod
    def build_ingestion_payload(self) -> dict:
        """
        Construye y normaliza el payload de entrada para enviar a la cola de procesamiento
        con un formato estándar, aislando la estructura interna de cada proveedor.
        """
        pass

class AWSAdapter(CloudAdapter):
    """
    Adaptador específico para Amazon Web Services (AWS).
    Realiza la validación sintáctica de los parámetros necesarios para que el Worker
    descargue el reporte AWS Cost and Usage Reports (CUR) desde S3.
    """
    def __init__(self, credentials: Dict[str, Any]):
        self.role_arn = credentials.get("role_arn")
        self.s3_bucket = credentials.get("s3_bucket")
        self.external_id = credentials.get("external_id")

    def validate_credentials(self) -> bool:
        """
        Valida que el formato del Role ARN y el nombre del Bucket S3 cumplan con las
        reglas sintácticas de AWS de manera local (síncrona y no bloqueante).
        """
        # Validación de formato oficial de ARN de AWS IAM: arn:aws:iam::[account-id]:role/[role-name]
        arn_pattern = r"^arn:aws:iam::\d{12}:role/[\w+=,.@-]+$"
        if not self.role_arn or not re.match(arn_pattern, self.role_arn):
            return False
            
        # Validación sintáctica de nombre de bucket S3 según políticas de nomenclatura de AWS
        # Min 3, Max 63 caracteres. Solo minúsculas, números, puntos y guiones.
        bucket_pattern = r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$"
        if not self.s3_bucket or not re.match(bucket_pattern, self.s3_bucket):
            return False
            
        return True

    def build_ingestion_payload(self) -> dict:
        """
        Construye el payload normalizado para AWS CUR.
        """
        return {
            "source_provider": "AWS",
            "ingestion_method": "S3_CUR_PULL",
            "details": {
                "role_arn": self.role_arn,
                "s3_bucket": self.s3_bucket,
                "external_id": self.external_id,
                "report_prefix": "bite-cost-reports"
            }
        }

class GCPAdapter(CloudAdapter):
    """
    Adaptador esquelético para Google Cloud Platform (GCP).
    Demuestra que la arquitectura es extensible bajo el Principio Open/Closed
    (se pueden añadir nuevas nubes sin modificar el core del microservicio).
    """
    def __init__(self, credentials: Dict[str, Any]):
        self.project_id_gcp = credentials.get("project_id_gcp")
        self.service_account_key = credentials.get("service_account_key")

    def validate_credentials(self) -> bool:
        """
        Realiza la validación sintáctica de las credenciales de GCP.
        """
        # Un project_id válido en GCP debe tener entre 6 y 30 caracteres
        gcp_project_pattern = r"^[a-z0-9-]{6,30}$"
        if not self.project_id_gcp or not re.match(gcp_project_pattern, self.project_id_gcp):
            return False
            
        if not self.service_account_key:
            return False
            
        return True

    def build_ingestion_payload(self) -> dict:
        """
        Construye el payload normalizado para GCP BigQuery Export.
        """
        return {
            "source_provider": "GCP",
            "ingestion_method": "BIGQUERY_BILLING_EXPORT",
            "details": {
                "gcp_project_id": self.project_id_gcp,
                "dataset_name": "billing_export_dataset"
            }
        }
