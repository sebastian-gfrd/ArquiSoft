from pydantic import BaseModel, Field
from typing import List

class CloudProviderCost(BaseModel):
    """
    Representa el desglose de costo acumulado para un proveedor específico de nube.
    """
    proveedor: str = Field(
        ..., 
        description="Nombre del proveedor de infraestructura cloud (AWS, GCP, Azure, etc.)",
        examples=["AWS", "GCP", "Azure"]
    )
    costo: float = Field(
        ..., 
        description="Monto acumulado en USD",
        ge=0.0,
        examples=[8543.20]
    )

    class Config:
        from_attributes = True


class DashboardOverview(BaseModel):
    """
    Esquema de respuesta para la vista general del dashboard de costos y optimización.
    """
    costo_total: float = Field(
        ..., 
        description="Costo total de la infraestructura acumulado en USD",
        ge=0.0,
        examples=[12543.50]
    )
    ahorro_proyectado: float = Field(
        ..., 
        description="Dinero que el tenant podría ahorrar aplicando las recomendaciones de optimización",
        ge=0.0,
        examples=[1820.75]
    )
    recursos_infrautilizados_count: int = Field(
        ..., 
        description="Cantidad total de recursos inactivos o con muy baja utilización",
        ge=0,
        examples=[14]
    )
    costos_por_proveedor: List[CloudProviderCost] = Field(
        ..., 
        description="Desglose detallado de costos por proveedor de nube pública"
    )

    class Config:
        from_attributes = True


class MonthlyReport(BaseModel):
    """
    Esquema de respuesta para los reportes mensuales históricos del tenant.
    """
    tenant_id: str = Field(
        ..., 
        description="Identificador único del tenant/cliente en la plataforma multitenant",
        examples=["tenant-123e4567"]
    )
    mes: int = Field(
        ..., 
        description="Mes correspondiente al reporte (1 a 12)",
        ge=1,
        le=12,
        examples=[5]
    )
    año: int = Field(
        ..., 
        description="Año correspondiente al reporte",
        ge=2000,
        examples=[2026]
    )
    costo_computo: float = Field(
        ..., 
        description="Gastos asociados a cómputo (instancias, contenedores, funciones serverless) en USD",
        ge=0.0,
        examples=[6200.50]
    )
    costo_almacenamiento: float = Field(
        ..., 
        description="Gastos asociados a almacenamiento de datos (discos, buckets, bases de datos) en USD",
        ge=0.0,
        examples=[4100.80]
    )
    costo_otros: float = Field(
        ..., 
        description="Otros cargos adicionales (red, soporte, licencias, etc.) en USD",
        ge=0.0,
        examples=[2242.20]
    )
    limite_presupuesto_excedido: bool = Field(
        ..., 
        description="Bandera que indica si el consumo mensual del tenant superó su umbral presupuestado establecido",
        examples=[False]
    )

    class Config:
        from_attributes = True
